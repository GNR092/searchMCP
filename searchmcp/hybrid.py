from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .cache import (
    _config_dir,
    CHROMA_DIR,
    CHROMA_COLLECTION,
    DEFAULT_TOP_K,
    MAX_TOP_K,
    DEFAULT_SIMILARITY_THRESHOLD,
    MODEL_NAME,
    RERANKER_MODEL,
    EMBEDDING_BATCH_SIZE,
    DISABLE_EMBEDDINGS,
    DISABLE_RERANKER,
    MAX_SEQ_LENGTH,
)
from .models import SearchResult


QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


_chroma_collection = None
_embedding_ready: bool | None = None
_embedding_device = "cpu"
_backend_error = ""
_reranker_model: Any = None
_reranker_ready: bool | None = None

logger = logging.getLogger("searchmcp")


def _batch_size() -> int:
    return max(1, EMBEDDING_BATCH_SIZE)


def _embeddings_disabled() -> bool:
    return DISABLE_EMBEDDINGS


def _reranker_disabled() -> bool:
    return DISABLE_RERANKER


def normalize_text(text: str) -> str:
    normalized = text.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def detect_language(text: str) -> str:
    query = text.strip()
    if not query:
        return "unknown"
    try:
        from langdetect import detect

        detected = detect(query)
        if detected.startswith("es"):
            return "es"
        if detected.startswith("en"):
            return "en"
        return "mixed"
    except Exception:
        has_spanish_chars = any(ch in query.lower() for ch in "áéíóúñü¿¡")
        has_english_hints = bool(re.search(r"\b(the|error|how|with|for|and)\b", query.lower()))
        if has_spanish_chars and has_english_hints:
            return "mixed"
        if has_spanish_chars:
            return "es"
        return "en"


def hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


def hash_content(title: str, snippet: str, url: str) -> str:
    content = f"{normalize_text(title)}|{normalize_text(snippet)}|{url.strip().lower()}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class _EmbeddingCache:
    """LRU in-memory cache for embedding vectors keyed by (model, prefix, text)."""

    def __init__(self, capacity: int = 2048) -> None:
        self._capacity = max(1, capacity)
        self._data: OrderedDict[str, list[float]] = OrderedDict()

    def _key(self, model_name: str, prefix: str, text: str) -> str:
        token = f"{model_name}:{prefix}:{text}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def get(self, model_name: str, prefix: str, text: str) -> list[float] | None:
        key = self._key(model_name, prefix, text)
        value = self._data.pop(key, None)
        if value is not None:
            self._data[key] = value
        return value

    def put(self, model_name: str, prefix: str, text: str, vector: list[float]) -> None:
        key = self._key(model_name, prefix, text)
        if key in self._data:
            self._data.move_to_end(key)
        else:
            self._data[key] = vector
        if len(self._data) > self._capacity:
            self._data.popitem(last=False)


_embedding_cache = _EmbeddingCache(capacity=2048)


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


class _EmbeddingFunction:
    def __init__(self, model: Any) -> None:
        self.model = model
        self._tokenizer = getattr(model, "tokenizer", None)
        self._max_seq_length = MAX_SEQ_LENGTH
        if hasattr(model, "max_seq_length") and model.max_seq_length:
            self._max_seq_length = min(int(model.max_seq_length), MAX_SEQ_LENGTH)

    def name(self) -> str:
        return MODEL_NAME

    def _truncate(self, texts: list[str]) -> list[str]:
        if self._tokenizer is None:
            return texts
        try:
            truncated = self._tokenizer(
                texts,
                truncation=True,
                max_length=self._max_seq_length,
                add_special_tokens=True,
            )
            # Reconstruct strings from token ids to keep the input shape expected by encode.
            return self._tokenizer.batch_decode(
                truncated["input_ids"], skip_special_tokens=True
            )
        except Exception:
            return texts

    def _encode_with_cache(self, texts: list[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str]] = []

        for index, text in enumerate(texts):
            cached = _embedding_cache.get(MODEL_NAME, prefix, text)
            if cached is not None:
                vectors[index] = cached
            else:
                missing.append((index, text))

        if missing:
            prefixed = [prefix + text for _, text in missing]
            prefixed = self._truncate(prefixed)
            encoded = self.model.encode(
                prefixed,
                normalize_embeddings=True,
                batch_size=_batch_size(),
                convert_to_numpy=True,
            ).tolist()
            for (index, text), vector in zip(missing, encoded):
                _embedding_cache.put(MODEL_NAME, prefix, text, vector)
                vectors[index] = vector

        return vectors

    def __call__(self, input: Any) -> list[list[float]]:
        if isinstance(input, str):
            input = [input]
        texts = list(input)
        return self._encode_with_cache(texts, PASSAGE_PREFIX)

    def embed_query(self, input: Any) -> list[list[float]]:  # noqa: Vulture; used by ChromaDB
        if isinstance(input, str):
            input = [input]
        texts = list(input)
        return self._encode_with_cache(texts, QUERY_PREFIX)

    def embed_records(self, input: Any) -> list[list[float]]:  # noqa: Vulture; used by ChromaDB
        return self.__call__(input)


def _get_collection() -> Any:
    global _chroma_collection, _embedding_ready, _embedding_device, _backend_error

    if _chroma_collection is not None:
        return _chroma_collection

    if _embeddings_disabled():
        _embedding_ready = False
        _backend_error = "Embeddings disabled (config or SEARCHMCP_DISABLE_EMBEDDINGS=1)"
        logger.warning(_backend_error)
        return None

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _embedding_device = "cuda" if _cuda_available() else "cpu"
        model = SentenceTransformer(MODEL_NAME, device=_embedding_device)
        embedding_function = _EmbeddingFunction(model)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _chroma_collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine"},
        )
        _embedding_ready = True
        _backend_error = ""
        logger.info("ChromaDB + embeddings backend ready on %s", _embedding_device)
        return _chroma_collection
    except Exception as exc:
        _embedding_ready = False
        _backend_error = f"{type(exc).__name__}: {exc}"
        logger.warning("Embedding backend unavailable: %s", _backend_error)
        return None


def backend_status() -> dict[str, Any]:
    collection = _get_collection()
    return {
        "ready": collection is not None,
        "model": MODEL_NAME,
        "device": _embedding_device,
        "path": str(CHROMA_DIR),
        "error": _backend_error,
    }


def count_indexed() -> int:
    collection = _get_collection()
    if collection is None:
        return 0
    try:
        return int(collection.count())
    except Exception:
        return 0


def _record_from_result(query: str, result: SearchResult, source: str, score: float) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    normalized_fragment = normalize_text(result.snippet)
    url_domain = urlparse(result.url).netloc.lower()
    url_hash = hash_url(result.url)
    content_hash = hash_content(result.title, result.snippet, result.url)

    return {
        "id": url_hash,
        "query_original": query,
        "idioma_detectado": detect_language(query),
        "titulo": result.title,
        "url": result.url,
        "dominio": url_domain,
        "fuente": source,
        "fecha_indexacion": now,
        "fecha_acceso": now,
        "access_count": 1,
        "hash_contenido": content_hash,
        "hash_url": url_hash,
        "fragmento_normalizado": normalized_fragment,
        "score": float(score),
        "snippet": result.snippet,
    }


def results_to_records(query: str, results: list[SearchResult], source: str, base_score: float = 0.75) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for result in results:
        records.append(_record_from_result(query, result, source, base_score))
    return records


def index_results(query: str, results: list[SearchResult], source: str = "duckduckgo") -> bool:
    collection = _get_collection()
    if collection is None:
        return False

    records = results_to_records(query, results, source=source, base_score=0.85)
    if not records:
        return True

    ids = [record["id"] for record in records]
    documents = [f"{record['titulo']}\n{record['snippet']}\n{record['url']}" for record in records]
    metadatas = [
        {
            "query_original": record["query_original"],
            "idioma_detectado": record["idioma_detectado"],
            "titulo": record["titulo"],
            "url": record["url"],
            "dominio": record["dominio"],
            "fuente": record["fuente"],
            "fecha_indexacion": record["fecha_indexacion"],
            "fecha_acceso": record["fecha_acceso"],
            "access_count": int(record["access_count"]),
            "hash_contenido": record["hash_contenido"],
            "hash_url": record["hash_url"],
            "fragmento_normalizado": record["fragmento_normalizado"],
            "score": float(record["score"]),
        }
        for record in records
    ]

    try:
        embedding_function = collection._embedding_function
        embeddings = embedding_function(documents)
    except Exception:
        embeddings = None

    try:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        return True
    except Exception:
        return False


def semantic_search(query: str, max_results: int = MAX_TOP_K) -> list[dict[str, Any]]:
    collection = _get_collection()
    if collection is None:
        return []

    top_n = max(1, min(max_results, MAX_TOP_K))
    try:
        raw = collection.query(
            query_texts=[query],
            n_results=top_n,
            include=["metadatas", "documents", "distances"],
        )
    except Exception:
        return []

    metadatas = (raw.get("metadatas") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]
    records: list[dict[str, Any]] = []

    for metadata, document, distance in zip(metadatas, documents, distances):
        score = max(0.0, 1.0 - float(distance)) if distance is not None else float(metadata.get("score", 0.0))
        snippet = metadata.get("fragmento_normalizado") or document or ""
        records.append(
            {
                "id": metadata.get("hash_url", hash_url(metadata.get("url", ""))),
                "query_original": metadata.get("query_original", query),
                "idioma_detectado": metadata.get("idioma_detectado", detect_language(query)),
                "titulo": metadata.get("titulo", ""),
                "url": metadata.get("url", ""),
                "dominio": metadata.get("dominio", ""),
                "fuente": "chroma",
                "fecha_indexacion": metadata.get("fecha_indexacion", ""),
                "fecha_acceso": datetime.utcnow().isoformat(),
                "access_count": int(metadata.get("access_count", 1)),
                "hash_contenido": metadata.get("hash_contenido", ""),
                "hash_url": metadata.get("hash_url", ""),
                "fragmento_normalizado": metadata.get("fragmento_normalizado", normalize_text(snippet)),
                "score": float(score),
                "snippet": snippet,
            }
        )
    return records


def merge_results(
    primary_results: list[dict[str, Any]],
    secondary_results: list[dict[str, Any]],
    top_k: int = DEFAULT_TOP_K,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> tuple[list[dict[str, Any]], bool]:
    merged: dict[str, dict[str, Any]] = {}

    for item in primary_results:
        key = item["hash_url"]
        merged[key] = dict(item)

    for item in secondary_results:
        key = item["hash_url"]
        if key in merged:
            merged_item = merged[key]
            merged_item["score"] = min(1.0, max(merged_item["score"], item["score"]) + 0.10)
            merged_item["fuente"] = "cache+chroma"
            merged_item["snippet"] = merged_item.get("snippet") or item.get("snippet", "")
            merged_item["titulo"] = merged_item.get("titulo") or item.get("titulo", "")
            merged_item["url"] = merged_item.get("url") or item.get("url", "")
        else:
            merged[key] = dict(item)

    ordered = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    clamped_top_k = max(1, min(top_k, MAX_TOP_K))
    selected = ordered[:clamped_top_k]
    useful = bool(selected) and float(selected[0]["score"]) >= similarity_threshold
    return selected, useful


def _load_reranker() -> Any:
    global _reranker_model, _reranker_ready

    if _reranker_ready is not None:
        return _reranker_model if _reranker_ready else None

    if _reranker_disabled():
        _reranker_ready = False
        logger.debug("Reranker disabled (config or SEARCHMCP_DISABLE_RERANKER=1)")
        return None

    try:
        from sentence_transformers import CrossEncoder

        _reranker_model = CrossEncoder(RERANKER_MODEL)
        _reranker_ready = True
        logger.info("Reranker loaded: %s", RERANKER_MODEL)
        return _reranker_model
    except Exception as exc:
        _reranker_ready = False
        logger.warning("Reranker unavailable: %s", exc)
        return None


def rerank_results(query: str, results: list[dict[str, Any]], top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    reranker = _load_reranker()
    if reranker is None or not results:
        return results

    pairs = [[query, f"{r.get('titulo', '')}\n{r.get('snippet', '')}"] for r in results]
    try:
        scores = reranker.predict(pairs)
    except Exception:
        return results

    for record, score in zip(results, scores):
        record["score"] = float(score)
        record["fuente"] = f"{record.get('fuente', '')}+rerank".strip("+")

    ordered = sorted(results, key=lambda item: item["score"], reverse=True)
    clamped_top_k = max(1, min(top_k, MAX_TOP_K))
    return ordered[:clamped_top_k]


def mark_access(results: list[dict[str, Any]]) -> None:
    collection = _get_collection()
    if collection is None:
        return

    now = datetime.utcnow().isoformat()
    for item in results:
        record_id = item.get("hash_url")
        if not record_id:
            continue
        try:
            current = collection.get(ids=[record_id], include=["metadatas"])
            metadatas = current.get("metadatas") or []
            if not metadatas:
                continue
            metadata = dict(metadatas[0])
            metadata["access_count"] = int(metadata.get("access_count", 0)) + 1
            metadata["fecha_acceso"] = now
            collection.update(ids=[record_id], metadatas=[metadata])
        except Exception:
            continue

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import cache
from .models import SearchResult


DEFAULT_TOP_K = 5
MAX_TOP_K = 10
DEFAULT_SIMILARITY_THRESHOLD = 0.60
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHROMA_DIR = Path(".search") / "chroma"
CHROMA_COLLECTION = "search_results"

_chroma_collection = None
_embedding_ready = None
_embedding_device = "cpu"
_backend_error = ""


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


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


class _EmbeddingFunction:
    def __init__(self, model: Any) -> None:
        self.model = model

    def name(self) -> str:
        return MODEL_NAME

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()


def _get_collection() -> Any:
    global _chroma_collection, _embedding_ready, _embedding_device, _backend_error

    if _chroma_collection is not None:
        return _chroma_collection

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
        return _chroma_collection
    except Exception as exc:
        _embedding_ready = False
        _backend_error = str(exc)
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
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return True
    except Exception:
        return False


def _extract_entries_from_markdown(file_path: Path) -> list[dict[str, Any]]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r"##\s+\d+\.\s+(?P<title>.+?)\n\n\*\*URL\*\*:\s+(?P<url>.+?)\n\n(?P<snippet>.*?)(?:\n\n\*\*Motor\*\*:.*?\n\n---|\Z)",
        re.DOTALL,
    )
    entries: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        title = match.group("title").strip()
        url = match.group("url").strip()
        snippet = match.group("snippet").strip()
        entries.append({"title": title, "url": url, "snippet": snippet})
    return entries


def literal_search(query: str, max_results: int = MAX_TOP_K) -> list[dict[str, Any]]:
    terms = [token for token in re.findall(r"[a-z0-9áéíóúñü]+", normalize_text(query)) if len(token) > 2]
    if not terms:
        return []

    result_files = list(cache.CACHE_DIR.glob("*/results.md")) + list(cache.HISTORY_DIR.glob("*/results.md"))
    scored: dict[str, dict[str, Any]] = {}

    for file_path in result_files:
        for entry in _extract_entries_from_markdown(file_path):
            haystack = normalize_text(f"{entry['title']} {entry['snippet']} {entry['url']}")
            matches = sum(1 for term in terms if term in haystack)
            if matches <= 0:
                continue
            score = min(1.0, matches / max(1, len(terms)))
            url_hash = hash_url(entry["url"])
            record = {
                "id": url_hash,
                "query_original": query,
                "idioma_detectado": detect_language(query),
                "titulo": entry["title"],
                "url": entry["url"],
                "dominio": urlparse(entry["url"]).netloc.lower(),
                "fuente": "cache",
                "fecha_indexacion": datetime.utcfromtimestamp(file_path.stat().st_mtime).isoformat(),
                "fecha_acceso": datetime.utcnow().isoformat(),
                "access_count": 1,
                "hash_contenido": hash_content(entry["title"], entry["snippet"], entry["url"]),
                "hash_url": url_hash,
                "fragmento_normalizado": normalize_text(entry["snippet"]),
                "score": float(score),
                "snippet": entry["snippet"],
            }
            existing = scored.get(url_hash)
            if existing is None or record["score"] > existing["score"]:
                scored[url_hash] = record

    ordered = sorted(scored.values(), key=lambda item: item["score"], reverse=True)
    return ordered[: max(1, min(max_results, MAX_TOP_K))]


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
    literal_results: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
    top_k: int = DEFAULT_TOP_K,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> tuple[list[dict[str, Any]], bool]:
    merged: dict[str, dict[str, Any]] = {}

    for item in literal_results:
        key = item["hash_url"]
        merged[key] = dict(item)

    for item in semantic_results:
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

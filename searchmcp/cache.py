from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .models import SearchResult


def _config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "searchMCP"
    return Path.home() / ".config" / "searchMCP"


def _load_config() -> dict:
    """Load config from ~/.config/searchMCP/config.json"""
    config_path = _config_dir() / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


_config = _load_config()

# Configurable defaults (JSON > env > hardcoded)
DEFAULT_TOP_K = int(_config.get("default_top_k", 5))
MAX_TOP_K = int(_config.get("max_top_k", 10))
DEFAULT_SIMILARITY_THRESHOLD = float(_config.get("similarity_threshold", 0.60))
MODEL_NAME = _config.get("model_name", "intfloat/multilingual-e5-small")
RERANKER_MODEL = _config.get("reranker_model", os.environ.get(
    "SEARCHMCP_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
))
EMBEDDING_BATCH_SIZE = int(_config.get("embedding_batch_size", os.environ.get("SEARCHMCP_EMBEDDING_BATCH_SIZE", "32")))
DISABLE_EMBEDDINGS = _config.get("disable_embeddings", os.environ.get("SEARCHMCP_DISABLE_EMBEDDINGS") == "1")
DISABLE_RERANKER = _config.get("disable_reranker", os.environ.get("SEARCHMCP_DISABLE_RERANKER") == "1")
MAX_SEQ_LENGTH = int(_config.get("max_seq_length", 512))
CHROMA_COLLECTION = _config.get("chroma_collection", "search_results")

HISTORY_DIR = _config_dir() / "history"
HISTORY_DAYS = int(_config.get("history_days", 30))
CHROMA_DIR = _config_dir() / "chroma"


def _ensure_dirs() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_old_history(days: int = HISTORY_DAYS) -> int:
    if not HISTORY_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0

    for item in HISTORY_DIR.iterdir():
        if not item.is_dir():
            continue
        try:
            timestamp = datetime.strptime(item.name, "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if timestamp < cutoff:
            for file_item in item.iterdir():
                file_item.unlink(missing_ok=True)
            item.rmdir()
            deleted += 1

    return deleted


def save_to_history(query: str, results: list[SearchResult]) -> str:
    _ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = HISTORY_DIR / timestamp
    history_path.mkdir(parents=True, exist_ok=True)

    md_content = f"# Búsqueda: {query}\n\n"
    md_content += f"Fecha: {datetime.now().isoformat()}\n\n"
    md_content += "---\n\n"

    for i, result in enumerate(results, 1):
        md_content += f"## {i}. {result.title}\n\n"
        md_content += f"**URL**: {result.url}\n\n"
        md_content += f"{result.snippet}\n\n"
        md_content += f"**Motor**: {result.engine}\n\n"
        md_content += "---\n\n"

    (history_path / "results.md").write_text(md_content, encoding="utf-8")
    (history_path / "query.txt").write_text(query, encoding="utf-8")

    cleanup_old_history()

    return str(history_path.absolute())

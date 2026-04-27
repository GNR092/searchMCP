from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import SearchResult


CACHE_DIR = Path(".search") / "cache"
HISTORY_DIR = Path(".search") / "history"
CACHE_SIZE_WARNING = 100
HISTORY_DAYS = 30


def _ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_key(query: str) -> str:
    return hashlib.sha256(query.lower().strip().encode("utf-8")).hexdigest()[:16]


def get_cache_path(query: str) -> Path:
    return CACHE_DIR / get_cache_key(query)


def get_cached(query: str) -> Optional[str]:
    results_file = get_cache_path(query) / "results.md"
    if results_file.exists():
        return results_file.read_text(encoding="utf-8", errors="ignore")
    return None


def set_cached(query: str, results: list[SearchResult]) -> str:
    _ensure_dirs()
    cache_key = get_cache_key(query)
    cache_path = CACHE_DIR / cache_key
    cache_path.mkdir(parents=True, exist_ok=True)

    md_content = f"# Búsqueda (caché): {query}\n\n"
    md_content += f"Fecha: {datetime.now().isoformat()}\n"
    md_content += f"Clave de caché: {cache_key}\n\n"
    md_content += "---\n\n"

    for i, result in enumerate(results, 1):
        md_content += f"## {i}. {result.title}\n\n"
        md_content += f"**URL**: {result.url}\n\n"
        md_content += f"{result.snippet}\n\n"
        md_content += f"**Motor**: {result.engine}\n\n"
        md_content += "---\n\n"

    (cache_path / "results.md").write_text(md_content, encoding="utf-8")
    (cache_path / "query.txt").write_text(query, encoding="utf-8")
    return str(cache_path.absolute())


def check_cache_size() -> tuple[int, bool]:
    if not CACHE_DIR.exists():
        return 0, False
    count = sum(1 for item in CACHE_DIR.iterdir() if item.is_dir())
    return count, count > CACHE_SIZE_WARNING


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


def is_codesearch_available() -> bool:
    return shutil.which("codesearch") is not None


def index_with_codesearch(timeout_seconds: int = 60) -> bool:
    if not is_codesearch_available():
        return False
    try:
        result = subprocess.run(
            ["codesearch", "index"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def save_to_history(query: str, results: list[SearchResult], auto_index: bool = True) -> str:
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
    if auto_index and is_codesearch_available():
        index_with_codesearch()

    return str(history_path.absolute())


def get_cache_warning() -> Optional[str]:
    count, warning = check_cache_size()
    if warning:
        return f"[AVISO] Caché acumulado: {count} entradas. Considera limpiar con 'search_cleanup'."
    return None

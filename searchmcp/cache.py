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


def get_cache_key(query: str) -> str:
    return hashlib.sha256(query.lower().encode()).hexdigest()[:16]


def get_cache_path(query: str) -> Path:
    cache_key = get_cache_key(query)
    return CACHE_DIR / cache_key


def get_cached(query: str) -> Optional[str]:
    cache_path = get_cache_path(query)
    results_file = cache_path / "results.md"

    if results_file.exists():
        return results_file.read_text(encoding="utf-8")
    return None


def set_cached(query: str, results: list[SearchResult]) -> str:
    cache_key = get_cache_key(query)
    cache_path = CACHE_DIR / cache_key
    cache_path.mkdir(parents=True, exist_ok=True)

    md_content = f"# Búsqueda (caché): {query}\n\n"
    md_content += f"Fecha: {datetime.now().isoformat()}\n"
    md_content += f"Clave de caché: {cache_key}\n\n"
    md_content += "---\n\n"

    for i, r in enumerate(results, 1):
        md_content += f"## {i}. {r.title}\n\n"
        md_content += f"**URL**: {r.url}\n\n"
        md_content += f"{r.snippet}\n\n"
        md_content += f"**Motor**: {r.engine}\n\n"
        md_content += "---\n\n"

    results_file = cache_path / "results.md"
    results_file.write_text(md_content, encoding="utf-8")

    query_file = cache_path / "query.txt"
    query_file.write_text(query, encoding="utf-8")

    return str(cache_path.absolute())


def check_cache_size() -> tuple[int, bool]:
    if not CACHE_DIR.exists():
        return 0, False

    count = len([d for d in CACHE_DIR.iterdir() if d.is_dir()])
    warning = count > CACHE_SIZE_WARNING
    return count, warning


def cleanup_old_history(days: int = HISTORY_DAYS) -> int:
    if not HISTORY_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0

    for item in HISTORY_DIR.iterdir():
        if item.is_dir():
            try:
                timestamp_str = item.name
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                if timestamp < cutoff:
                    for f in item.iterdir():
                        f.unlink()
                    item.rmdir()
                    deleted += 1
            except ValueError:
                continue

    return deleted


def save_to_history(query: str, results: list[SearchResult]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = HISTORY_DIR / timestamp
    history_path.mkdir(parents=True, exist_ok=True)

    md_content = f"# Búsqueda: {query}\n\n"
    md_content += f"Fecha: {datetime.now().isoformat()}\n\n"
    md_content += "---\n\n"

    for i, r in enumerate(results, 1):
        md_content += f"## {i}. {r.title}\n\n"
        md_content += f"**URL**: {r.url}\n\n"
        md_content += f"{r.snippet}\n\n"
        md_content += f"**Motor**: {r.engine}\n\n"
        md_content += "---\n\n"

    results_file = history_path / "results.md"
    results_file.write_text(md_content, encoding="utf-8")

    query_file = history_path / "query.txt"
    query_file.write_text(query, encoding="utf-8")

    cleanup_old_history()

    return str(history_path.absolute())


def get_cache_warning() -> Optional[str]:
    count, warning = check_cache_size()
    if warning:
        return f"[AVISO] Caché acumulado: {count} entradas. Considera limpiar con 'search_cleanup'."
    return None


def is_codesearch_available() -> bool:
    """Detecta si codesearch esta instalado y disponible."""
    return shutil.which("codesearch") is not None


def index_with_codesearch() -> bool:
    """Ejecuta codesearch index si esta disponible. Retorna True si se ejecuto."""
    if not is_codesearch_available():
        return False

    try:
        result = subprocess.run(
            ["codesearch", "index"],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def save_to_history(query: str, results: list[SearchResult], auto_index: bool = True) -> str:
    """Guarda en historial y opcionalmente indexa con codesearch."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = HISTORY_DIR / timestamp
    history_path.mkdir(parents=True, exist_ok=True)

    md_content = f"# Búsqueda: {query}\n\n"
    md_content += f"Fecha: {datetime.now().isoformat()}\n\n"
    md_content += "---\n\n"

    for i, r in enumerate(results, 1):
        md_content += f"## {i}. {r.title}\n\n"
        md_content += f"**URL**: {r.url}\n\n"
        md_content += f"{r.snippet}\n\n"
        md_content += f"**Motor**: {r.engine}\n\n"
        md_content += "---\n\n"

    results_file = history_path / "results.md"
    results_file.write_text(md_content, encoding="utf-8")

    query_file = history_path / "query.txt"
    query_file.write_text(query, encoding="utf-8")

    cleanup_old_history()

    if auto_index and is_codesearch_available():
        index_with_codesearch()

    return str(history_path.absolute())
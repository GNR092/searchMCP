from __future__ import annotations
import logging
import os
import time
from ddgs import DDGS
from typing import List
from ..models import SearchResult


os.environ["DDGS_LOG"] = "error"
for logger_name in ["ddgs", "primp", "httpcore", "httpx", "httpcore.http11"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

MAX_RETRIES = 3
BASE_DELAY = 0.5


def _retry_on_exception(func):
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    delay = BASE_DELAY * (2 ** attempt)
                    time.sleep(delay)
        raise last_exc
    return wrapper


@_retry_on_exception
def _search_with_retry(query: str, max_results: int) -> List[SearchResult]:
    results = []
    with DDGS() as ddgs:
        for result in ddgs.text(query, max_results=max_results):
            results.append(SearchResult(
                title=result.get("title", ""),
                url=result.get("href", ""),
                snippet=result.get("body", ""),
                engine="duckduckgo"
            ))
    return results


def search_duckduckgo(query: str, max_results: int = 10) -> List[SearchResult]:
    """Busca en DuckDuckGo y retorna una lista de SearchResult.

    Args:
        query: Término de búsqueda
        max_results: Número máximo de resultados a retornar

    Returns:
        Lista de SearchResult con título, URL, snippet y motor
    """
    return _search_with_retry(query, max_results)
from __future__ import annotations
import logging
import os
from ddgs import DDGS
from typing import List
from ..models import SearchResult


os.environ["DDGS_LOG"] = "error"
for logger_name in ["ddgs", "primp", "httpcore", "httpx", "httpcore.http11"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)


def search_duckduckgo(query: str, max_results: int = 10) -> List[SearchResult]:
    """Busca en DuckDuckGo y retorna una lista de SearchResult.

    Args:
        query: Término de búsqueda
        max_results: Número máximo de resultados a retornar

    Returns:
        Lista de SearchResult con título, URL, snippet y motor
    """
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
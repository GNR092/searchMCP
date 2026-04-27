from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from .providers.duckduckgo import search_duckduckgo
from .models import SearchResult
from . import cache


mcp = FastMCP("searchmcp")


@mcp.tool()
async def search(query: str, max_results: int = 10) -> str:
    """Busca en la web usando DuckDuckGo.

    Args:
        query: Término de búsqueda
        max_results: Número máximo de resultados a retornar. Default: 10

    Returns:
        Resultados formateados de la búsqueda
    """
    results = await search_duckduckgo(query, max_results)
    return format_results(results)


@mcp.tool()
async def search_cached(query: str, max_results: int = 10) -> str:
    """Busca con caché permanente. Si la query ya fue buscada, retorna resultados en caché (0 tokens).
    Si es nueva, guarda en caché permanentemente e indexa para codesearch.

    Args:
        query: Término de búsqueda
        max_results: Número máximo de resultados a retornar. Default: 10

    Returns:
        Resultados formateados (del caché o frescos)
    """
    cached = cache.get_cached(query)
    if cached:
        warning = cache.get_cache_warning()
        msg = f"[CACHÉ] Resultados de: \"{query}\"\n"
        if warning:
            msg += f"\n{warning}\n"
        msg += "\n" + cached
        return msg

    results = await search_duckduckgo(query, max_results)

    cache.set_cached(query, results)
    cache.save_to_history(query, results)

    warning = cache.get_cache_warning()
    msg = f"[NUEVO] Resultados de: \"{query}\"\n"
    if warning:
        msg += f"\n{warning}\n"
    msg += "\n" + format_results(results)
    return msg


@mcp.tool()
async def search_and_save(query: str, max_results: int = 10) -> str:
    """Busca en la web y guarda los resultados en la carpeta .search/ para consultarlos después con codesearch.

    Args:
        query: Término de búsqueda
        max_results: Número máximo de resultados a retornar. Default: 10

    Returns:
        Ruta donde se guardaron los resultados
    """
    results = await search_duckduckgo(query, max_results)
    save_path = cache.save_to_history(query, results)
    cache.set_cached(query, results)
    return f"Resultados guardados en: {save_path}\n\nPara indexar: codesearch index --sync"


@mcp.tool()
def search_cleanup() -> str:
    """Limpia el historial de búsqueda antiguo (entradas mayores a 30 días).

    Returns:
        Número de entradas eliminadas
    """
    deleted = cache.cleanup_old_history()
    cache_count, _ = cache.check_cache_size()
    return f"Eliminadas {deleted} entradas de historial antiguo.\nCaché tiene {cache_count} entradas."


@mcp.tool()
def search_stats() -> str:
    """Muestra estadísticas del caché e historial.

    Returns:
        Estadísticas sobre el caché y el historial
    """
    cache_count, cache_warning = cache.check_cache_size()
    history_count = len(list(cache.HISTORY_DIR.glob("*"))) if cache.HISTORY_DIR.exists() else 0

    msg = f"## Estadísticas de Búsqueda\n\n"
    msg += f"- **Caché permanente**: {cache_count} entradas\n"
    msg += f"- **Historial (30 días)**: {history_count} entradas\n"

    if cache_warning:
        msg += f"\n[AVISO] El caché tiene {cache_count} entradas. Considera limpiar con 'search_cleanup'."

    return msg


def format_results(results: list[SearchResult]) -> str:
    if not results:
        return "No se encontraron resultados."

    output = []
    for i, r in enumerate(results, 1):
        output.append(f"{i}. {r.title}")
        output.append(f"   URL: {r.url}")
        output.append(f"   {r.snippet}")
        output.append(f"   (vía {r.engine})")
        output.append("")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Servidor SearchMCP")
    parser.add_argument("--verbose", action="store_true", help="Habilitar logging detallado")
    args, _ = parser.parse_known_args()

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
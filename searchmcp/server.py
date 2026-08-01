from __future__ import annotations
import asyncio
import argparse
import logging
from typing import Any
from mcp.server.fastmcp import FastMCP
from .providers.duckduckgo import search_duckduckgo
from .models import SearchResult
from . import cache
from . import hybrid


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("searchmcp")

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
    results = await asyncio.to_thread(search_duckduckgo, query, max_results)
    return format_results(results)


@mcp.tool()
async def search_cached(
    query: str,
    top_k: int = hybrid.DEFAULT_TOP_K,
    similarity_threshold: float = hybrid.DEFAULT_SIMILARITY_THRESHOLD,
    web_max_results: int = hybrid.MAX_TOP_K,
) -> str:
    """Búsqueda híbrida multilingüe (es/en) con embeddings locales (ChromaDB) + web fallback.

    Args:
        query: Término de búsqueda
        top_k: Número de resultados a retornar (default 5, máximo 10)
        similarity_threshold: Umbral para decidir si resultados locales son útiles. Default: 0.60
        web_max_results: Número máximo de resultados para web fallback. Default: 10

    Returns:
        Resultados formateados (del caché o frescos)
    """
    top_k = max(1, min(top_k, hybrid.MAX_TOP_K))
    web_max_results = max(1, min(web_max_results, hybrid.MAX_TOP_K))

    backend = hybrid.backend_status()
    local_results: list[dict[str, Any]] = []
    useful_local = False
    backend_warning = ""

    if backend["ready"]:
        semantic_results = hybrid.semantic_search(query, max_results=hybrid.MAX_TOP_K)
        local_results, useful_local = hybrid.merge_results(
            semantic_results,
            [],
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )

    if not backend["ready"]:
        backend_warning = f"[AVISO] Backend de embeddings no disponible: {backend.get('error') or 'unknown'}. Usando búsqueda web."
        logger.warning(backend_warning)

    if useful_local:
        reranked = hybrid.rerank_results(query, local_results, top_k=top_k)
        hybrid.mark_access(reranked)
        return format_hybrid_results(
            query=query,
            mode="LOCAL",
            results=reranked,
            threshold=similarity_threshold,
            warning=backend_warning or None,
        )

    web_results = await asyncio.to_thread(search_duckduckgo, query, web_max_results)
    history_path = cache.save_to_history(query, web_results)

    if backend["ready"]:
        hybrid.index_results(query, web_results, source="duckduckgo")

    web_records = hybrid.results_to_records(query, web_results, source="duckduckgo", base_score=0.80)
    merged_after_web, _ = hybrid.merge_results(
        local_results,
        web_records,
        top_k=top_k,
        similarity_threshold=0.0,
    )
    reranked = hybrid.rerank_results(query, merged_after_web, top_k=top_k)

    message = format_hybrid_results(
        query=query,
        mode="WEB_FALLBACK",
        results=reranked,
        threshold=similarity_threshold,
        warning=backend_warning or None,
    )
    message += f"\n\nHistorial guardado en: {history_path}"
    return message


@mcp.tool()
async def search_and_save(query: str, max_results: int = 10) -> str:
    """Busca en la web, guarda el historial en disco y embebe los resultados en ChromaDB.

    Args:
        query: Término de búsqueda
        max_results: Número máximo de resultados a retornar. Default: 10

    Returns:
        Ruta donde se guardaron los resultados
    """
    results = await asyncio.to_thread(search_duckduckgo, query, max_results)
    save_path = cache.save_to_history(query, results)

    backend = hybrid.backend_status()
    if backend["ready"]:
        hybrid.index_results(query, results, source="duckduckgo")
        index_msg = "Indexados en ChromaDB para búsqueda semántica posterior."
    else:
        index_msg = f"Backend de embeddings no disponible ({backend.get('error') or 'unknown'}); solo se guardó historial."
        logger.warning("search_and_save: %s", index_msg)

    return f"Resultados guardados en: {save_path}\n\n{index_msg}"


@mcp.tool()
def search_cleanup() -> str:
    """Limpia el historial de búsqueda antiguo (entradas mayores a 30 días).

    Returns:
        Número de entradas eliminadas
    """
    deleted = cache.cleanup_old_history()
    return f"Eliminadas {deleted} entradas de historial antiguo."


@mcp.tool()
def search_stats() -> str:
    """Muestra estadísticas del historial y del índice semántico local.

    Returns:
        Estadísticas sobre el historial y ChromaDB
    """
    history_count = len(list(cache.HISTORY_DIR.glob("*"))) if cache.HISTORY_DIR.exists() else 0
    backend = hybrid.backend_status()
    indexed_count = hybrid.count_indexed()

    msg = f"## Estadísticas de Búsqueda\n\n"
    msg += f"- **Historial (30 días)**: {history_count} entradas\n"
    msg += f"- **ChromaDB**: {'Activo' if backend['ready'] else 'No disponible'}\n"
    msg += f"- **Modelo embeddings**: {backend['model']}\n"
    msg += f"- **Dispositivo**: {backend['device']}\n"
    msg += f"- **Documentos indexados (ChromaDB)**: {indexed_count}\n"
    if not backend["ready"] and backend.get("error"):
        msg += f"- **Error backend**: {backend['error']}\n"

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


def format_hybrid_results(
    query: str,
    mode: str,
    results: list[dict],
    threshold: float,
    warning: str | None = None,
) -> str:
    if not results:
        return f"[{mode}] Sin resultados para: \"{query}\""

    output: list[str] = []
    output.append(f"[{mode}] Resultados para: \"{query}\"")
    output.append(f"Umbral aplicado: {threshold:.2f}")
    if warning:
        output.append(warning)
    output.append("")

    for index, result in enumerate(results, 1):
        output.append(f"{index}. {result.get('titulo', '')}")
        output.append(f"   URL: {result.get('url', '')}")
        output.append(f"   Fuente: {result.get('fuente', '')}")
        output.append(f"   Score: {float(result.get('score', 0.0)):.3f}")
        snippet = result.get("snippet") or result.get("fragmento_normalizado", "")
        output.append(f"   {snippet}")
        output.append("")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Servidor SearchMCP: búsqueda web con caché local e indexado")
    parser.add_argument(
        "-search",
        "--search",
        metavar="QUERY",
        help="Realiza una búsqueda web y muestra los resultados en consola",
    )
    parser.add_argument(
        "-n",
        "--max-results",
        type=int,
        default=10,
        help="Número máximo de resultados a mostrar (default: 10)",
    )
    parser.add_argument("--verbose", action="store_true", help="Habilitar logging detallado")
    args = parser.parse_args()

    if args.search:
        results = asyncio.run(search(args.search, max_results=args.max_results))
        print(results)
        return

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

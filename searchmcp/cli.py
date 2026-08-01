from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

from . import hybrid
from . import server


def _output(text: str, as_json: bool, payload: dict[str, Any] | None = None) -> None:
    if as_json:
        output = {"text": text}
        if payload:
            output.update(payload)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(text)


async def _cmd_search(args: argparse.Namespace) -> None:
    results = await server.search(args.query, max_results=args.max_results)
    _output(
        results,
        args.json,
        {"command": "search", "query": args.query, "max_results": args.max_results},
    )


async def _cmd_cached(args: argparse.Namespace) -> None:
    if args.disable_embeddings:
        os.environ["SEARCHMCP_DISABLE_EMBEDDINGS"] = "1"
    results = await server.search_cached(
        args.query,
        top_k=args.top_k,
        similarity_threshold=args.threshold,
        web_max_results=args.max_results,
    )
    _output(
        results,
        args.json,
        {
            "command": "cached",
            "query": args.query,
            "top_k": args.top_k,
            "threshold": args.threshold,
            "max_results": args.max_results,
            "disable_embeddings": args.disable_embeddings,
        },
    )


async def _cmd_save(args: argparse.Namespace) -> None:
    results = await server.search_and_save(args.query, max_results=args.max_results)
    _output(
        results,
        args.json,
        {"command": "save", "query": args.query, "max_results": args.max_results},
    )


def _cmd_stats(args: argparse.Namespace) -> None:
    results = server.search_stats()
    _output(results, args.json, {"command": "stats"})


def _cmd_cleanup(args: argparse.Namespace) -> None:
    results = server.search_cleanup()
    _output(results, args.json, {"command": "cleanup"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="searchmcp",
        description="SearchMCP: servidor MCP y CLI de búsqueda semántica multilingüe.",
    )

    sub = parser.add_subparsers(dest="command", help="Comandos disponibles")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", help="Devuelve la salida en formato JSON"
    )
    common.add_argument(
        "--verbose", action="store_true", help="Habilita logging detallado (DEBUG)"
    )

    p_search = sub.add_parser(
        "search", parents=[common], help="Búsqueda web directa con DuckDuckGo"
    )
    p_search.add_argument("query", help="Término de búsqueda")
    p_search.add_argument(
        "-n", "--max-results", type=int, default=10,
        help="Número máximo de resultados (default: 10)"
    )

    p_cached = sub.add_parser(
        "cached", parents=[common], help="Búsqueda híbrida semántica (ChromaDB) + fallback web"
    )
    p_cached.add_argument("query", help="Término de búsqueda")
    p_cached.add_argument(
        "-k", "--top-k", type=int, default=hybrid.DEFAULT_TOP_K,
        help="Resultados a retornar (default: 5, max: 10)"
    )
    p_cached.add_argument(
        "-t", "--threshold", type=float, default=hybrid.DEFAULT_SIMILARITY_THRESHOLD,
        help="Umbral de similitud para usar resultados locales (default: 0.60)"
    )
    p_cached.add_argument(
        "-n", "--max-results", type=int, default=hybrid.MAX_TOP_K,
        help="Resultados máximos de fallback web (default: 10)"
    )
    p_cached.add_argument(
        "--disable-embeddings", action="store_true",
        help="Fuerza búsqueda web sin cargar embeddings"
    )

    p_save = sub.add_parser(
        "save", parents=[common], help="Busca en la web, guarda historial e indexa en ChromaDB"
    )
    p_save.add_argument("query", help="Término de búsqueda")
    p_save.add_argument(
        "-n", "--max-results", type=int, default=10,
        help="Número máximo de resultados (default: 10)"
    )

    sub.add_parser("stats", parents=[common], help="Muestra estadísticas del historial e índice")
    sub.add_parser("cleanup", parents=[common], help="Elimina historial de más de 30 días")
    sub.add_parser("server", parents=[common], help="Inicia el servidor MCP por stdio (default)")

    return parser


def _handle_legacy_flags(argv: list[str]) -> list[str]:
    """Convierte el uso legacy `-search "q" -n 5` al subcomando `search`."""
    if not argv:
        return argv
    if argv[0] in ("-search", "--search"):
        new_argv = ["search"]
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg in ("-search", "--search"):
                if i + 1 < len(argv):
                    new_argv.append(argv[i + 1])
                    i += 2
                else:
                    i += 1
            elif arg in ("-n", "--max-results"):
                if i + 1 < len(argv):
                    new_argv.extend(["-n", argv[i + 1]])
                    i += 2
                else:
                    i += 1
            else:
                new_argv.append(arg)
                i += 1
        return new_argv
    return argv


def main(argv: list[str] | None = None) -> None:
    raw_argv = argv if argv is not None else sys.argv[1:]
    processed_argv = _handle_legacy_flags(raw_argv)

    parser = _build_parser()
    args = parser.parse_args(processed_argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.DEBUG)

    if args.command is None or args.command == "server":
        server.mcp.run(transport="stdio")
        return

    if args.command == "search":
        asyncio.run(_cmd_search(args))
    elif args.command == "cached":
        asyncio.run(_cmd_cached(args))
    elif args.command == "save":
        asyncio.run(_cmd_save(args))
    elif args.command == "stats":
        _cmd_stats(args)
    elif args.command == "cleanup":
        _cmd_cleanup(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

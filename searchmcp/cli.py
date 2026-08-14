from __future__ import annotations

import sys
import tomllib

from .server import mcp


def _get_version() -> str:
    """Lee la versión de pyproject.toml."""
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


__version__ = _get_version()


def main() -> None:
    """Punto de entrada CLI para searchmcp."""
    args = sys.argv[1:]

    if "--version" in args or "-v" in args:
        print(f"searchmcp {_get_version()}")
        sys.exit(0)

    if "--help" in args or "-h" in args:
        print("""
searchmcp - Servidor MCP de búsqueda semántica multilingüe

Uso:
  searchmcp [OPCIONES]

Opciones:
  --version, -v   Mostrar versión
  --help, -h      Mostrar esta ayuda

Comandos disponibles (usar con MCP client):
  search       Busca en la web usando DuckDuckGo
  search_cached Búsqueda híbrida: ChromaDB + fallback DuckDuckGo
  search_and_save Fuerza búsqueda web e indexa en ChromaDB
  search_stats Muestra estado del historial, ChromaDB, modelo y dispositivo
  search_cleanup Elimina historial de más de 30 días
""")
        sys.exit(0)

    # Lanzar el server FastMCP
    import asyncio

    async def run():
        from mcp.server import Server
        from mcp.types import ServerCapabilities

        async with mcp.server(
            server=Server(
                config=mcp.config,
                capabilities=ServerCapabilities(
                    {},
                ),
            )
        ) as server:
            pass

    asyncio.run(run())


if __name__ == "__main__":
    main()
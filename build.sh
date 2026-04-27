#!/bin/bash
# Build script para Linux

set -e

echo "Construyendo searchmcp para Linux..."

pip install pyinstaller -q

pyinstaller \
    --name searchmcp \
    --onefile \
    --console \
    --clean \
    --add-data ".search:.search" \
    --hidden-import mcp.server.fastmcp \
    --hidden-import mcp.server.stdio \
    --hidden-import mcp.types \
    --hidden-import ddgs \
    --hidden-import searchmcp.providers.duckduckgo \
    --hidden-import searchmcp.cache \
    --hidden-import searchmcp.models \
    searchmcp/server.py

echo "Binario creado: dist/searchmcp"
ls -lh dist/searchmcp

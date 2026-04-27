@echo off
REM Build script para Windows

echo Construyendo searchmcp para Windows...

pip install pyinstaller -q

pyinstaller ^
    --name searchmcp ^
    --onefile ^
    --console ^
    --clean ^
    --add-data ".search;." ^
    --hidden-import mcp.server.fastmcp ^
    --hidden-import mcp.server.stdio ^
    --hidden-import mcp.types ^
    --hidden-import ddgs ^
    --hidden-import searchmcp.providers.duckduckgo ^
    --hidden-import searchmcp.cache ^
    --hidden-import searchmcp.models ^
    searchmcp/server.py

echo.
echo Binario creado: dist\searchmcp.exe
dir dist\searchmcp.exe

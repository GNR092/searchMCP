# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['searchmcp\\server.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['mcp.server.fastmcp', 'mcp.server.stdio', 'mcp.types', 'ddgs', 'searchmcp.providers.duckduckgo', 'searchmcp.cache', 'searchmcp.models'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'sphinx', 'jupyter', 'ipython', 'numpy', 'pandas', 'matplotlib', 'tkinter', 'PyQt5', 'PySide6', 'PyQt6', 'PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='searchmcp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

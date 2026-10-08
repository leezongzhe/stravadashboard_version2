# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = [
    ("dashboard.py", "."),
    ("config.example.json", "."),
    *collect_data_files("streamlit"),
    *collect_data_files("plotly"),
    *collect_data_files("pydeck"),
]
for package in ("streamlit", "plotly", "pydeck", "playwright", "pandas", "numpy", "altair"):
    datas += copy_metadata(package)
binaries = []
hiddenimports = [
    "app.backup",
    "app.ai_context",
    "app.ai_provider",
    "app.credential_store",
    "app.metrics",
    "numpy",
    "pandas",
    "plotly.express",
    "plotly.graph_objects",
    "pydeck",
    "streamlit",
    "streamlit.runtime.scriptrunner.magic_funcs",
]

a = Analysis(
    ["launcher_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
launcher_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StravaDashboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
server_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StravaDashboardServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    launcher_exe,
    server_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="StravaDashboard",
)

# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file per FastAPI Backend
Eseguibile standalone (onefile, console) per backend web :8000
NOTA: legge config.json e data/ dalla cartella in cui viene eseguito
(la root della build NSTONELLM_App).
"""

from pathlib import Path

project_root = Path(SPECPATH)


def project_package_modules(*folders):
    found = []
    for folder in folders:
        base = project_root / folder
        if not base.is_dir():
            continue
        for py in base.rglob('*.py'):
            rel = py.relative_to(project_root)
            parts = list(rel.with_suffix('').parts)
            if 'tests' in parts or '__pycache__' in parts:
                continue
            if parts[-1] == '__init__':
                parts = parts[:-1]
            if parts:
                found.append('.'.join(parts))
    return sorted(set(found))


hiddenimports = project_package_modules('fastapi_backend', 'modules') + [
    'fastapi',
    'uvicorn',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.logging',
    'pydantic',
    'starlette',
    'starlette.applications',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'multipart',
    'sqlite3',
    'json',
    'uuid',
    'logging',
    'pathlib',
    'datetime',
    'typing',
]

a = Analysis(
    [str(project_root / 'fastapi_backend_launcher.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'matplotlib', 'numpy', 'pandas', 'tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='fastapi_backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console mode per vedere i log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file per snap7_multifilo_server
Eseguibile standalone (onefile) per simulazione PLC Multifilo
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

project_root = Path(SPECPATH)

binaries = []
snap7_dll = project_root / 'bin' / 'snap7.dll'
if snap7_dll.is_file():
    binaries.append((str(snap7_dll), '.'))
    binaries.append((str(snap7_dll), 'bin'))
binaries += collect_dynamic_libs('snap7')

a = Analysis(
    [str(project_root / 'snap7_multifilo_server.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        'snap7',
        'struct',
        'time',
        'random',
        'threading',
        'logging',
        'ctypes',
        'datetime',
    ],
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
    name='snap7_multifilo_server',
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

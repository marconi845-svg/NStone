# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file per NSTONELLM — BETA V1.14 LOCALE
Build one-folder (layout flat, compatibile col vecchio comportamento PyInstaller 5):
tutte le risorse accanto all'exe, sorgenti Python inclusi come datas per
supportare gli import dinamici a runtime.

Comando:
  pyinstaller --distpath "%USERPROFILE%\\Desktop" --workpath "%USERPROFILE%\\Desktop\\build_temp" --clean nstone_main_window.spec
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

project_root = Path(SPECPATH).resolve().parent

# ============================================================================
# DATAS — cartelle e file copiati accanto all'exe (layout flat)
# NOTA: rust_engine/ (sorgenti Rust, ~2.3 GB di target/) è ESCLUSO di proposito:
# il modulo compilato arriva da site-packages via hiddenimports.
# logs/ è escluso: viene creato vuoto da BUILD.bat.
# ============================================================================
data_folders = [
    'agents',
    'app',
    'assets',
    'core',
    'data',
    'database',
    'fastapi_backend',
    'integrations',
    'llm',
    'machines',
    'modules',
    'plc',
    'plc_maps',
    'python_app',
    'python_engine',
    'rust_core',
    'safety',
    'scripts',
    'services',
    'ui',
    'workers',
]

root_files = [
    'config.json',
    'config.json.example',
    'run.py',
    'ngrok.exe',
]

datas = []
for folder in data_folders:
    src = project_root / folder
    if src.is_dir():
        datas.append((str(src), folder))

for fname in root_files:
    src = project_root / fname
    if src.is_file():
        datas.append((str(src), '.'))

# ============================================================================
# HIDDENIMPORTS — moduli root + tutti i moduli dei pacchetti del progetto
# (enumerati dai sorgenti: robusto contro import dinamici)
# ============================================================================
root_modules = [
    'action_executor', 'agents_config', 'ai_assistant', 'autonomy_policy',
    'backup_nstonellm', 'check_db',
    'cnc_adapter', 'cnc_simulator', 'cnc_simulator_integration', 'cnc_ui_integration',
    'cnc_worker', 'dashboard_worker', 'data_loader',
    'fanghi_simulator_integration', 'gcode_ai_integration', 'gcode_worker',
    'gemini_model_registry', 'gemini_service', 'host_hardware',
    'llm_contexts', 'llm_inference_manager', 'llm_service',
    'lucidatrice_snap7_integration', 'lucidatrice_ui_integration',
    'machine_plc_config',
    'multifilo_snap7_integration', 'multifilo_ui_integration',
    'ollama_runtime', 'orders_worker',
    'plc_connection_diagnostics', 'plc_db_size_probe', 'plc_db_write',
    'plc_map_decoder', 'plc_map_loader', 'plc_rust_bridge', 'plc_snap7_reader',
    'production_worker', 'quotations_worker',
    'rag_engine', 'rust_bridge', 'rust_worker',
    'server', 'session_manager',
    'snap7_lucidatrice_client', 'snap7_multifilo_client',
    'validazione_cnc', 'validazione_lucidatrice', 'validazione_multifilo',
    'waste_worker',
]


def project_package_modules(*folders):
    """Enumera tutti i moduli .py dei pacchetti progetto (esclusi i test)."""
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


hiddenimports = (
    root_modules
    + project_package_modules(
        'modules', 'ui', 'agents', 'fastapi_backend',
        'database', 'services', 'python_engine', 'python_app',
    )
    + [
        # Engine Rust compilato (site-packages)
        'rust_engine',
        # PLC
        'snap7',
        # AI / LLM
        'google.genai',
        # PyQt5
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.QtWebEngineWidgets',
        # Altri pacchetti runtime
        'PIL',
        'PIL.Image',
        'dotenv',
        'requests',
        'psutil',
        'fpdf',
        'fastapi',
        'uvicorn',
        'sqlite3',
        'multipart',
    ]
)

# ============================================================================
# BINARIES — DLL snap7 (sia da bin/ che dal wheel python-snap7)
# ============================================================================
binaries = []
snap7_dll = project_root / 'bin' / 'snap7.dll'
if snap7_dll.is_file():
    binaries.append((str(snap7_dll), '.'))
    binaries.append((str(snap7_dll), 'bin'))
binaries += collect_dynamic_libs('snap7')

# ============================================================================
# ANALISI
# ============================================================================
a = Analysis(
    [str(project_root / 'app' / 'nstone_main_window.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'customtkinter',
        'tkinter',
        'test',
        'tests',
        'unittest',
        'pydoc',
        'doctest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ============================================================================
# EXE — one-folder, layout flat (contents_directory='.') come la build storica:
# config.json, data/, modules/ ecc. finiscono accanto a NSTONELLM.exe
# ============================================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NSTONELLM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX disattivato: evita falsi positivi antivirus
    console=False,  # GUI mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NSTONELLM_App',
)

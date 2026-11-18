"""
Wrapper per avviare FastAPI Backend come eseguibile standalone
Accetta argomenti da riga di comando e li passa a uvicorn
"""

import sys
import os
import traceback
from pathlib import Path

# Determina il percorso base (directory dell'eseguibile)
if getattr(sys, 'frozen', False):
    # Eseguibile compilato con PyInstaller
    # sys._MEIPASS è la directory temporanea dove PyInstaller estrae i file
    # sys.executable è il percorso dell'eseguibile
    meipass_dir = Path(sys._MEIPASS)
    exe_dir = Path(sys.executable).parent
    
    # Aggiungi entrambi i percorsi
    sys.path.insert(0, str(meipass_dir))
    sys.path.insert(0, str(exe_dir))
    
    # Aggiungi anche fastapi_backend se esiste
    if (meipass_dir / "fastapi_backend").exists():
        sys.path.insert(0, str(meipass_dir / "fastapi_backend"))
    if (exe_dir / "fastapi_backend").exists():
        sys.path.insert(0, str(exe_dir / "fastapi_backend"))
    
    base_dir = exe_dir
    meipass_dir_str = str(meipass_dir)
else:
    # Script Python normale
    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))
    if (base_dir / "fastapi_backend").exists():
        sys.path.insert(0, str(base_dir / "fastapi_backend"))
    meipass_dir_str = "N/A"

# Importa uvicorn
try:
    import uvicorn
except ImportError as e:
    print("=" * 60)
    print("ERRORE: Impossibile importare uvicorn")
    print("=" * 60)
    print(f"Errore: {e}")
    print(f"sys.path: {sys.path}")
    print("=" * 60)
    input("Premi INVIO per chiudere...")
    sys.exit(1)

# Importa l'app FastAPI
app = None
try:
    from fastapi_backend.main import app
except ImportError as e1:
    try:
        from main import app
    except ImportError as e2:
        print("=" * 60)
        print("ERRORE: Impossibile importare l'app FastAPI")
        print("=" * 60)
        print(f"Tentativo 1 (fastapi_backend.main): {e1}")
        print(f"Tentativo 2 (main): {e2}")
        print(f"\nsys.path:")
        for p in sys.path:
            print(f"  - {p}")
        print(f"\nbase_dir: {base_dir}")
        if getattr(sys, 'frozen', False):
            print(f"meipass_dir: {meipass_dir_str}")
            print(f"sys.executable: {sys.executable}")
            print(f"sys._MEIPASS: {sys._MEIPASS}")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        input("Premi INVIO per chiudere...")
        sys.exit(1)

if app is None:
    print("=" * 60)
    print("ERRORE: app è None dopo l'importazione")
    print("=" * 60)
    input("Premi INVIO per chiudere...")
    sys.exit(1)

def main():
    """Avvia il server FastAPI con uvicorn"""
    try:
        # Argomenti di default
        host = "0.0.0.0"
        port = 8000
        reload = False
        
        # Parsa argomenti da riga di comando
        args = sys.argv[1:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--host" and i + 1 < len(args):
                host = args[i + 1]
                i += 2
            elif arg == "--port" and i + 1 < len(args):
                port = int(args[i + 1])
                i += 2
            elif arg == "--reload":
                reload = True
                i += 1
            else:
                i += 1
        
        print("=" * 60)
        print("Avvio FastAPI Backend")
        print("=" * 60)
        print(f"Host: {host}")
        print(f"Porta: {port}")
        print(f"Reload: {reload}")
        print(f"App: {app}")
        print("=" * 60)
        print("Premi Ctrl+C per fermare il server")
        print()
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=reload
        )
    except KeyboardInterrupt:
        print("\n\nServer fermato dall'utente")
    except Exception as e:
        print("=" * 60)
        print("ERRORE durante l'avvio del server")
        print("=" * 60)
        print(f"Errore: {e}")
        print()
        traceback.print_exc()
        print("=" * 60)
        input("Premi INVIO per chiudere...")
        sys.exit(1)

if __name__ == "__main__":
    main()


"""
Script di avvio rapido per NStone LLM (PyQt5).
Verifica le dipendenze principali e avvia l'applicazione.
"""
import io
import sys

# Configura encoding UTF-8 per evitare errori con emoji su console Windows
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except AttributeError:
        # stdout senza buffer (es. PyInstaller windowed mode)
        pass


def check_dependencies() -> bool:
    """Verifica che le dipendenze principali siano installate."""
    required = ["PyQt5", "PIL", "requests"]
    missing = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print("ERRORE: pacchetti mancanti:")
        for pkg in missing:
            print(f"   - {pkg}")
        print("\nInstalla le dipendenze con:")
        print("   pip install -r requirements.txt")
        return False

    print("OK: dipendenze principali installate")
    return True


def main() -> None:
    print("NStone LLM - Avvio applicazione...\n")

    if not check_dependencies():
        sys.exit(1)

    try:
        from app.nstone_main_window import main as app_main

        app_main()
    except Exception as exc:
        print(f"\nERRORE durante l'avvio: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

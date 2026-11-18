"""Verifica dipendenze minime per avvio GUI NSTONELLM. Exit 0 = OK."""
from __future__ import annotations

import importlib
import sys

_REQUIRED = (
    ("PyQt5", "PyQt5"),
    ("fpdf", "fpdf2"),
    ("psutil", "psutil"),
    ("requests", "requests"),
)


def main() -> int:
    missing = []
    for module, pip_name in _REQUIRED:
        try:
            importlib.import_module(module)
        except Exception as exc:
            missing.append((module, pip_name, str(exc)))
    if missing:
        print("DIPENDENZE MANCANTI:")
        for module, pip_name, err in missing:
            print(f"  - {module} (pip install {pip_name})  [{err}]")
        print("\nEsegui: python -m pip install -r requirements.txt")
        return 1
    print("Dipendenze desktop OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

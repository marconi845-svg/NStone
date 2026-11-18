"""
Copia runtime Ollama + un solo modello nella cartella build (USB portabile).

Uso:
  python scripts/bundle_ollama_for_build.py <APPDIR> [model_tag]

Default modello: qwen2.5:14b-instruct-q4_0
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DEFAULT_MODEL = "qwen2.5:14b-instruct-q4_0"
OLLAMA_INSTALL = Path.home() / "AppData" / "Local" / "Programs" / "Ollama"
OLLAMA_MODELS_SRC = Path.home() / ".ollama" / "models"


def _digest_to_blob_name(digest: str) -> str:
    d = digest.strip()
    if d.startswith("sha256:"):
        d = d[7:]
    return f"sha256-{d}"


def _collect_manifest_blobs(manifest_path: Path) -> set[str]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    blobs: set[str] = set()

    def add_digest(digest: str) -> None:
        blobs.add(_digest_to_blob_name(digest))

    cfg = data.get("config") or {}
    if cfg.get("digest"):
        add_digest(str(cfg["digest"]))

    for layer in data.get("layers") or []:
        if isinstance(layer, dict) and layer.get("digest"):
            add_digest(str(layer["digest"]))

    return blobs


def _manifest_path_for_model(model: str, models_root: Path) -> Path:
    name, _, tag = model.partition(":")
    if not tag:
        tag = "latest"
    return (
        models_root
        / "manifests"
        / "registry.ollama.ai"
        / "library"
        / name
        / tag
    )


def copy_model(model: str, src: Path, dst: Path) -> None:
    manifest = _manifest_path_for_model(model, src)
    if not manifest.is_file():
        raise FileNotFoundError(
            f"Manifest non trovato: {manifest}\n"
            f"Esegui prima: ollama pull {model}"
        )

    rel = manifest.relative_to(src / "manifests")
    dest_manifest = dst / "manifests" / rel
    dest_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest, dest_manifest)
    print(f"  Manifest: {rel}")

    src_blobs = src / "blobs"
    dst_blobs = dst / "blobs"
    dst_blobs.mkdir(parents=True, exist_ok=True)

    for blob_name in sorted(_collect_manifest_blobs(manifest)):
        src_blob = src_blobs / blob_name
        if not src_blob.is_file():
            raise FileNotFoundError(f"Blob mancante: {src_blob}")
        dst_blob = dst_blobs / blob_name
        size_gb = src_blob.stat().st_size / (1024**3)
        if dst_blob.exists() and dst_blob.stat().st_size == src_blob.stat().st_size:
            print(f"  Blob gia' presente: {blob_name} ({size_gb:.2f} GB)")
            continue
        print(f"  Copia blob {blob_name} ({size_gb:.2f} GB)...")
        shutil.copy2(src_blob, dst_blob)


def copy_runtime(install_dir: Path, dst_ollama: Path) -> None:
    exe = install_dir / "ollama.exe"
    lib = install_dir / "lib"
    if not exe.is_file():
        raise FileNotFoundError(
            f"ollama.exe non trovato in {install_dir}\n"
            "Installa Ollama da https://ollama.com"
        )
    if not lib.is_dir():
        raise FileNotFoundError(f"Cartella lib/ non trovata in {install_dir}")

    dst_ollama.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, dst_ollama / "ollama.exe")

    dst_lib = dst_ollama / "lib"
    if dst_lib.exists():
        shutil.rmtree(dst_lib)
    print("  Copia runtime Ollama (ollama.exe + lib/)...")
    shutil.copytree(lib, dst_lib)


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts/bundle_ollama_for_build.py <APPDIR> [model]")
        return 1

    app_dir = Path(sys.argv[1]).resolve()
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL

    if not app_dir.is_dir():
        print(f"[ERRORE] Cartella build non trovata: {app_dir}")
        return 1

    print("=" * 60)
    print(f"  Bundle Ollama portabile -> {app_dir}")
    print(f"  Modello: {model}")
    print("=" * 60)

    copy_runtime(OLLAMA_INSTALL, app_dir / "ollama")
    copy_model(model, OLLAMA_MODELS_SRC, app_dir / "models")

    print("=" * 60)
    print("  Bundle Ollama completato.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

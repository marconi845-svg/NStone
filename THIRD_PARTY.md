# Third-party components

NStone proprietary source is under [`LICENSE`](LICENSE) (**all rights reserved / source-available for viewing**).

Dependencies keep **their own** licenses. Do **not** vendor their binaries into this repository.

| Component | Used for | License / terms | In this repo? |
|-----------|----------|-----------------|---------------|
| **PyQt5** | Desktop GUI | **GPL v3** *or* Riverbank commercial | No — `requirements.txt` only |
| python-snap7 | Snap7 bindings | MIT (bindings) | No |
| Snap7 native (`snap7.dll`) | S7 PLC I/O | LGPL | **Not shipped** — see `bin/README.md` |
| FastAPI / Uvicorn / Pydantic | Local HTTP API | MIT / BSD-style | No |
| google-genai | Optional Gemini client | check package | No |
| fpdf2 / requests / psutil | PDF / HTTP / process | check package | No |
| ngrok | Optional tunnel | [ngrok ToS](https://ngrok.com/tos) | **Not shipped** |
| Ollama | Local LLM runtime | [Ollama terms](https://ollama.com) | **Not shipped** |

## PyQt5 / GPL — read this before redistributing

This repository is published so others can **read** the design. The `LICENSE` does **not** grant reuse rights.

**PyQt5 under GPL is viral for combined works.** If you:

- run or redistribute a binary that **links/imports PyQt5 under GPL**, and
- do not hold a **Riverbank commercial PyQt license**,

then GPL obligations may apply to the combined program (including offering corresponding source under GPL).

NStone’s proprietary `LICENSE` does **not** override PyQt5 GPL. Compatible options:

1. Obtain a **commercial PyQt license** from Riverbank for proprietary distribution; or  
2. Do not distribute PyQt-linked builds; keep this tree as **view-only** source; or  
3. Relicense *your* code under GPL-compatible terms (not current intent).

`python-snap7` / Snap7 LGPL: prefer **dynamic** linking to `snap7.dll`; do not statically merge Snap7 into proprietary binaries without LGPL compliance.

ngrok / Ollama: do not redistribute their installers inside NStone packs unless their current terms allow it.

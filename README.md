# NStone LLM

[![CI](https://github.com/marconi845-svg/NStone/actions/workflows/ci.yml/badge.svg)](https://github.com/marconi845-svg/NStone/actions/workflows/ci.yml)

**Status: public demo / private-beta product** — source is viewable; reuse requires a written license (see [`LICENSE`](LICENSE)).

Agentic OS for natural stone companies: office (requests, quotations, orders),
plant (multifilo, polisher, CNC via Snap7 **simulator** or live), and governance
(autonomy levels, fail-closed PLC writes, audit) in one local-first desktop app
with optional Ollama LLM.

## Hub

![NStone hub](assets/docs/hub-screenshot.jpg)

## Architecture

![NStone architecture](assets/docs/architecture.svg)

```mermaid
flowchart LR
  Hub[Desktop Hub / PyQt5] --> Office[Office pipelines]
  Hub --> Plant[Plant machines]
  Hub --> LLM[Local LLM / Ollama]
  Office --> DB[(SQLite audit)]
  Plant --> Gov[Write governor]
  Gov --> PLC[Snap7 PLC / sim]
  LLM --> Office
  LLM --> Plant
```

## Quick start

```bash
git clone https://github.com/marconi845-svg/NStone.git
cd NStone
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy config.json.example config.json
python run.py
```

On Windows you can also use `00_AVVIA_NSTONELLM.bat`.

### Config (do not commit secrets)

1. Copy `config.json.example` → `config.json`
2. Fill only what you need (Gmail app password, Gemini key, machine IPs)
3. **Never commit** `config.json`, `*.db`, `ngrok.exe`, or `bin/*.dll` — they are gitignored

Optional local LLM:

```bash
ollama pull qwen2.5:14b-instruct-q4_0
```

## Layout

| Path | Role |
|------|------|
| `app/` | Main window |
| `ui/` | PyQt windows |
| `modules/` | Orders, quotations, knowledge, pricing |
| `agents/` | Office/plant agent runtime |
| `core/` | Autonomy, config, governance |
| `plc/` | Snap7 helpers, write governor |
| `machines/` | Machine adapters |
| `llm/` | Ollama / Gemini services |
| `plc_maps/` | **Synthetic** demo DB maps only |
| `database/` | SQLite schema + seed (SQL only) |
| `data/` | Runtime DB (gitignored) + knowledge samples |
| `tests/` | Pytest suite |

## Tests / CI

```bash
python -m pytest tests/ -q
```

## Security

- Rotate any credentials that ever appeared outside a private machine
- PLC maps in this tree are **NStone-authored demos**, not OEM manuals
- FreeSWITCH lab password must be changed (`CHANGE_ME_SIP_PASSWORD`)

## License

**Proprietary — all rights reserved / view-only.** [`LICENSE`](LICENSE)  
Third-party (incl. **PyQt5 GPL** warning): [`THIRD_PARTY.md`](THIRD_PARTY.md)

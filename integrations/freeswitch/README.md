# FreeSWITCH integration (LAN)

## Windows — installazione rapida (NStone)

1. **Tasto destro** su `legacy\INSTALLA_FREESWITCH.bat` → **Esegui come amministratore**
2. Scarica (se serve) e installa **FreeSWITCH 1.10.12** MSI
3. Copia dialplan, Lua e utente SIP **2001**
4. Aggiorna `config.json` → `agentic_calling.freeswitch_path` e `sip_server`
5. Avvia servizio: `net start FreeSWITCH` oppure **services.msc**
6. Apri NStone → **Agentic Calling** (Voice Bridge)
7. Zoiper: utente **2001**, password **CHANGE_ME_SIP_PASSWORD**, server = IP LAN del PC, porta **5060**
8. Componi **2000** (Commercial)

Solo deploy config (FS già installato) — **Esegui come amministratore**:

```powershell
python tools\deploy_freeswitch_nstone.py
```

Oppure:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_freeswitch_windows.ps1 -SkipMsi
```

### Perché 2000 squilla 1000?

Il dialplan demo di FreeSWITCH definisce **2000 = gruppo sales** (utenti 1000–1004).  
MicroSIP registrato come **1000** riceve quella chiamata invece dell’agente Commercial.

Il deploy NStone:
- include `nstone_agentic.xml` **prima** delle regole demo
- disabilita `group_dial_sales` / `support` / `billing` su 2000/2001/2002

Dopo deploy: `fs_cli -x reloadxml` e ricomponi **2000**.

MSI manuale: `tools\cache\FreeSWITCH-1.10.12-Release-x64.msi` (scaricato dallo script)

---

Minimal dialplan + Lua script for NStone Voice Bridge.

## Prerequisites

1. FreeSWITCH listening on SIP port (default 5060)
2. NStone open on **Agentic Calling** (starts Voice Bridge on `127.0.0.1:8765`)
3. Optional: whisper.cpp and Piper paths in `config.json` → `agentic_calling`

## Install

Copy into your FreeSWITCH tree (or run `python tools/deploy_freeswitch_nstone.py` as Admin):

- `dialplan/nstone_agentic.xml` → `conf/dialplan/nstone_agentic.xml` (included first in `default.xml`)
- `scripts/agentic_call.lua` → `conf/scripts/agentic_call.lua`

Reload: `fs_cli -x "reloadxml"`

## Extensions

| Number | Agent |
|--------|--------|
| 1000 | Management |
| 2000 | Commercial |
| 3000 | Production |

Zoiper registers as a normal SIP user, then dials `1000`, `2000`, or `3000`.

## Voice Bridge API

```
GET  http://127.0.0.1:8765/health
POST http://127.0.0.1:8765/voice/turn
```

POST body (JSON):

```json
{
  "call_uuid": "optional-uuid",
  "extension_key": "commercial",
  "wav_in": "C:/path/to/recording.wav"
}
```

Response includes `text_in`, `text_out`, `wav_out` (when Piper is configured).

## Test without phone

```powershell
curl -X POST http://127.0.0.1:8765/voice/turn `
  -H "Content-Type: application/json" `
  -d "{\"extension_key\":\"commercial\",\"text_in\":\"Avete Carrara 2 cm?\"}"
```

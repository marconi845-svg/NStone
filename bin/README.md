# Native binaries

Native libraries are **not** versioned in git.

| Library | Purpose | How to obtain |
|---------|---------|---------------|
| `snap7.dll` (Windows x64) | Siemens S7 / Snap7 PLC sim/live | Build or download Snap7 (LGPL) and place `snap7.dll` here, or rely on the DLL shipped with the `python-snap7` install for your platform |
| `ngrok.exe` | Optional public tunnel | [ngrok.com/download](https://ngrok.com/download) — do not commit |

See `THIRD_PARTY.md` and root `LICENSE`.

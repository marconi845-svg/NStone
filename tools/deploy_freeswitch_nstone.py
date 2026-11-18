"""Deploy NStone Agentic Calling files into FreeSWITCH conf (no MSI)."""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FS_ROOT = Path(r"C:\Program Files\FreeSWITCH")
INTEGRATION = PROJECT_ROOT / "integrations" / "freeswitch"
RECORDINGS = Path(r"C:\freeswitch\recordings\agentic")
SCRIPTS = Path(r"C:\freeswitch\scripts")
CONFIG_PATH = PROJECT_ROOT / "config.json"

NSTONE_DIALPLAN_MARKER = "NSTONE: nstone_agentic.xml priority include"
NSTONE_GROUP_DISABLED_MARKER = "NStone disabled group_dial_sales"


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _patch_default_dialplan(default_xml: Path) -> None:
    """Load agentic extensions before stock demo rules (2000 -> sales group)."""
    text = default_xml.read_text(encoding="utf-8")
    changed = False

    if NSTONE_DIALPLAN_MARKER not in text:
        needle = '  <context name="default">\n'
        insert = (
            f'  <context name="default">\n'
            f'    <!-- {NSTONE_DIALPLAN_MARKER} -->\n'
            f'    <X-PRE-PROCESS cmd="include" data="nstone_agentic.xml"/>\n'
        )
        if needle not in text:
            raise SystemExit(f"Cannot patch {default_xml}: context default not found")
        text = text.replace(needle, insert, 1)
        changed = True
        print("Patched default.xml: nstone_agentic.xml included first")

    if NSTONE_GROUP_DISABLED_MARKER not in text:
        start = text.find('<extension name="group_dial_sales">')
        billing_pos = text.find('<extension name="group_dial_billing">')
        if start != -1 and billing_pos != -1:
            end = text.find("</extension>", billing_pos)
            if end != -1:
                end += len("</extension>")
                block = text[start:end]
                commented = (
                    f"    <!-- {NSTONE_GROUP_DISABLED_MARKER} (2000/2001/2002 = NStone agents) -->\n"
                    f"    <!--\n{block}\n    -->"
                )
                text = text[:start] + commented + text[end:]
                changed = True
                print("Patched default.xml: disabled stock group_dial_sales/support/billing")

    if changed:
        default_xml.write_text(text, encoding="utf-8")


def _patch_public_dialplan(public_xml: Path) -> None:
    marker = "NSTONE: nstone_agentic.xml public include"
    text = public_xml.read_text(encoding="utf-8")
    if marker in text:
        return
    needle = '  <context name="public">\n'
    insert = (
        f'  <context name="public">\n'
        f'    <!-- {marker} -->\n'
        f'    <X-PRE-PROCESS cmd="include" data="nstone_agentic.xml"/>\n'
    )
    if needle not in text:
        return
    public_xml.write_text(text.replace(needle, insert, 1), encoding="utf-8")
    print("Patched public.xml: nstone_agentic.xml included first")


def deploy() -> None:
    conf = FS_ROOT / "conf"
    if not conf.is_dir():
        raise SystemExit(f"FreeSWITCH not found at {FS_ROOT}")

    RECORDINGS.mkdir(parents=True, exist_ok=True)
    SCRIPTS.mkdir(parents=True, exist_ok=True)

    lua_src = INTEGRATION / "scripts" / "agentic_call.lua"
    helper_src = INTEGRATION / "scripts" / "voice_turn_post.py"
    shutil.copy2(lua_src, SCRIPTS / "agentic_call.lua")
    shutil.copy2(helper_src, SCRIPTS / "voice_turn_post.py")
    print(f"Deployed Lua -> {SCRIPTS / 'agentic_call.lua'}")

    shutil.copy2(
        INTEGRATION / "dialplan" / "nstone_agentic.xml",
        conf / "dialplan" / "nstone_agentic.xml",
    )
    legacy_agentic = conf / "dialplan" / "default" / "01_agentic.xml"
    if legacy_agentic.is_file():
        legacy_agentic.unlink()
        print("Removed legacy default/01_agentic.xml (superseded by nstone_agentic.xml)")

    fs_scripts = conf.parent / "scripts"
    try:
        fs_scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lua_src, fs_scripts / "agentic_call.lua")
        print(f"Deployed Lua -> {fs_scripts / 'agentic_call.lua'}")
    except OSError as exc:
        print(f"Skip Program Files scripts (no admin?): {exc}")
    shutil.copy2(
        INTEGRATION / "directory" / "2001.xml",
        conf / "directory" / "default" / "2001.xml",
    )

    default_xml = conf / "dialplan" / "default.xml"
    if default_xml.is_file():
        _patch_default_dialplan(default_xml)

    public_xml = conf / "dialplan" / "public.xml"
    if public_xml.is_file():
        _patch_public_dialplan(public_xml)

    print("Deployed dialplan, Lua, SIP user 2001")

    fs_cli = FS_ROOT / "fs_cli.exe"
    if fs_cli.is_file():
        try:
            subprocess.run(
                [str(fs_cli), "-x", "reloadxml"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            print("Sent reloadxml to FreeSWITCH")
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"reloadxml skipped ({exc})")

    sip_host = _lan_ip()
    agentic = {
        "enabled": True,
        "mode": "lan",
        "sip_server": sip_host,
        "sip_port": 5060,
        "freeswitch_path": str(fs_cli),
        "voice_bridge_host": "127.0.0.1",
        "voice_bridge_port": 8765,
        "voice_bridge_auto_start": True,
        "recordings_dir": str(RECORDINGS),
    }

    if CONFIG_PATH.is_file():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
        current = data.get("agentic_calling")
        if isinstance(current, dict):
            current.update(agentic)
            data["agentic_calling"] = current
        else:
            data["agentic_calling"] = agentic
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated config.json (sip_server={sip_host}, freeswitch_path={fs_cli})")
    else:
        print("config.json missing - add agentic_calling block manually")


if __name__ == "__main__":
    deploy()

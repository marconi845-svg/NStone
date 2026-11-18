"""
Smoke test headless del pannello proposte governate nella finestra CNC.

Non chiama il modello: inietta risposte canned in on_write_intent_ready e
verifica parser → anteprima governor → approvazione operatore (shadow).
Qt gira in modalità offscreen.

Uso:  python tests/smoke_write_proposal_ui.py
"""

import os
import sys
from enum import Enum
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox


class FakeState(Enum):
    RUN = "RUN"


class FakeSimStatus:
    """Solo i campi usati da _governor_status (mai inventare il resto)."""
    machine_state = FakeState.RUN
    feed_rate_override = 100.0


def main() -> int:
    app = QApplication(sys.argv)

    import ui.windows.machines.gestione_cnc_window as win_mod

    # Niente RAG engine reale nello smoke test
    win_mod.GestioneCNCWindow.get_rag_engine = classmethod(lambda cls: None)
    window = win_mod.GestioneCNCWindow()
    window._current_cnc_status = FakeSimStatus()

    failures = []

    def expect(cond, label):
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures.append(label)

    # --- 1. Proposta valida: anteprima ok, Approve abilitato -------------
    window.on_write_intent_ready(
        '{"action": "write", "variable": "cmd_feed_override", '
        '"value": 92.0, "reason": "spindle load high", "urgency": "normal"}'
    )
    text = window.proposal_text.toPlainText()
    expect("WRITABLE pending operator approval" in text, "proposta valida → anteprima ok")
    expect(window.approve_write_button.isEnabled(), "Approve abilitato su proposta valida")

    # --- 2. Approvazione operatore (QMessageBox → Yes), shadow -----------
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    window.on_approve_write()
    text = window.proposal_text.toPlainText()
    expect("APPROVED BY OPERATOR" in text, "approvazione registrata")
    expect("SHADOW" in text, "esito dichiara shadow mode")
    expect(not window.approve_write_button.isEnabled(), "Approve disabilitato dopo l'uso")

    # --- 3. Fuori range: rifiutata, Approve resta spento -----------------
    window.on_write_intent_ready(
        '{"action": "write", "variable": "cmd_feed_override", '
        '"value": 300.0, "reason": "go faster"}'
    )
    text = window.proposal_text.toPlainText()
    expect("VERDICT: REJECTED" in text, "fuori range → rifiutata")
    expect("range" in text, "check range mostrato")
    expect(not window.approve_write_button.isEnabled(), "Approve spento su rifiuto")

    # --- 4. Output non conforme: fermato dal parser -----------------------
    window.on_write_intent_ready("Certo! Ti consiglio di aumentare il feed del 20%.")
    text = window.proposal_text.toPlainText()
    expect("REJECTED BY PARSER" in text, "prosa senza JSON → parser blocca")

    # --- 5. action=none ----------------------------------------------------
    window.on_write_intent_ready('{"action": "none", "reason": "all nominal"}')
    text = window.proposal_text.toPlainText()
    expect("PROPOSES NO CHANGE" in text, "action=none gestita")

    # --- 6. Audit su DB -----------------------------------------------------
    from modules.action_store import list_recent_audit
    rows = [r for r in list_recent_audit(10)
            if r["action"] in ("plc_write", "plc_write_proposal")]
    expect(len(rows) >= 4, f"audit registrato su DB ({len(rows)} righe recenti)")

    window.close()
    app.quit()
    print()
    if failures:
        print(f"SMOKE TEST FALLITO: {failures}")
        return 1
    print("SMOKE TEST OK: pannello proposte governate funzionante (shadow).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

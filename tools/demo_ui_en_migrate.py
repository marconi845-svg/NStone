"""One-off migration: English labels + SectionDialog for demo."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "ui" / "windows"

COMMON = [
    ('setWindowTitle("Centro Ordini")', 'setWindowTitle("Order Center")'),
    ('setWindowTitle("📋 Centro Ordini Produzione")', 'setWindowTitle("📋 Production Order Center")'),
    ('setWindowTitle("Impostazioni Sistema")', 'setWindowTitle("System Settings")'),
    ('setWindowTitle("🏭 Gestione Multifilo")', 'setWindowTitle("🏭 Multifilo Management")'),
    ('setWindowTitle("🔧 Gestione Lucidatrice/Calibratrice")', 'setWindowTitle("🔧 Polisher / Calibrator Management")'),
    ('setWindowTitle("⚙️ Gestione CNC Universale")', 'setWindowTitle("⚙️ Universal CNC Management")'),
    ('setWindowTitle("💧 Gestione Fanghi — Depurazione")', 'setWindowTitle("💧 Sludge Treatment")'),
    ('setWindowTitle("💡 Suggerimenti Operativi — Multifilo")', 'setWindowTitle("💡 Operational Insights — Multifilo")'),
    ('setWindowTitle("💡 Suggerimenti Operativi — Lucidatrice/Calibratrice")', 'setWindowTitle("💡 Operational Insights — Polisher")'),
    ('setWindowTitle("💡 Suggerimenti Operativi — CNC")', 'setWindowTitle("💡 Operational Insights — CNC")'),
    ('setWindowTitle("Esporta Analisi")', 'setWindowTitle("Export Analysis")'),
    ('setWindowTitle(f"Dettaglio Ordine', 'setWindowTitle(f"Order Details'),
    ('setWindowTitle(f"Dettaglio Richiesta")', 'setWindowTitle("Request Details")'),
    ('setWindowTitle(f"📋 Ordini in Arrivo / Produzione', 'setWindowTitle(f"📋 Incoming / Production Orders'),
    ('"Nuovo prodotto"', '"New product"'),
    ('"Modifica prodotto"', '"Edit product"'),
    ('QPushButton("+ Nuovo")', 'QPushButton("+ New")'),
    ('QPushButton("Modifica")', 'QPushButton("Edit")'),
    ('QPushButton("Elimina")', 'QPushButton("Delete")'),
    ('QPushButton("Aggiorna")', 'QPushButton("Refresh")'),
    ('QPushButton("Aggiorna dati")', 'QPushButton("Refresh data")'),
    ('QLabel("Ordini Ricevuti")', 'QLabel("Received Orders")'),
    ('QLabel("Ordini Inviati")', 'QLabel("Sent Orders")'),
    ('QLabel("Centro Ordini")', 'QLabel("Order Center")'),
    ('"Carica ordine"', '"Load order"'),
    ('"Analisi AI"', '"AI Analysis"'),
    ('"Genera G-code"', '"Generate G-code"'),
    ('"Invia alla macchina"', '"Send to machine"'),
    ('"Ordini in Arrivo / Produzione"', '"Incoming / Production Orders"'),
    ('"Gestione Richieste"', '"Request Management"'),
    ('"Elabora con Gemini"', '"Process with Gemini"'),
    ('"Dettaglio Richiesta"', '"Request Details"'),
    ('"💧 Gestione Fanghi — Depurazione"', '"💧 Sludge Treatment"'),
    ('"🔧 Gestione Lucidatrice/Calibratrice"', '"🔧 Polisher / Calibrator Management"'),
    ('"🏭 Gestione Multifilo"', '"🏭 Multifilo Management"'),
    ('"Aggiorna lista ordini"', '"Refresh order list"'),
    ('"Aggiorna Ultimo Ordine"', '"Refresh latest order"'),
    ('"Elimina selezionati"', '"Delete selected"'),
    ('"Refresh Ordini Inviati"', '"Refresh sent orders"'),
    ('"Stato Gmail (Ordini)"', '"Gmail status (Orders)"'),
    ('"Aggiorna Stato Servizi"', '"Refresh services status"'),
    ('"Aggiorna stato monitor"', '"Refresh monitor status"'),
    ('"Pulisci elaborate"', '"Clear processed"'),
    ('"Cerca prodotti..."', '"Search products..."'),
    ('"Salvato"', '"Saved"'),
    ('"Eliminato"', '"Deleted"'),
    ('"Errore"', '"Error"'),
    ('"Selezione"', '"Selection"'),
    ('"Solo lettura"', '"Read only"'),
    ('"Conferma eliminazione"', '"Confirm deletion"'),
    ('QPushButton("➕ Crea Nuova Richiesta")', 'QPushButton("➕ New Request")'),
    ('QGroupBox("Ordini produzione")', 'QGroupBox("Production orders")'),
    ('QGroupBox("Ordini Inviati alle Macchine")', 'QGroupBox("Orders sent to machines")'),
    ('QLabel("📋 Centro Ordini Produzione")', 'QLabel("📋 Production Order Center")'),
    ('QGroupBox(f"Ordini inviati al {nome_macchina}")', 'QGroupBox(f"Orders sent to {nome_macchina}")'),
    ('QLabel(f"📋 Ordini in Arrivo / Produzione — {self.nome_macchina}")', 'QLabel(f"📋 Incoming / Production Orders — {self.nome_macchina}")'),
    ('QGroupBox(f"Ordini ricevuti da {self.nome_macchina}")', 'QGroupBox(f"Orders received by {self.nome_macchina}")'),
    ('QLabel("Ordini: 0")', 'QLabel("Orders: 0")'),
    ('setText(f"Ordini: {len(self.ordini_ricevuti)}")', 'setText(f"Orders: {len(self.ordini_ricevuti)}")'),
    ('QPushButton("📋 Ordini in Arrivo / Produzione")', 'QPushButton("📋 Incoming / Production Orders")'),
    ('"Elimina ordine"', '"Delete order"'),
    ('"Ordini"', '"Orders"'),
    ('"Analisi completata"', '"Analysis complete"'),
    ('"Analisi AI già in corso…"', '"AI analysis already running…"'),
    ('QLabel("Gestione chiamate VoIP e servizio Asterisk")', 'QLabel("VoIP calls and Asterisk service management")'),
    ('"Motore neurale locale"', '"Local neural engine"'),
    ('"Aggiorna dati"', '"Refresh data"'),
    ('"In attesa"', '"Waiting"'),
    ('"In esecuzione"', '"Running"'),
    ('"Stop inviato all\'inferenza in corso."', '"Stop sent to running inference."'),
    ('"Nessuna inferenza attiva da fermare."', '"No active inference to stop."'),
    ('"Scarico modelli dalla VRAM…"', '"Unloading models from VRAM…"'),
]

DIALOG_CLASSES = [
    "OnlineStockWindow", "AgentsCommandCenterWindow", "SuggerimentiMultifiloWindow",
    "SuggerimentiLucidatriceWindow", "GestioneMultifiloWindow", "GestioneLucidatriceWindow",
    "RequestDetailWindow", "AdministrationWindow", "SettingsWindow", "OrdersWindow",
    "QuotationsHubWindow", "DatabaseWindow", "SuggerimentiCNCWindow", "CollectionsWindow",
    "RAGMemoryViewer", "RAGEngineWindow", "DettaglioOrdineWindow", "CreditsWindow",
    "CallCenterWindow", "ProductionWindow", "QuotationsWindow", "OnlineStockEditDialog",
    "ExportAnalysisDialog",
]
MAIN_CLASSES = [
    "GestioneFanghiWindow", "GestioneCNCWindow", "CentroOrdiniProduzioneWindow",
    "OrdiniMacchinaWindow", "MachinesMonitoringWindow", "PrivacySecurityCenterWindow",
]


def _patch_datetime(text: str) -> str:
    marker = '"""Aggiorna la data e ora in formato italiano"""'
    if marker not in text:
        return text
    import re

    pattern = re.compile(
        r"def update_datetime\(self\):\s*"
        r'"""Aggiorna la data e ora in formato italiano"""\s*'
        r"now = datetime\.now\(\).*?"
        r'self\.datetime_label\.setText\(datetime_str\)',
        re.DOTALL,
    )
    replacement = (
        "def update_datetime(self):\n"
        '        """Update header date/time (English)."""\n'
        "        self.datetime_label.setText(format_header_datetime())"
    )
    if "format_header_datetime" not in text:
        text = text.replace(
            "from datetime import datetime",
            "from datetime import datetime\nfrom ui.common.datetime_ui import format_header_datetime",
            1,
        )
    return pattern.sub(replacement, text)


def migrate() -> list[str]:
    changed: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        orig = text
        if "section_window import" not in text and "from PyQt5.QtWidgets import" in text:
            text = text.replace(
                "from PyQt5.QtWidgets import",
                "from ui.common.section_window import SectionDialog, SectionMainWindow\nfrom PyQt5.QtWidgets import",
                1,
            )
        for old, new in COMMON:
            text = text.replace(old, new)
        for cls in DIALOG_CLASSES:
            text = text.replace(f"class {cls}(QDialog):", f"class {cls}(SectionDialog):")
        for cls in MAIN_CLASSES:
            text = text.replace(f"class {cls}(QMainWindow):", f"class {cls}(SectionMainWindow):")
        text = _patch_datetime(text)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed.append(str(path.relative_to(ROOT.parent.parent)))
    return changed


if __name__ == "__main__":
    files = migrate()
    print(f"Updated {len(files)} files")
    for f in files:
        print(f)

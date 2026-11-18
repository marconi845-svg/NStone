"""
Pulizia database nella BUILD (mai quello di sviluppo).

Svuota le tabelle transazionali (offerte, ordini, email, richieste, audit)
accumulate nei mesi di test, mantenendo i dati master/demo:
stock, listino manodopera, knowledge base, utenti, password sezioni, compliance.

Uso (chiamato da BUILD.bat dopo la copia dei datas):
  python scripts/prepare_clean_db_for_build.py <APPDIR>\\data\\nstonellm.db
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Tabelle da SVUOTARE: dati operativi/test accumulati
TRANSACTIONAL_TABLES = [
    "email_logs",
    "incoming_request",
    "quotations",
    "quotation_email_turn",
    "orders",
    "invoices",
    "autonomy_audit",
    "agent_messages",
    "pending_actions",
    "knowledge_retrieval_log",
    "rag_memory",
    "material_assets",
    "material_location_events",
    "compliance_worker_ack",
]

# Tabelle MANTENUTE (documentazione, non toccate dallo script):
#   online_stock, pricing_labor, knowledge_documents, knowledge_chunks,
#   app_user, section_password, compliance_checklist, compliance_profile,
#   administration, collection, production  (seed demo per dashboard)


def clean_database(db_path: Path) -> int:
    if not db_path.is_file():
        print(f"[ERRORE] Database non trovato: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        total_removed = 0
        for table in TRANSACTIONAL_TABLES:
            if table not in existing:
                print(f"  - {table}: assente, skip")
                continue
            (count,) = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
            conn.execute(f'DELETE FROM "{table}"')
            # Reset autoincrement (la tabella sqlite_sequence esiste se c'è
            # almeno una colonna AUTOINCREMENT nel DB)
            if "sqlite_sequence" in existing:
                conn.execute(
                    "DELETE FROM sqlite_sequence WHERE name = ?", (table,)
                )
            total_removed += count
            print(f"  - {table}: rimosse {count} righe")

        conn.commit()
        conn.execute("VACUUM")
        print(f"\nTotale righe di test rimosse: {total_removed}")
    finally:
        conn.close()

    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts/prepare_clean_db_for_build.py <path db build>")
        return 1

    db_path = Path(sys.argv[1]).resolve()

    # Guardia: rifiuta di pulire il DB di sviluppo nel repo
    project_db = Path(__file__).resolve().parents[1] / "data" / "nstonellm.db"
    if db_path == project_db:
        print("[ERRORE] Questo script pulisce SOLO la copia nella build,")
        print(f"         non il database di sviluppo: {project_db}")
        return 1

    print("=" * 60)
    print(f"  Pulizia dati di test -> {db_path}")
    print("=" * 60)
    return clean_database(db_path)


if __name__ == "__main__":
    raise SystemExit(main())

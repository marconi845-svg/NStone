"""Manual smoke test — Retrieval Fabric UI + backend (run: python tools/smoke_retrieval_fabric.py)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE = """# Smoke test listino

## Lucido 2 cm
Prezzo: 85.00 EUR/m² per Carrara CD lucido spessore 2 cm.
"""


def test_backend(tmp_dir: Path) -> None:
    from modules import knowledge_db as kdb
    from modules import knowledge_ingest as ingest
    from modules import knowledge_retriever as retr
    from modules import knowledge_audit_db as audit

    db = tmp_dir / "test.db"
    knowledge = tmp_dir / "knowledge"
    knowledge.mkdir()

    orig_get_db = kdb.get_database_path
    orig_root = kdb.KNOWLEDGE_ROOT
    orig_ingest = ingest.get_database_path
    orig_retr = retr.get_database_path
    orig_audit = audit.get_database_path
    try:
        kdb.get_database_path = lambda: db  # type: ignore[method-assign]
        kdb.KNOWLEDGE_ROOT = knowledge
        ingest.get_database_path = lambda: db  # type: ignore[method-assign]
        retr.get_database_path = lambda: db  # type: ignore[method-assign]
        audit.get_database_path = lambda: db  # type: ignore[method-assign]

        kdb.init_knowledge_tables(db)
        md = knowledge / "smoke_listino.md"
        md.write_text(SAMPLE, encoding="utf-8")
        r = ingest.index_file(md, copy_to_knowledge_root=False)
        assert r["status"] == "indexed", r

        hits = retr.retrieve("Prezzo Carrara lucido 2 cm", limit=3)
        assert hits, "no retrieval hits"
        assert "85" in hits[0]["content"] or "Carrara" in hits[0]["content"]

        audit.log_retrieval(
            question="Prezzo Carrara lucido 2 cm",
            hits=hits,
            answer_preview="smoke",
        )
        assert audit.list_logs(limit=1)
    finally:
        kdb.get_database_path = orig_get_db
        kdb.KNOWLEDGE_ROOT = orig_root
        ingest.get_database_path = orig_ingest
        retr.get_database_path = orig_retr
        audit.get_database_path = orig_audit

    print("[OK] backend ingest + retrieve + audit")


def test_ui() -> None:
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from ui.windows.ai.retrieval_fabric_window import RetrievalFabricWindow
    from ui.windows.ai.knowledge_library_widget import KnowledgeLibraryWidget
    from ui.windows.ai.knowledge_query_widget import KnowledgeQueryWidget
    from ui.windows.ai.knowledge_sources_widget import KnowledgeSourcesWidget
    from ui.windows.ai.knowledge_settings_widget import KnowledgeSettingsWidget

    win = RetrievalFabricWindow()
    assert win.stats_banner.text()
    assert win.footer_label.text()
    assert win.tabs.count() == 4

    for i in range(win.tabs.count()):
        w = win.tabs.widget(i)
        assert w is not None
        assert isinstance(
            w,
            (
                KnowledgeLibraryWidget,
                KnowledgeQueryWidget,
                KnowledgeSourcesWidget,
                KnowledgeSettingsWidget,
            ),
        )

    win.library_tab.refresh()
    win.sources_tab.refresh()
    win.settings_tab.refresh()
    print("[OK] UI window + 4 tabs instantiate")


def main() -> int:
    test_ui()
    with tempfile.TemporaryDirectory() as td:
        test_backend(Path(td))
    print("\n=== Retrieval Fabric smoke: ALL PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

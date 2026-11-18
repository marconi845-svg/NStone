"""
Retrieval Fabric — domain knowledge center (MD listini, procedure, cataloghi).
Sostituisce Logistic in hub.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionMainWindow
from ui.windows.ai.knowledge_library_widget import KnowledgeLibraryWidget
from ui.windows.ai.knowledge_query_widget import KnowledgeQueryWidget
from ui.windows.ai.knowledge_settings_widget import KnowledgeSettingsWidget
from ui.windows.ai.knowledge_sources_widget import KnowledgeSourcesWidget

from llm.llm_service import load_llm_config, ui_model_label_from_config
from modules.knowledge_db import init_knowledge_tables
from modules.knowledge_ingest import stats_summary


class RetrievalFabricWindow(SectionMainWindow):
    """Hub section: Library · Ask · Sources · Settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Retrieval Fabric")
        init_knowledge_tables()
        self._setup_window_size()
        self.init_ui()
        self.apply_stylesheet()
        self._stats_timer = QTimer(self)
        self.manage_section_timer(self._stats_timer, 5000)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._refresh_stats()

    def _setup_window_size(self) -> None:
        from ui.common.window_helpers import default_window_geometry, ensure_resizable_window

        ensure_resizable_window(self, min_width=1280, min_height=820)
        default_window_geometry(self)

    def init_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._create_header())

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab {
                background: #1a1a2a; color: #ccc; padding: 10px 18px;
                border: 1px solid #2a2a3a; border-bottom: none; margin-right: 4px;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
            }
            QTabBar::tab:selected { background: #2a1a3a; color: #fff; }
            """
        )
        self.library_tab = KnowledgeLibraryWidget(on_stats_changed=self._refresh_stats)
        self.ask_tab = KnowledgeQueryWidget(on_logged=self._refresh_sources)
        self.sources_tab = KnowledgeSourcesWidget()
        self.settings_tab = KnowledgeSettingsWidget()

        self.tabs.addTab(self.library_tab, "Library")
        self.tabs.addTab(self.ask_tab, "Ask")
        self.tabs.addTab(self.sources_tab, "Sources")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 16)
        content_layout.addWidget(self.tabs, 1)
        layout.addWidget(content, 1)
        layout.addWidget(self._create_footer())
        self.setCentralWidget(container)

    def _create_header(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(84)
        frame.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
            """
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(28, 12, 28, 12)
        title = QLabel("Retrieval Fabric")
        title.setStyleSheet("color: #fff; font-size: 24px; font-weight: bold;")
        row.addWidget(title)
        row.addStretch()
        self.stats_banner = QLabel()
        self.stats_banner.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.stats_banner.setStyleSheet("color: #c8a8e8; font-size: 11px; font-weight: bold;")
        row.addWidget(self.stats_banner)
        return frame

    def _create_footer(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(40)
        frame.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
            """
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(20, 8, 20, 8)
        self.footer_label = QLabel()
        self.footer_label.setStyleSheet("color: #aaa; font-size: 11px;")
        row.addWidget(self.footer_label)
        return frame

    def _refresh_stats(self) -> None:
        stats = stats_summary()
        model = ui_model_label_from_config(load_llm_config())
        banner = (
            f"{stats['documents']} docs · {stats['chunks']} chunks · {model}"
        )
        if hasattr(self, "stats_banner"):
            self.stats_banner.setText(banner)
        if hasattr(self, "footer_label"):
            self.footer_label.setText(
                f"{format_header_datetime()} · Knowledge base local · Retrieval Fabric"
            )
        if hasattr(self, "settings_tab"):
            self.settings_tab.refresh()

    def _refresh_sources(self) -> None:
        if hasattr(self, "sources_tab"):
            self.sources_tab.refresh()

    def open_ask_with_question(self, question: str) -> None:
        """Apre tab Ask con domanda precompilata (es. da Quotations Hub)."""
        text = (question or "").strip()
        self.tabs.setCurrentWidget(self.ask_tab)
        if text:
            self.ask_tab.set_input_text(text)
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) == "Ask":
            try:
                from modules.ollama_prewarm import request_lazy_prewarm

                request_lazy_prewarm(reason="retrieval_fabric_ask")
            except Exception:
                pass
        elif self.tabs.tabText(index) == "Library":
            self.library_tab.refresh()
        elif self.tabs.tabText(index) == "Sources":
            self.sources_tab.refresh()
        elif self.tabs.tabText(index) == "Settings":
            self.settings_tab.refresh()

    def on_section_shown(self) -> None:
        self._refresh_stats()
        self.library_tab.refresh()

    def apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
            QLabel { color: #FFFFFF; }
            """
        )

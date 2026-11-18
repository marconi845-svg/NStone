"""
Nstone LLM - Finestra Quotations Hub
Gestione richieste preventivo (SQLite) e help neurale
"""
import os
import sys
import csv
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from ui.common.window_helpers import (
    ensure_resizable_window,
    show_auxiliary_window,
    resolve_dashboard,
    show_section_window,
)
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTableView,
                             QLineEdit, QHeaderView, QProgressBar, QScrollArea,
                             QMessageBox, QTextEdit, QStackedWidget, QComboBox, QButtonGroup)
from PyQt5.QtCore import (
    Qt, QTimer, QSortFilterProxyModel, QAbstractTableModel, QModelIndex,
    QThread, pyqtSignal, QItemSelectionModel,
)
try:
    from PyQt5.QtCore import QRegularExpression
    HAS_QREGULAREXPRESSION = True
except ImportError:
    from PyQt5.QtCore import QRegExp
    HAS_QREGULAREXPRESSION = False
from PyQt5.QtGui import QFont, QColor, QBrush, QStandardItemModel, QStandardItem
import subprocess
import platform
from llm.ai_assistant import AIAssistant
from ui.common.neural_stats_sidebar import NeuralStatsPollWorker, apply_neural_stats_to_labels
from ui.theme.quotations_theme import (
    BTN_FILTER,
    BTN_FILTER_TECH,
    STATUS_ERR,
    STATUS_OK,
    TEXT_MUTED,
    TEXT_SECONDARY,
    TEXT_SUBTITLE_OK,
    apply_button_role,
    configure_email_table,
    configure_requests_table,
    is_technical_stato,
    request_type_badge,
    status_dot_color,
)
from ui.common.worker_lifecycle import (
    QUOTATIONS_WORKER_ATTRS,
    is_ui_active,
    wait_workers,
    wire_worker,
)
from ui.common.hub_column_splitter import (
    create_hub_three_column_splitter,
    collapse_hub_center_column,
    expand_hub_center_column,
    schedule_hub_splitter_collapsed,
    hub_side_toolbar_spacer,
    HUB_SIDE_FOOTER_HEIGHT,
)

# Import SQL Databaser (consulta / modifica DB)
try:
    from ui.windows.admin.database_window import DatabaseWindow
    HAS_DATABASE_WINDOW = True
except ImportError:
    HAS_DATABASE_WINDOW = False
    DatabaseWindow = None  # type: ignore

# Import finestra dettaglio richiesta
try:
    from ui.windows.common.request_detail_window import (
        RequestDetailWindow,
        RequestWorker,
        _http_timeout_for_elabora,
    )
    HAS_REQUEST_DETAIL_WINDOW = True
except ImportError:
    HAS_REQUEST_DETAIL_WINDOW = False
    RequestDetailWindow = None  # type: ignore
    RequestWorker = None  # type: ignore
    _http_timeout_for_elabora = lambda: 225  # type: ignore
    print("Warning: request_detail_window non trovato")

try:
    from ui.windows.quotations.quotation_request_detail_dialog import (
        QuotationRequestDetailDialog,
    )
    HAS_QUOTATION_DETAIL_DIALOG = True
except ImportError:
    HAS_QUOTATION_DETAIL_DIALOG = False
    QuotationRequestDetailDialog = None  # type: ignore

_MATERIAL_KEYWORDS = (
    "marmo", "marble", "granito", "granite", "travertino", "travertine",
    "calacatta", "carrara", "quartzite", "quarzo", "quartz", "onyx",
    "lastra", "lastre", "slab", "blocco", "block", "piastrella", "ardesia",
    "porfido", "limestone", "pietra", "stone",
)


class SentEmailDetailDialog(SectionDialog):
    """Sent Email Details (log JSON o record richiesta SQLite)."""

    def __init__(self, email_record: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sent Email")
        self.setMinimumSize(620, 480)
        self._record = email_record or {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Sent Email Details")
        title.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        meta = QLabel(self._meta_line())
        meta.setWordWrap(True)
        meta.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        layout.addWidget(meta)

        for label_text, key, max_h in (
            ("Oggetto", "subject", 48),
            ("Corpo", "body", None),
        ):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
            layout.addWidget(lbl)
            field = QTextEdit()
            field.setReadOnly(True)
            if max_h:
                field.setMaximumHeight(max_h)
            field.setPlainText(self._field_text(key))
            field.setStyleSheet("""
                QTextEdit {
                    background-color: #0a0a1a; color: #E8E8E8;
                    border: 1px solid #2a2a3a; border-radius: 6px; padding: 8px;
                    font-size: 12px;
                }
            """)
            layout.addWidget(field, 1 if key == "body" else 0)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a; color: #fff; border-radius: 6px;
                padding: 10px 24px; font-weight: bold;
            }
            QPushButton:hover { background-color: #5a3a7a; }
        """)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

        self.setStyleSheet("QDialog { background-color: #0a0a15; }")

    def _meta_line(self) -> str:
        r = self._record
        parts = [
            f"A: {r.get('to') or '—'}",
            f"Quando: {r.get('timestamp') or '—'}",
        ]
        status = r.get("status")
        if status:
            parts.append(f"Stato: {status}")
        src = r.get("source")
        if src:
            parts.append(f"Fonte: {src}")
        return " · ".join(parts)

    def _field_text(self, key: str) -> str:
        r = self._record
        if key == "subject":
            return str(r.get("subject") or r.get("summary") or "—")
        body = r.get("body") or r.get("summary") or r.get("message") or ""
        return str(body).strip() or "—"


class QuotationsTableModel(QAbstractTableModel):
    """Model per la tabella quotations con dati da CSV"""

    def __init__(
        self,
        data,
        headers,
        parent=None,
        row_colors=None,
        row_tooltips=None,
        row_badge_labels=None,
        row_badge_colors=None,
    ):
        super().__init__(parent)
        self._data = data
        self._headers = headers
        self.table_data = data  # Alias per compatibilità con codice esistente
        self._row_colors = row_colors or {}
        self._row_tooltips = row_tooltips or {}
        self._row_badge_labels = row_badge_labels or {}
        self._row_badge_colors = row_badge_colors or {}

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.DisplayRole:
            row = index.row()
            col = index.column()
            if row < len(self._data) and col < len(self._headers):
                if col == 0:
                    label = self._row_badge_labels.get(row, "ORDINE")
                    return f"[{label}]"
                return str(self._data[row][col])

        if role == Qt.FontRole and index.column() == 0:
            font = QFont()
            font.setBold(True)
            font.setPointSize(9)
            return font

        if role == Qt.ForegroundRole:
            if index.column() == 0:
                color = self._row_badge_colors.get(index.row())
                if color:
                    return QBrush(QColor(color))
            color = self._row_colors.get(index.row())
            if color:
                return QBrush(QColor(color))

        if role == Qt.ToolTipRole:
            tip = self._row_tooltips.get(index.row())
            if tip:
                return tip

        return None
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if section < len(self._headers):
                return self._headers[section]
        return None


class QuotationsFilterProxyModel(QSortFilterProxyModel):
    """Proxy model personalizzato per filtrare su tutte le colonne"""
    
    def filterAcceptsRow(self, source_row, source_parent):
        """Controlla se la riga deve essere mostrata in base al filtro"""
        source_model = self.sourceModel()
        if not source_model:
            return True
        
        # Ottieni il pattern del filtro
        if HAS_QREGULAREXPRESSION:
            regex = self.filterRegularExpression()
            if not regex.isValid() or regex.pattern() == "":
                return True
            filter_text = regex.pattern().lower()
        else:
            regex = self.filterRegExp()
            if not regex.isValid() or regex.pattern() == "":
                return True
            filter_text = regex.pattern().lower()
        
        # Cerca il testo in tutte le colonne
        for col in range(source_model.columnCount()):
            index = source_model.index(source_row, col, source_parent)
            if index.isValid():
                data = source_model.data(index, Qt.DisplayRole)
                if data and filter_text in str(data).lower():
                    return True
        
        return False


_HTTP_QUICK = (0.35, 0.65)
_API_OFFLINE_CACHE_SEC = 45
_STATUS_INTERVAL_ONLINE_MS = 5000
_STATUS_INTERVAL_OFFLINE_MS = 20000

# Request Center — tre colonne (stesso schema di Orders)

_FASTAPI_ONLINE_STYLE = f"""
    QLabel {{
        color: {STATUS_OK};
        font-size: 11px;
        font-weight: bold;
        background: transparent;
        padding: 4px 0px;
    }}
"""
_FASTAPI_OFFLINE_STYLE = f"""
    QLabel {{
        color: {STATUS_ERR};
        font-size: 11px;
        font-weight: bold;
        background: transparent;
        padding: 4px 0px;
    }}
"""
_NGROK_ONLINE_STYLE = """
    QLabel {
        color: #8B5CF6;
        font-size: 11px;
        font-weight: bold;
        background: transparent;
        padding: 4px 0px;
    }
"""
_NGROK_OFFLINE_STYLE = """
    QLabel {
        color: #FF0000;
        font-size: 11px;
        font-weight: bold;
        background: transparent;
        padding: 4px 0px;
    }
"""


def _fetch_messages_from_api(api_url: str):
    try:
        response = requests.get(api_url, timeout=_HTTP_QUICK)
        response.raise_for_status()
        data = response.json()
        if data.get("success", False):
            return data.get("messages", [])
    except requests.RequestException as exc:
        print(f"API messages unavailable ({api_url}): {exc}")
    except Exception as exc:
        print(f"API messages error: {exc}")
    return None


def _fetch_messages_from_db(project_root: Path):
    try:
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from modules.incoming_requests_db import ensure_incoming_request_table, list_incoming_requests

        ensure_incoming_request_table()
        return list_incoming_requests()
    except Exception as exc:
        print(f"SQLite incoming_request read error: {exc}")
        return None


class _InfrastructureStatusWorker(QThread):
    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        fastapi_online = False
        ngrok_text = "ngrok: OFFLINE"
        ngrok_style = _NGROK_OFFLINE_STYLE

        try:
            response = requests.get("http://127.0.0.1:8000/health", timeout=_HTTP_QUICK)
            fastapi_online = response.status_code == 200
        except requests.RequestException:
            pass

        try:
            response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=_HTTP_QUICK)
            if response.status_code == 200:
                tunnels = response.json().get("tunnels") or []
                https_tunnel = None
                for tunnel in tunnels:
                    if tunnel.get("proto") == "https" and tunnel.get("public_url"):
                        https_tunnel = tunnel
                        break
                if not https_tunnel:
                    for tunnel in tunnels:
                        if tunnel.get("public_url"):
                            https_tunnel = tunnel
                            break
                if https_tunnel:
                    public_url = https_tunnel.get("public_url", "")
                    display_url = public_url[:37] + "..." if len(public_url) > 40 else public_url
                    ngrok_text = f"ngrok: ONLINE — {display_url}"
                    ngrok_style = _NGROK_ONLINE_STYLE
        except requests.RequestException:
            pass

        self.result_ready.emit(
            {
                "fastapi_online": fastapi_online,
                "ngrok_text": ngrok_text,
                "ngrok_style": ngrok_style,
            }
        )


class _MessagesRefreshWorker(QThread):
    loaded = pyqtSignal(object, bool)

    def __init__(self, api_url: str, project_root: Path, skip_api: bool = False):
        super().__init__()
        self.api_url = api_url
        self.project_root = project_root
        self.skip_api = skip_api

    def run(self):
        from_api = False
        messages = None
        if not self.skip_api:
            messages = _fetch_messages_from_api(self.api_url)
            if messages is not None:
                from_api = True
        if messages is None:
            messages = _fetch_messages_from_db(self.project_root)
        self.loaded.emit(messages, from_api)


class _GmailPollWorker(QThread):
    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        try:
            from ui.common.gmail_imap_scheduler import trigger_imap_poll_now

            self.result_ready.emit(trigger_imap_poll_now())
        except Exception as exc:
            self.error.emit(str(exc))


class _TechnicalReplyWorker(QThread):
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, request_id: str, request_data: dict, parent=None):
        super().__init__(parent)
        self.request_id = request_id
        self.request_data = request_data

    def run(self) -> None:
        try:
            from modules.technical_auto_pipeline import elaborate_technical_request

            result = elaborate_technical_request(
                self.request_id,
                send_email=False,
                request_data=self.request_data,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class QuotationsHubWindow(SectionDialog):
    """Finestra Quotations Hub completa con navigazione tra sezioni"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quotations Hub")
        ensure_resizable_window(self, min_width=1280, min_height=720)
        self.setModal(False)
        
        # Root progetto (ui/windows/quotations → 3 livelli su)
        self.project_root = Path(__file__).resolve().parents[3]
        if str(self.project_root) not in sys.path:
            sys.path.insert(0, str(self.project_root))

        # Messaggi richieste web (FastAPI)
        self.messages_json_file = self.project_root / "fastapi_backend" / "data" / "messages.json"
        self.api_url = "http://localhost:8000/api/messages"
        
        # Percorso file log email
        self.logs_dir = Path(__file__).parent / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        self.email_log_file = self.logs_dir / "email_log.json"
        self.gmail_status_file = self.logs_dir / "gmail_status.json"
        self.gmail_imap_status_file = self.project_root / "logs" / "gmail_orders_status.json"
        self.last_email_file = self.logs_dir / "last_email.json"
        
        # Dati
        self.current_section = "Request Center"
        self.messages_data = []  # Richieste da SQLite (incoming_request)
        self.sent_emails_data: list = []  # Log email complete (parallelo alla tabella dx)

        self._api_offline_until = 0.0
        self._status_worker = None
        self._neural_stats_worker = None
        self._detail_panel_collapsed = False
        self._messages_worker = None
        self._detail_worker = None
        self._selected_request_id: str | None = None
        self._selected_request_msg: dict | None = None
        self._related_sent_emails: list = []
        self._timers_running = False
        self._ui_active = False
        self._updating_table = False
        self._ai_worker = None
        self._gmail_poll_worker = None
        self._technical_worker = None
        self._request_filter = "all"
        self._filtered_messages: list = []

        self.init_ui()
        self.apply_stylesheet()
        
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        
        self.neural_stats_timer = QTimer(self)
        self.neural_stats_timer.timeout.connect(self.update_neural_stats)
        
        self.email_log_timer = QTimer(self)
        self.email_log_timer.timeout.connect(self.load_email_log)
        
        self.gmail_status_timer = QTimer(self)
        self.gmail_status_timer.timeout.connect(self.update_gmail_status)

        self.messages_refresh_timer = QTimer(self)
        self.messages_refresh_timer.timeout.connect(
            lambda: self.load_messages_from_backend(force_api=False)
        )

    def on_section_shown(self) -> None:
        self._ui_active = True
        self._start_background_timers()
        self.load_messages_from_backend()
        self.update_status()
        self.update_neural_stats()
        self.load_email_log()
        self.update_gmail_status()

    def on_section_hidden(self) -> None:
        self._ui_active = False
        self._stop_background_timers()

    def _is_ui_active(self) -> bool:
        return is_ui_active(self)

    def _start_background_timers(self):
        if self._timers_running:
            return
        self._timers_running = True
        interval = (
            _STATUS_INTERVAL_OFFLINE_MS
            if time.time() < self._api_offline_until
            else _STATUS_INTERVAL_ONLINE_MS
        )
        self.status_timer.start(interval)
        self.neural_stats_timer.start(15000)
        self.email_log_timer.start(10000)
        self.gmail_status_timer.start(10000)
        self.messages_refresh_timer.start(30000)

    def _stop_background_timers(self):
        if not self._timers_running:
            wait_workers(self, QUOTATIONS_WORKER_ATTRS)
            return
        self._timers_running = False
        self.status_timer.stop()
        self.neural_stats_timer.stop()
        self.email_log_timer.stop()
        self.gmail_status_timer.stop()
        if hasattr(self, "messages_refresh_timer"):
            self.messages_refresh_timer.stop()
        if getattr(self, "_fast_section_hide", False):
            return
        wait_workers(self, QUOTATIONS_WORKER_ATTRS)

    def closeEvent(self, event):
        self._ui_active = False
        self.on_section_hidden()
        super().closeEvent(event)
        
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top bar
        top_bar = self.create_top_bar()
        main_layout.addWidget(top_bar)
        
        # Contenuto principale (layout orizzontale)
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Menu laterale sinistro
        left_menu = self.create_left_menu()
        content_layout.addWidget(left_menu, 0)
        
        # Area principale con StackedWidget per navigazione
        self.stacked_widget = QStackedWidget()
        
        # Mappa sezioni per nome -> indice nello stacked widget
        self.section_index_map = {}
        current_index = 0
        
        # Sezione Request Center (SQLite incoming_request)
        centro_section = self.create_centro_richieste_section()
        self.stacked_widget.addWidget(centro_section)
        self.section_index_map["Request Center"] = current_index
        current_index += 1

        # Sezione Help
        help_section = self.create_help_section()
        self.stacked_widget.addWidget(help_section)
        self.section_index_map["Help"] = current_index
        current_index += 1
        
        content_layout.addWidget(self.stacked_widget, 1)

        footer = self.create_footer()

        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(content_widget, 1)
        body_layout.addWidget(footer, 0)

        main_layout.addWidget(body_widget, 1)
        
        # Imposta sezione iniziale
        self.show_section("Request Center")
        
    def create_top_bar(self):
        """Crea la top bar con Dashboard, logo, titolo e SYNC DATABASE"""
        top_frame = QFrame()
        top_frame.setFixedHeight(70)
        top_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
        """)
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(20, 10, 20, 10)
        top_layout.setSpacing(15)
        
        # Pulsante Dashboard
        dashboard_button = QPushButton("← Dashboard")
        apply_button_role(dashboard_button, "secondary", min_height=34)
        dashboard_button.clicked.connect(self.go_back)
        top_layout.addWidget(dashboard_button)
        
        # Logo N+
        logo_label = QLabel("N+")
        logo_label.setFixedSize(40, 40)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("""
            QLabel {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 2px solid #5a3a7a;
                border-radius: 20px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        top_layout.addWidget(logo_label)
        
        # Titolo e sottotitolo
        title_layout = QVBoxLayout()
        title_layout.setSpacing(0)
        
        title_label = QLabel("Quotations Hub")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        title_layout.addWidget(title_label)
        
        subtitle_label = QLabel("Neural sync active")
        subtitle_label.setStyleSheet(f"color: {TEXT_SUBTITLE_OK}; font-size: 11px;")
        title_layout.addWidget(subtitle_label)
        
        top_layout.addLayout(title_layout)
        top_layout.addStretch()

        self._top_bar_frame = top_frame
        return top_frame
    
    def create_left_menu(self):
        """Crea il menu laterale sinistro (scrollabile in verticale)"""
        menu_frame = QFrame()
        menu_frame.setFixedWidth(250)
        menu_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border-right: 1px solid #2a2a3a;
            }
        """)
        outer_layout = QVBoxLayout(menu_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        menu_scroll = QScrollArea()
        menu_scroll.setWidgetResizable(True)
        menu_scroll.setFrameShape(QFrame.NoFrame)
        menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        menu_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        menu_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #1a1a2a;
                width: 10px;
                border-radius: 5px;
                margin: 2px 0;
            }
            QScrollBar::handle:vertical {
                background: #4a2a6a;
                border-radius: 5px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: #5a3a7a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        menu_content = QWidget()
        menu_content.setStyleSheet("background-color: #1a1a2a;")
        menu_layout = QVBoxLayout(menu_content)
        menu_layout.setContentsMargins(15, 20, 15, 20)
        menu_layout.setSpacing(10)
        
        # Titolo NAVIGATION
        nav_title = QLabel("NAVIGATION")
        nav_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: bold; padding: 10px 0;")
        menu_layout.addWidget(nav_title)
        
        self.menu_items = [
            ("Request Center", "📧", 0),
            ("Help", "❓", 1),
        ]
        
        self.menu_buttons = {}
        for text, icon, section_idx in self.menu_items:
            button = QPushButton(f"{icon} {text}")
            apply_button_role(button, "ghost", min_height=45)
            button.clicked.connect(lambda checked, name=text: self.show_section(name))
            menu_layout.addWidget(button)
            self.menu_buttons[text] = button
        
        menu_layout.addSpacing(20)
        
        # Neural Stats
        stats_title = QLabel("NEURAL STATS")
        stats_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: bold; padding: 10px 0;")
        menu_layout.addWidget(stats_title)

        self.neural_stat_model = QLabel("Model: —")
        self.neural_stat_engine = QLabel("Engine: —")
        self.neural_stat_tps = QLabel("Tokens/s: —")
        self.neural_stat_queue = QLabel("Inference queue: —")
        self.neural_stat_pipeline = QLabel("Pipeline: —")
        for lbl in (
            self.neural_stat_model,
            self.neural_stat_engine,
            self.neural_stat_tps,
            self.neural_stat_queue,
            self.neural_stat_pipeline,
        ):
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 2px 0;")
            lbl.setWordWrap(True)
            menu_layout.addWidget(lbl)

        menu_layout.addSpacing(15)

        # Box Localhost Status (sotto NEURAL STATS)
        localhost_box = self.create_localhost_status_box(is_left_column=True)
        menu_layout.addWidget(localhost_box)

        # Box Gmail Service Status (sotto NEURAL STATS)
        gmail_status_box = self._create_gmail_status_box()
        menu_layout.addWidget(gmail_status_box)

        menu_layout.addStretch()

        db_button = QPushButton("Browse / Edit DB")
        apply_button_role(db_button, "secondary", min_height=40)
        db_button.setToolTip("Opens SQL Databaser on data/nstonellm.db")
        db_button.clicked.connect(self.open_sql_database)
        menu_layout.addWidget(db_button)

        menu_scroll.setWidget(menu_content)
        outer_layout.addWidget(menu_scroll)

        return menu_frame
    
    def create_centro_richieste_section(self):
        """Request Center — consultazione e modifica tabella incoming_request (SQLite)."""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(20, 20, 20, 20)
        section_layout.setSpacing(15)
        
        # Titolo e descrizione
        title_label = QLabel("Request Center")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        section_layout.addWidget(title_label)
        
        desc_label = QLabel(
            "Web form requests in SQLite · select, edit, and save to the database"
        )
        desc_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px;")
        section_layout.addWidget(desc_label)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(0)

        self._request_center_left = self.create_left_column()
        self._request_center_center = self.create_center_column()
        self._request_center_right = self.create_right_column()
        self._request_center_splitter = create_hub_three_column_splitter(
            self._request_center_left,
            self._request_center_center,
            self._request_center_right,
        )
        columns_layout.addWidget(self._request_center_splitter)
        schedule_hub_splitter_collapsed(self._request_center_splitter)

        section_layout.addLayout(columns_layout, 1)
        
        return section_widget
    
    def create_left_column(self):
        """Crea la colonna sinistra: Incoming Requests (Form HTML) + Localhost Status"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(12)
        
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_label = QLabel("Incoming Requests")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        title_row.addWidget(title_label)
        title_row.addStretch()

        badge_label = QLabel("0 NEW")
        badge_label.setStyleSheet("""
            QLabel {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border-radius: 12px;
                padding: 5px 15px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        badge_label.setAlignment(Qt.AlignCenter)
        title_row.addWidget(badge_label)
        column_layout.addLayout(title_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_label = QLabel("Show:")
        filter_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        filter_row.addWidget(filter_label)

        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        for key, label, qss in (
            ("all", "Tutti", BTN_FILTER),
            ("commercial", "Commerciali", BTN_FILTER),
            ("technical", "Tecnici", BTN_FILTER_TECH),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            btn.setStyleSheet(qss)
            btn.clicked.connect(lambda _=False, k=key: self._set_request_filter(k))
            self._filter_group.addButton(btn)
            filter_row.addWidget(btn)
            if key == "all":
                btn.setChecked(True)
        filter_row.addStretch()
        column_layout.addLayout(filter_row)
        
        requests_table = QTableView()
        headers = ["Tipo", "Date", "Name", "Email", "Message", "Status"]
        model = QuotationsTableModel([], headers)
        requests_table.setModel(model)
        configure_requests_table(requests_table)
        requests_table.setAlternatingRowColors(True)
        requests_table.setSelectionBehavior(QTableView.SelectRows)
        requests_table.setEditTriggers(QTableView.NoEditTriggers)
        
        if HAS_REQUEST_DETAIL_WINDOW:
            requests_table.doubleClicked.connect(self.on_request_table_double_clicked)
            requests_table.clicked.connect(self._on_request_table_clicked)
            requests_table.selectionModel().selectionChanged.connect(
                self._on_request_selection_changed
            )
        
        column_layout.addWidget(requests_table, 1)

        footer = QWidget()
        footer.setMinimumHeight(HUB_SIDE_FOOTER_HEIGHT)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(10)
        
        refresh_btn = QPushButton("Refresh")
        apply_button_role(refresh_btn, "secondary", min_height=34)
        refresh_btn.clicked.connect(lambda: self.load_messages_from_backend(force_api=True))
        footer_layout.addWidget(refresh_btn)

        self.poll_gmail_btn = QPushButton("Poll Gmail")
        self.poll_gmail_btn.setToolTip(
            "Check Gmail inbox now (new requests + quotation replies)"
        )
        apply_button_role(self.poll_gmail_btn, "secondary", min_height=34)
        self.poll_gmail_btn.clicked.connect(self._poll_gmail_now)
        footer_layout.addWidget(self.poll_gmail_btn)

        delete_btn = QPushButton("Delete")
        apply_button_role(delete_btn, "danger", min_height=34)
        delete_btn.clicked.connect(self.delete_selected_request)
        footer_layout.addWidget(delete_btn)

        column_layout.addWidget(footer)
        
        # Salva riferimenti per aggiornamenti futuri
        self.left_requests_table = requests_table
        self.left_requests_model = model
        self.left_badge_label = badge_label
        
        return column_widget
    
    def create_center_column(self):
        """Colonna centrale: dettaglio richiesta (attiva solo su selezione tabella sx)."""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        title_label = QLabel("Request Details")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        header_row.addWidget(title_label)
        header_row.addStretch()
        self.detail_close_btn = QPushButton("×")
        self.detail_close_btn.setToolTip("Close detail panel")
        self.detail_close_btn.setVisible(False)
        self.detail_close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888899;
                border: 1px solid #3a3a5a;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #3a2a3a;
                color: #FFFFFF;
                border-color: #6a4a6a;
            }
        """)
        self.detail_close_btn.clicked.connect(self._collapse_request_detail_panel)
        header_row.addWidget(self.detail_close_btn)
        column_layout.addLayout(header_row)

        self._detail_empty_default_text = (
            "Select a request from the table on the left to view "
            "customer message, status, and quotation actions."
        )
        self.detail_empty_label = QLabel(self._detail_empty_default_text)
        self.detail_empty_label.setWordWrap(True)
        self.detail_empty_label.setAlignment(Qt.AlignCenter)
        self.detail_empty_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 40px 16px;"
        )
        column_layout.addWidget(self.detail_empty_label, 1)

        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 12px;
                padding: 12px;
            }
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(10)

        self.detail_meta_label = QLabel("—")
        self.detail_meta_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.detail_meta_label.setWordWrap(True)
        panel_layout.addWidget(self.detail_meta_label)

        self.detail_contact_label = QLabel("—")
        self.detail_contact_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        self.detail_contact_label.setWordWrap(True)
        panel_layout.addWidget(self.detail_contact_label)

        msg_header = QHBoxLayout()
        msg_title = QLabel("Customer Message")
        msg_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        msg_header.addWidget(msg_title)
        msg_header.addStretch()
        self.detail_rag_btn = QPushButton("Retrieval Fabric")
        self.detail_rag_btn.setToolTip(
            "Apre Retrieval Fabric → Ask con il testo del messaggio cliente"
        )
        apply_button_role(self.detail_rag_btn, "rag_compact", min_height=26)
        self.detail_rag_btn.clicked.connect(self._open_in_retrieval_fabric)
        self.detail_rag_btn.setEnabled(False)
        msg_header.addWidget(self.detail_rag_btn)
        panel_layout.addLayout(msg_header)

        self.detail_message_open_btn = QPushButton()
        self.detail_message_open_btn.setFlat(True)
        self.detail_message_open_btn.setCursor(Qt.PointingHandCursor)
        self.detail_message_open_btn.setMinimumHeight(72)
        self.detail_message_open_btn.setMaximumHeight(120)
        self.detail_message_open_btn.setStyleSheet("""
            QPushButton {
                background-color: #0a0a1a;
                color: #E8E8E8;
                border: 1px solid #3a3a5a;
                border-radius: 8px;
                padding: 12px;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #14142a;
                border-color: #6B4C9A;
            }
        """)
        self.detail_message_open_btn.clicked.connect(
            lambda: self._open_request_full_detail(initial_tab=0)
        )
        panel_layout.addWidget(self.detail_message_open_btn)

        stato_title = QLabel("Request Status")
        stato_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(stato_title)

        self.detail_stato = QComboBox()
        self.detail_stato.setEditable(True)
        self.detail_stato.addItems([
            "NUOVA", "NUOVA_TECNICA", "IN_ELABORAZIONE", "ELABORATA", "OFFERTA_INVIATA",
            "BOZZA_IN_ATTESA", "BOZZA_TECNICA", "RISPOSTA_TECNICA",
            "IN_CONVERSAZIONE", "ORDINE_CONFERMATO",
            "INVIATA", "ARCHIVIATA", "ERRORE", "ERRORE_TECNICA",
        ])
        self.detail_stato.setStyleSheet("""
            QComboBox {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
        """)
        panel_layout.addWidget(self.detail_stato)

        self.detail_status_label = QLabel("")
        self.detail_status_label.setWordWrap(True)
        self.detail_status_label.setStyleSheet("color: #9B8CF6; font-size: 11px;")
        panel_layout.addWidget(self.detail_status_label)

        email_title = QLabel("Email Sent to Customer")
        email_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(email_title)

        self.detail_email_open_btn = QPushButton("No linked email")
        self.detail_email_open_btn.setFlat(True)
        self.detail_email_open_btn.setCursor(Qt.PointingHandCursor)
        self.detail_email_open_btn.setEnabled(False)
        self.detail_email_open_btn.setStyleSheet("""
            QPushButton {
                color: #888899; font-size: 11px; text-align: left;
                padding: 4px 0; border: none;
            }
            QPushButton:enabled { color: #7EB8FF; }
            QPushButton:enabled:hover { color: #A8D4FF; text-decoration: underline; }
            QPushButton:disabled { color: #888899; }
        """)
        self.detail_email_open_btn.clicked.connect(
            lambda: self._open_request_full_detail(initial_tab=1)
        )
        panel_layout.addWidget(self.detail_email_open_btn)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        detail_scroll.setFrameShape(QFrame.NoFrame)
        detail_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        detail_scroll.setWidget(panel)

        detail_actions = QWidget()
        detail_actions_layout = QVBoxLayout(detail_actions)
        detail_actions_layout.setContentsMargins(0, 8, 0, 0)
        detail_actions_layout.setSpacing(8)

        btn_row_top = QHBoxLayout()
        btn_row_top.setSpacing(8)
        self.detail_generate_btn = QPushButton("Generate Quotation")
        apply_button_role(self.detail_generate_btn, "primary", min_height=36)
        self.detail_generate_btn.clicked.connect(self._on_center_generate_quotation)
        btn_row_top.addWidget(self.detail_generate_btn, 1)

        self.detail_technical_btn = QPushButton("Technical Reply")
        self.detail_technical_btn.setToolTip(
            "Risposta tecnica da knowledge base (senza calcolo prezzi / offerta)"
        )
        apply_button_role(self.detail_technical_btn, "technical", min_height=36)
        self.detail_technical_btn.clicked.connect(self._on_center_technical_reply)
        self.detail_technical_btn.setEnabled(False)
        btn_row_top.addWidget(self.detail_technical_btn, 1)
        detail_actions_layout.addLayout(btn_row_top)

        btn_row_bottom = QHBoxLayout()
        btn_row_bottom.setSpacing(8)
        self.detail_open_btn = QPushButton("Full Details")
        apply_button_role(self.detail_open_btn, "secondary", min_height=36)
        self.detail_open_btn.clicked.connect(
            lambda: self._open_request_full_detail(initial_tab=0)
        )
        btn_row_bottom.addWidget(self.detail_open_btn, 1)

        self.detail_save_db_btn = QPushButton("Save to DB")
        apply_button_role(self.detail_save_db_btn, "secondary", min_height=36)
        self.detail_save_db_btn.setToolTip(
            "Save message, status, and draft to incoming_request table (SQLite)"
        )
        self.detail_save_db_btn.clicked.connect(self.save_selected_request_to_db)
        btn_row_bottom.addWidget(self.detail_save_db_btn, 1)
        detail_actions_layout.addLayout(btn_row_bottom)

        self.detail_content = QWidget()
        detail_content_layout = QVBoxLayout(self.detail_content)
        detail_content_layout.setContentsMargins(0, 0, 0, 0)
        detail_content_layout.setSpacing(0)
        detail_content_layout.addWidget(detail_scroll, 1)
        detail_content_layout.addWidget(detail_actions)

        self.detail_panel = self.detail_content
        self.detail_panel.setVisible(False)
        column_layout.addWidget(self.detail_panel, 1)

        return column_widget

    @staticmethod
    def _extract_material_hints(text: str) -> str:
        if not (text or "").strip():
            return "—"
        lower = text.lower()
        found: list[str] = []
        for kw in _MATERIAL_KEYWORDS:
            if kw in lower and kw not in found:
                found.append(kw)
        if found:
            return ", ".join(w.capitalize() for w in found)
        return "Not detected automatically — see full message."

    def _set_request_center_splitter_expanded(self, expanded: bool) -> None:
        splitter = getattr(self, "_request_center_splitter", None)
        if splitter is None:
            return
        if expanded:
            expand_hub_center_column(splitter)
        else:
            collapse_hub_center_column(splitter)

    def _collapse_request_detail_panel(self) -> None:
        self._detail_panel_collapsed = True
        if hasattr(self, "detail_empty_label"):
            self.detail_empty_label.setText(
                "Detail panel closed — click the row again or select another request."
            )
            self.detail_empty_label.setVisible(True)
        if hasattr(self, "detail_panel"):
            self.detail_panel.setVisible(False)
        if hasattr(self, "detail_close_btn"):
            self.detail_close_btn.setVisible(False)
        self._set_request_center_splitter_expanded(False)

    def _show_request_detail_panel(self) -> None:
        self._detail_panel_collapsed = False
        if hasattr(self, "detail_empty_label"):
            self.detail_empty_label.setText(self._detail_empty_default_text)
            self.detail_empty_label.setVisible(False)
        if hasattr(self, "detail_panel"):
            self.detail_panel.setVisible(True)
        if hasattr(self, "detail_close_btn"):
            self.detail_close_btn.setVisible(True)
        self._set_request_center_splitter_expanded(True)

    def _on_request_table_clicked(self, index: QModelIndex) -> None:
        if getattr(self, "_updating_table", False):
            return
        if not index.isValid():
            return
        self._detail_panel_collapsed = False
        msg = self._get_message_for_row(index.row())
        self._populate_request_detail(msg)

    def _on_request_selection_changed(self):
        if getattr(self, "_updating_table", False):
            return
        if not self._is_ui_active():
            return
        if not hasattr(self, "left_requests_table"):
            return
        selection = self.left_requests_table.selectionModel()
        if not selection or not selection.hasSelection():
            self._populate_request_detail(None)
            return
        rows = selection.selectedRows()
        if not rows:
            self._populate_request_detail(None)
            return
        self._detail_panel_collapsed = False
        row = rows[0].row()
        msg = self._get_message_for_row(row)
        self._populate_request_detail(msg)

    def _get_message_for_row(self, row: int):
        pool = self._filtered_messages if self._filtered_messages else self.messages_data
        if 0 <= row < len(pool):
            return pool[row]
        return None

    def _set_request_filter(self, mode: str) -> None:
        self._request_filter = mode
        self._apply_messages_to_table(self.messages_data)

    def _open_in_retrieval_fabric(self) -> None:
        msg = self._selected_request_msg
        if not msg:
            return
        text = str(msg.get("messaggio") or "").strip()
        if not text:
            QMessageBox.information(
                self,
                "Retrieval Fabric",
                "No customer message text to send to Ask.",
            )
            return
        from ui.windows.ai.retrieval_fabric_window import RetrievalFabricWindow

        dashboard = resolve_dashboard(self)
        owner = dashboard if dashboard is not None else self
        win = getattr(owner, "retrieval_fabric_window", None)
        if win is None:
            win = RetrievalFabricWindow(owner)
            owner.retrieval_fabric_window = win
        win.open_ask_with_question(text)
        show_section_window(win)

    def _on_center_technical_reply(self) -> None:
        if not self._selected_request_id or not self._selected_request_msg:
            return
        if self._technical_worker is not None and self._technical_worker.isRunning():
            return

        self.detail_technical_btn.setEnabled(False)
        self.detail_generate_btn.setEnabled(False)
        self.detail_status_label.setText("Technical reply in progress…")

        worker = _TechnicalReplyWorker(
            self._selected_request_id,
            dict(self._selected_request_msg),
            parent=self,
        )
        worker.result_ready.connect(self._on_center_technical_done)
        worker.error.connect(self._on_center_technical_error)
        worker.finished.connect(worker.deleteLater)
        self._technical_worker = worker
        worker.start()

    def _on_center_technical_done(self, result: dict) -> None:
        self._technical_worker = None
        if self._selected_request_id and hasattr(self, "detail_technical_btn"):
            self.detail_technical_btn.setEnabled(True)
            self.detail_generate_btn.setEnabled(True)
        if not result.get("ok"):
            self.detail_status_label.setText(
                f"Technical error: {result.get('error', 'unknown')}"
            )
            return
        reply = str(result.get("reply") or "").strip()
        for msg in self.messages_data:
            if str(msg.get("id")) == self._selected_request_id:
                msg["risposta_gemini"] = reply
                msg["stato"] = "BOZZA_TECNICA"
                break
        self.load_messages_from_backend()
        self.detail_status_label.setText(
            "Technical reply ready — open Full Details to review before sending."
        )
        if reply:
            QMessageBox.information(
                self,
                "Technical Reply",
                "Draft generated from knowledge base (no price calculation).",
            )

    def _on_center_technical_error(self, error_msg: str) -> None:
        self._technical_worker = None
        if self._selected_request_id and hasattr(self, "detail_technical_btn"):
            self.detail_technical_btn.setEnabled(True)
            self.detail_generate_btn.setEnabled(True)
        self.detail_status_label.setText(f"Technical error: {error_msg[:120]}")

    def _message_preview_text(self, msg: dict) -> str:
        text = str(msg.get("messaggio") or "").strip()
        if not text:
            preview = "(nessun testo)"
        else:
            preview = text[:300] + ("…" if len(text) > 300 else "")
        mats = self._extract_material_hints(text)
        email_hint = ""
        if msg.get("email_inviata"):
            email_hint = "\n✓ Email already sent to customer"
        elif str(msg.get("risposta_gemini") or "").strip():
            email_hint = "\n○ Draft ready — open details to view the email"
        return (
            f"{preview}\n\n"
            f"Materiali: {mats}"
            f"{email_hint}\n\n"
            "▸ Clicca per aprire messaggio completo, email inviata e conversazione"
        )

    def _populate_request_detail(self, msg):
        if not self._is_ui_active():
            return
        try:
            self._populate_request_detail_impl(msg)
        except RuntimeError:
            pass

    def _populate_request_detail_impl(self, msg):
        if not msg:
            self._selected_request_id = None
            self._selected_request_msg = None
            self._related_sent_emails = []
            self._detail_panel_collapsed = False
            self.detail_empty_label.setText(self._detail_empty_default_text)
            self.detail_empty_label.setVisible(True)
            self.detail_panel.setVisible(False)
            self.detail_close_btn.setVisible(False)
            self.detail_generate_btn.setEnabled(False)
            self.detail_technical_btn.setEnabled(False)
            self.detail_open_btn.setEnabled(False)
            self.detail_email_open_btn.setEnabled(False)
            self.detail_save_db_btn.setEnabled(False)
            if hasattr(self, "detail_rag_btn"):
                self.detail_rag_btn.setEnabled(False)
            self.detail_status_label.clear()
            self._set_request_center_splitter_expanded(False)
            return

        self._selected_request_id = str(msg.get("id") or "")
        self._selected_request_msg = msg
        self._related_sent_emails = self._find_emails_for_request(msg)
        self.detail_generate_btn.setEnabled(bool(self._selected_request_id))
        self.detail_technical_btn.setEnabled(bool(self._selected_request_id))
        self.detail_open_btn.setEnabled(bool(self._selected_request_id))
        self.detail_rag_btn.setEnabled(bool(str(msg.get("messaggio") or "").strip()))
        self.detail_save_db_btn.setEnabled(bool(self._selected_request_id))

        stato = str(msg.get("stato") or "NUOVA")
        ts = str(msg.get("timestamp") or "—")
        rid = self._selected_request_id
        short_id = rid[-4:].upper() if len(rid) >= 4 else rid
        self.detail_meta_label.setText(f"Ref …{short_id} · {ts} · Stato: {stato}")
        self.detail_meta_label.setToolTip(f"Full ID: {rid}")

        idx = self.detail_stato.findText(stato, Qt.MatchFixedString)
        if idx >= 0:
            self.detail_stato.setCurrentIndex(idx)
        else:
            self.detail_stato.setEditText(stato)

        nome = str(msg.get("nome") or "—")
        email = str(msg.get("email") or "—")
        self.detail_contact_label.setText(f"{nome} · {email}")

        self.detail_message_open_btn.setText(self._message_preview_text(msg))
        self.detail_status_label.clear()
        if stato.upper() == "ORDINE_CONFERMATO":
            linked = str(msg.get("linked_order_id") or "").strip()
            if linked:
                short_oid = linked[:14] + "…" if len(linked) > 14 else linked
                self.detail_status_label.setText(
                    f"Order confirmed · linked to {short_oid} (Order Center)"
                )
            else:
                self.detail_status_label.setText(
                    "Order confirmed by customer on email thread"
                )
        self._update_detail_email_status(msg)
        if self._detail_panel_collapsed:
            return
        self._show_request_detail_panel()

    def _find_emails_for_request(self, msg: dict) -> list:
        """Email inviate al cliente (log JSON + record SQLite richiesta)."""
        client_email = str(msg.get("email") or "").strip().lower()
        related: list = []
        seen: set = set()

        for entry in getattr(self, "sent_emails_data", []):
            to_addr = str(entry.get("to") or "").strip().lower()
            if client_email and to_addr == client_email:
                key = (to_addr, str(entry.get("timestamp") or ""), str(entry.get("body") or "")[:80])
                if key not in seen:
                    seen.add(key)
                    related.append(dict(entry))

        if msg.get("email_inviata") or msg.get("risposta_gemini"):
            body = str(msg.get("risposta_gemini") or "").strip()
            ts = str(msg.get("data_invio_email") or msg.get("data_elaborazione") or "")
            nome = str(msg.get("nome") or "Cliente")
            synthetic = {
                "to": msg.get("email"),
                "timestamp": ts,
                "subject": f"Risposta alla tua richiesta — NStone ({nome})",
                "body": body,
                "summary": body[:120] if body else "Risposta AI",
                "status": "inviata" if msg.get("email_inviata") else "bozza non inviata",
                "source": "incoming_request (SQLite)",
            }
            key = (
                str(synthetic.get("to") or "").lower(),
                ts,
                body[:80],
            )
            if key not in seen and body:
                seen.add(key)
                related.append(synthetic)
            elif not related and body:
                related.append(synthetic)

        related.sort(key=lambda e: str(e.get("timestamp") or ""), reverse=True)
        return related

    def _update_detail_email_status(self, msg: dict) -> None:
        n = len(self._related_sent_emails)
        has_draft = bool(str(msg.get("risposta_gemini") or "").strip())
        can_open = n > 0 or has_draft or msg.get("email_inviata") or msg.get("errore_email")
        self.detail_email_open_btn.setEnabled(bool(can_open))

        if n == 0:
            if msg.get("errore_email"):
                self.detail_email_open_btn.setText(
                    f"Invio non riuscito — clicca per dettaglio: {msg.get('errore_email')}"
                )
            elif has_draft:
                self.detail_email_open_btn.setText(
                    "Draft available — click to view customer email"
                )
            else:
                self.detail_email_open_btn.setText(
                    "No email sent yet for this request."
                )
            return
        latest = self._related_sent_emails[0]
        ts = latest.get("timestamp") or "—"
        status = latest.get("status") or ("inviata" if msg.get("email_inviata") else "—")
        extra = f" (+{n - 1} altre)" if n > 1 else ""
        self.detail_email_open_btn.setText(
            f"Ultima email: {ts} · {status}{extra} — clicca per aprire"
        )

    def _open_request_full_detail(self, initial_tab: int = 0):
        if not self._selected_request_msg:
            QMessageBox.information(
                self,
                "Selezione",
                "Select a request from the table.",
            )
            return
        if not HAS_QUOTATION_DETAIL_DIALOG or QuotationRequestDetailDialog is None:
            if self._related_sent_emails:
                self._open_sent_email_detail(self._related_sent_emails[0])
            else:
                QMessageBox.warning(self, "Unavailable", "Detail window not configured.")
            return
        dialog = QuotationRequestDetailDialog(
            self._selected_request_msg,
            self._related_sent_emails,
            extract_material_hints=self._extract_material_hints,
            parent=self,
            initial_tab=initial_tab,
        )
        dialog.saved.connect(self._on_detail_dialog_saved)
        show_auxiliary_window(dialog)

    def _on_detail_dialog_saved(self, fields: dict):
        if not self._selected_request_msg:
            return
        self._selected_request_msg.update(fields)
        for msg in self.messages_data:
            if str(msg.get("id")) == self._selected_request_id:
                msg.update(fields)
                break
        self._populate_request_detail(self._selected_request_msg)

    def _open_sent_email_detail(self, email_record: dict):
        dialog = SentEmailDetailDialog(email_record, parent=self)
        show_auxiliary_window(dialog)

    def _on_center_generate_quotation(self):
        if not self._selected_request_id:
            return
        if not HAS_REQUEST_DETAIL_WINDOW or RequestWorker is None:
            QMessageBox.warning(self, "Unavailable", "Processing engine not configured.")
            return
        if self._detail_worker is not None and self._detail_worker.isRunning():
            return

        wait_sec = _http_timeout_for_elabora()
        self.detail_generate_btn.setEnabled(False)
        self.detail_status_label.setText(
            f"Processing… (attendi fino a ~{max(1, wait_sec // 60)} min al primo avvio)"
        )

        url = f"http://127.0.0.1:8000/api/elabora?request_id={self._selected_request_id}"
        worker = RequestWorker("POST", url, timeout=wait_sec)

        def _on_done(result: dict):
            self._on_center_elaboration_done(result)
            self._detail_worker = None
            if self._selected_request_id and hasattr(self, "detail_generate_btn"):
                self.detail_generate_btn.setEnabled(True)

        def _on_err(error_msg: str):
            self._on_center_elaboration_error(error_msg)
            self._detail_worker = None
            if self._selected_request_id and hasattr(self, "detail_generate_btn"):
                self.detail_generate_btn.setEnabled(True)

        worker.result_ready.connect(_on_done)
        worker.error.connect(_on_err)
        # Cleanup SOLO sul finished nativo (thread realmente terminato)
        worker.finished.connect(worker.deleteLater)
        self._detail_worker = worker
        worker.start()

    def _on_center_elaboration_done(self, result: dict):
        if result.get("success") and result.get("reply"):
            reply = str(result["reply"])
            self.detail_status_label.setText("Quotation Generated. Apri il dettaglio per leggere l'email.")
            for msg in self.messages_data:
                if str(msg.get("id")) == self._selected_request_id:
                    msg["risposta_gemini"] = reply
                    msg["stato"] = "ELABORATA"
                    break
            self._populate_request_detail(
                next(
                    (m for m in self.messages_data if str(m.get("id")) == self._selected_request_id),
                    None,
                )
            )
            self.load_messages_from_backend()
            msg = next(
                (m for m in self.messages_data if str(m.get("id")) == self._selected_request_id),
                None,
            )
            if msg:
                self._populate_request_detail(msg)
            if result.get("email_sent"):
                QMessageBox.information(
                    self,
                    "Quotation Generated",
                    "Draft created and email sent to the customer.",
                )
            else:
                err = result.get("email_error") or (
                    "Email not sent — configure Gmail in Settings."
                )
                QMessageBox.information(
                    self,
                    "Quotation Generated",
                    f"Draft saved.\n\n{err}",
                )
        else:
            self.detail_status_label.setText("Processing failed.")
            QMessageBox.warning(self, "Error", "Unable to generate quotation.")

    def _on_center_elaboration_error(self, error_msg: str):
        self.detail_status_label.setText(f"Error: {error_msg}")
        QMessageBox.critical(self, "Error", f"Processing failed:\n{error_msg}")
    
    def create_right_column(self):
        """Crea la colonna destra: Sent Emails"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(12)
        
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_label = QLabel("Sent Emails")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        title_row.addWidget(title_label)
        title_row.addStretch()
        column_layout.addLayout(title_row)

        column_layout.addWidget(hub_side_toolbar_spacer())

        email_table = QTableView()
        headers = ["Date", "To", "Summary"]
        model = QuotationsTableModel([], headers)
        email_table.setModel(model)
        configure_email_table(email_table)
        email_table.setAlternatingRowColors(True)
        email_table.setSelectionBehavior(QTableView.SelectRows)
        email_table.setEditTriggers(QTableView.NoEditTriggers)
        email_table.doubleClicked.connect(self._on_email_table_double_clicked)

        column_layout.addWidget(email_table, 1)

        footer = QWidget()
        footer.setMinimumHeight(HUB_SIDE_FOOTER_HEIGHT)
        actions_layout = QHBoxLayout(footer)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)

        update_last_email_btn = QPushButton("Refresh Sent")
        apply_button_role(update_last_email_btn, "secondary", min_height=34)
        update_last_email_btn.clicked.connect(self.update_last_email_row)
        actions_layout.addWidget(update_last_email_btn)

        delete_email_btn = QPushButton("Delete Selected")
        delete_email_btn.setToolTip(
            "Permanently delete the selected email from the database "
            "(orange rows = open negotiation)"
        )
        apply_button_role(delete_email_btn, "danger", min_height=34)
        delete_email_btn.clicked.connect(self.delete_selected_sent_email)
        actions_layout.addWidget(delete_email_btn)

        column_layout.addWidget(footer)
        
        # Salva riferimenti per aggiornamenti futuri
        self.right_email_table = email_table
        self.right_email_model = model
        
        return column_widget

    def delete_selected_sent_email(self):
        """Elimina fisicamente l'email outbound selezionata da quotation_email_turn."""
        if not hasattr(self, "right_email_table"):
            return
        indexes = self.right_email_table.selectedIndexes()
        if not indexes:
            QMessageBox.warning(
                self, "No Selection", "Select an email from the table first."
            )
            return
        row = indexes[0].row()
        if row < 0 or row >= len(self.sent_emails_data):
            return
        entry = self.sent_emails_data[row]
        turn_id = entry.get("turn_id")
        if not turn_id:
            QMessageBox.warning(
                self, "Cannot Delete", "Row has no database reference."
            )
            return

        to_email = entry.get("to") or "—"
        subject = (entry.get("subject") or "")[:80]
        if entry.get("risky"):
            msg = (
                "⚠️ TRATTATIVA ANCORA APERTA\n\n"
                f"To: {to_email}\nSubject: {subject}\n\n"
                "Deleting this email may prevent future customer replies from "
                "being linked to the quotation (thread broken).\n\n"
                "Delete permanently anyway?"
            )
        else:
            msg = (
                f"To: {to_email}\nSubject: {subject}\n\n"
                "Permanently delete this email from the database?"
            )
        reply = QMessageBox.question(
            self, "Delete Sent Email", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            import sqlite3

            from modules.quotation_email_db import ensure_quotation_email_tables

            db_path = ensure_quotation_email_tables()
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            try:
                conn.execute("PRAGMA busy_timeout=5000")
                cur = conn.execute(
                    "DELETE FROM quotation_email_turn WHERE id = ?", (turn_id,)
                )
                conn.commit()
                deleted = cur.rowcount
            finally:
                conn.close()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Deletion failed:\n{exc}")
            return

        if deleted:
            self.load_email_log()
        else:
            QMessageBox.warning(
                self, "Not Found", "Email not found in database (already deleted?)."
            )

    def _create_gmail_status_box(self):
        """Box Gmail Service Status (menu laterale, sotto NEURAL STATS)."""
        gmail_status_box = QFrame()
        gmail_status_box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        gmail_status_layout = QVBoxLayout(gmail_status_box)
        gmail_status_layout.setContentsMargins(10, 10, 10, 10)
        gmail_status_layout.setSpacing(8)

        gmail_status_title = QLabel("Gmail Service Status")
        gmail_status_title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        gmail_status_layout.addWidget(gmail_status_title)

        gmail_status_label = QLabel("Waiting for backend data...")
        gmail_status_label.setStyleSheet("""
            QLabel {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 10px;
            }
        """)
        gmail_status_label.setWordWrap(True)
        gmail_status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        gmail_status_label.setMinimumHeight(80)
        gmail_status_label.setTextFormat(Qt.PlainText)
        gmail_status_layout.addWidget(gmail_status_label)

        self.gmail_status_label = gmail_status_label
        return gmail_status_box
    
    def create_localhost_status_box(self, is_left_column=True):
        """Crea il box Localhost Status con indicatori reali per FastAPI e ngrok"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(14, 14, 14, 14)
        box_layout.setSpacing(8)

        title_label = QLabel("Localhost Status")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        box_layout.addWidget(title_label)
        
        # Label FastAPI Status (solo per la colonna sinistra salviamo i riferimenti)
        if is_left_column:
            fastapi_label = QLabel("FastAPI: OFFLINE")
            fastapi_label.setStyleSheet(_FASTAPI_OFFLINE_STYLE)
            box_layout.addWidget(fastapi_label)
            self.fastapi_status_label = fastapi_label
            
            # Label ngrok Status
            ngrok_label = QLabel("ngrok: OFFLINE")
            ngrok_label.setStyleSheet(_FASTAPI_OFFLINE_STYLE)
            box_layout.addWidget(ngrok_label)
            self.ngrok_status_label = ngrok_label
        else:
            # Per la colonna destra, crea label statici (non aggiornati)
            fastapi_label = QLabel("FastAPI: -")
            fastapi_label.setStyleSheet("""
                QLabel {
                    color: #AAAAAA;
                    font-size: 11px;
                    font-weight: bold;
                    background: transparent;
                    padding: 4px 0px;
            }
        """)
            box_layout.addWidget(fastapi_label)
            
            ngrok_label = QLabel("ngrok: -")
            ngrok_label.setStyleSheet("""
                QLabel {
                    color: #AAAAAA;
                    font-size: 11px;
                    font-weight: bold;
                    background: transparent;
                    padding: 4px 0px;
            }
        """)
            box_layout.addWidget(ngrok_label)
        
        return box
    
    def create_outlook_status_box(self):
        """Crea il box Outlook Status"""
        return self.create_service_status_box(
            "Outlook Status",
            [
                ("Stato", "Connesso", "#00FF00"),
                ("Token", "Valido", "#00FF00"),
                ("Ultimo invio", "N/A", "#AAAAAA"),
                ("Latency", "15ms", "#AAAAAA")
            ],
            icon="📧"
        )
    
    def create_service_status_box(self, title, items, icon=None):
        """Crea un box di stato per servizi"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(12, 12, 12, 12)
        box_layout.setSpacing(8)
        
        # Titolo con icona
        title_layout = QHBoxLayout()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 14px;")
            title_layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        box_layout.addLayout(title_layout)
        
        # Items
        for label, value, color in items:
            item_layout = QHBoxLayout()
            
            item_label = QLabel(f"{label}: {value}")
            item_label.setStyleSheet(f"color: {color}; font-size: 10px;")
            item_layout.addWidget(item_label)
            item_layout.addStretch()
            
            box_layout.addLayout(item_layout)
        
        return box
    
    def create_help_section(self):
        """Sezione Help — assistente neurale per preventivi."""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(30, 30, 30, 30)
        section_layout.setSpacing(20)

        help_title = QLabel("Help")
        help_title.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        section_layout.addWidget(help_title)

        help_desc = QLabel(
            "Ask the neural engine how to handle requests, quotations, and the Quotations workflow."
        )
        help_desc.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        help_desc.setWordWrap(True)
        section_layout.addWidget(help_desc)
        
        # Scroll area per i messaggi
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #1a1a2a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #4a2a6a;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #5a3a7a;
            }
        """)
        
        # Widget per i messaggi
        messages_widget = QWidget()
        self.ai_messages_layout = QVBoxLayout(messages_widget)
        self.ai_messages_layout.setAlignment(Qt.AlignTop)
        self.ai_messages_layout.setSpacing(15)
        
        # Messaggio di benvenuto
        welcome_frame = QFrame()
        welcome_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a3a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        welcome_layout = QHBoxLayout(welcome_frame)
        welcome_layout.setContentsMargins(15, 15, 15, 15)
        welcome_layout.setSpacing(10)
        
        # Logo N+
        n_logo = QLabel("N+")
        n_logo.setFixedSize(40, 40)
        n_logo.setAlignment(Qt.AlignCenter)
        n_logo.setStyleSheet("""
            QLabel {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 2px solid #5a3a7a;
                border-radius: 20px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        welcome_layout.addWidget(n_logo)
        
        welcome_text = QLabel(
            "NStone Neural Engine ready. Ask how to process a request, "
            "usare Generate Quotation o consultare il database incoming_request."
        )
        welcome_text.setWordWrap(True)
        welcome_text.setStyleSheet("color: #FFFFFF; font-size: 14px; padding: 10px;")
        welcome_layout.addWidget(welcome_text, 1)
        
        self.ai_messages_layout.addWidget(welcome_frame)
        self.ai_messages_layout.addStretch()
        
        scroll_area.setWidget(messages_widget)
        section_layout.addWidget(scroll_area, 1)
        
        # Area input
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        
        # Campo input
        self.ai_input = QLineEdit()
        self.ai_input.setPlaceholderText("Ask about quotations, requests, or database…")
        self.ai_input.setMinimumHeight(50)
        self.ai_input.setStyleSheet("""
            QLineEdit {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 8px;
                padding: 12px 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #5a3a7a;
            }
        """)
        input_layout.addWidget(self.ai_input, 1)
        
        # Collega il tasto Invio al campo input
        self.ai_input.returnPressed.connect(self.send_ai_message)
        
        # Pulsante invio (icona aereo)
        send_button = QPushButton("✈")
        send_button.setFixedSize(50, 50)
        send_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 25px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        send_button.clicked.connect(self.send_ai_message)
        input_layout.addWidget(send_button)
        
        section_layout.addLayout(input_layout)
        
        return section_widget
    
    def create_footer(self):
        """Crea il footer con bottoni operativi per l'operatore"""
        footer_frame = QFrame()
        footer_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
        """)
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 12, 20, 12)
        footer_layout.setSpacing(10)
        
        title_label = QLabel("QUOTATIONS TOOLS")
        title_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(title_label)

        hint_label = QLabel(
            "Web form → SQLite → local/cloud AI → Gmail reply · Check LOCAL stack"
        )
        hint_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        hint_label.setWordWrap(True)
        hint_label.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(hint_label)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.addStretch()
        force_sync_btn = QPushButton("Force Sync")
        force_sync_btn.setToolTip("Ricarica le richieste da SQLite (incoming_request)")
        apply_button_role(force_sync_btn, "secondary", min_height=40)
        force_sync_btn.clicked.connect(self.sync_database)
        buttons_layout.addWidget(force_sync_btn)
        
        health_btn = QPushButton("Check Pipeline")
        health_btn.setToolTip(
            "Controlla SQLite richieste, FastAPI, motore neurale (Ollama/Gemini) e Gmail SMTP"
        )
        apply_button_role(health_btn, "secondary", min_height=40)
        health_btn.clicked.connect(self.run_quotations_health_check)
        buttons_layout.addWidget(health_btn)

        start_web_btn = QPushButton("Start Web Backend")
        start_web_btn.setToolTip(
            "Esegue avvia_backend_web.bat: FastAPI, ngrok e aggiornamento URL form (push Git)"
        )
        apply_button_role(start_web_btn, "secondary", min_height=40)
        start_web_btn.clicked.connect(self.launch_backend_web_stack)
        buttons_layout.addWidget(start_web_btn)

        stop_web_btn = QPushButton("Stop Web Backend")
        stop_web_btn.setToolTip(
            "Termina FastAPI sulla porta 8000 e il processo ngrok"
        )
        apply_button_role(stop_web_btn, "danger", min_height=40)
        stop_web_btn.clicked.connect(self.shutdown_backend_web_stack)
        buttons_layout.addWidget(stop_web_btn)
        buttons_layout.addStretch()
        
        footer_layout.addLayout(buttons_layout)
        
        return footer_frame
    
    def create_health_box(self, title, items, icon=None):
        """Crea un box di stato per Infrastructure Health"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(12, 12, 12, 12)
        box_layout.setSpacing(8)
        
        # Titolo con icona
        title_layout = QHBoxLayout()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 14px;")
            title_layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: bold;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        box_layout.addLayout(title_layout)
        
        # Items
        for label, value, color in items:
            item_layout = QHBoxLayout()
            
            item_label = QLabel(label)
            if value:
                item_label.setText(f"{label}: {value}")
            item_label.setStyleSheet(f"color: {color}; font-size: 10px;")
            item_layout.addWidget(item_label)
            item_layout.addStretch()
            
            box_layout.addLayout(item_layout)
        
        return box
    
    def create_request_statistics_box(self):
        """Statistiche richieste da SQLite incoming_request."""
        total_requests = len(getattr(self, "messages_data", []) or [])
        new_requests = sum(
            1 for m in (self.messages_data or [])
            if str(m.get("stato") or "").upper() in ("NUOVA", "NEW", "")
        )
        in_progress = sum(
            1 for m in (self.messages_data or [])
            if str(m.get("stato") or "").upper() in ("ELABORATA", "IN LAVORAZIONE")
        )
        completed = sum(
            1 for m in (self.messages_data or [])
            if str(m.get("stato") or "").upper() in (
                "INVIATA", "COMPLETATA", "OFFERTA_INVIATA", "ORDINE_CONFERMATO",
            )
            or m.get("email_inviata")
        )
        stats_box = self.create_health_box(
            "REQUEST STATISTICS",
            [
                (f"Total: {total_requests}", "", "#FFFFFF"),
                (f"New: {new_requests}", "", "#FFD93D" if new_requests > 0 else "#AAAAAA"),
                (f"In Progress: {in_progress}", "", "#8B5CF6"),
                (f"Completed: {completed}", "", "#00FF00")
            ],
            icon="📊"
        )
        
        return stats_box
    
    def show_section(self, section_name, section_idx=None):
        """Mostra una sezione specifica"""
        self.current_section = section_name
        
        # Aggiorna stile dei pulsanti menu
        for name, button in self.menu_buttons.items():
            if name == section_name:
                button.setStyleSheet("""
                    QPushButton {
                        background-color: #8B5CF6;
                        color: #FFFFFF;
                        border: none;
                        border-radius: 8px;
                        font-size: 13px;
                        font-weight: bold;
                        text-align: left;
                        padding: 10px 15px;
                    }
                    QPushButton:hover {
                        background-color: #9B6CF6;
                    }
                """)
            else:
                button.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #CCCCCC;
                        border: none;
                        border-radius: 8px;
                        font-size: 13px;
                        text-align: left;
                        padding: 10px 15px;
                    }
                    QPushButton:hover {
                        background-color: #2a2a3a;
                        color: #FFFFFF;
                    }
                """)
        
        # Trova l'indice corretto dalla mappa
        if section_idx is None:
            section_idx = self.section_index_map.get(section_name)
        
        # Se non trovato nella mappa, cerca nel menu_items come fallback
        if section_idx is None:
            for name, _, idx in self.menu_items:
                if name == section_name:
                    # Usa l'indice dalla mappa se disponibile, altrimenti quello del menu
                    section_idx = self.section_index_map.get(name, idx)
                    break
        
        # Mostra la sezione se l'indice è valido
        if section_idx is not None and 0 <= section_idx < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(section_idx)
        else:
            print(f"Warning: Sezione '{section_name}' non trovata (indice: {section_idx}, totale sezioni: {self.stacked_widget.count()})")
    
    def sync_database(self):
        """Ricarica richieste da SQLite (incoming_request)."""
        self.load_messages_from_backend(force_api=False)
        count = len(self.messages_data or [])
        from modules.incoming_requests_db import get_database_path

        db_path = get_database_path()
        QMessageBox.information(
            self,
            "Sync",
            f"Requests refreshed from SQLite.\n\n"
            f"Records in queue/archive: {count}\n{db_path}",
        )
    
    def open_sql_database(self):
        """Apre SQL Databaser per consultare e modificare nstonellm.db."""
        if not HAS_DATABASE_WINDOW or DatabaseWindow is None:
            QMessageBox.warning(
                self,
                "Database",
                "SQL Databaser is not available in this installation.",
            )
            return
        dialog = DatabaseWindow(parent=self)
        dialog.destroyed.connect(lambda *_: self.load_messages_from_backend())
        show_auxiliary_window(dialog)
        self.load_messages_from_backend(force_api=False)

    def save_selected_request_to_db(self):
        """Salva modifiche manuali su incoming_request (SQLite)."""
        if not self._selected_request_id:
            QMessageBox.information(
                self,
                "Save to DB",
                "Select a request from the table.",
            )
            return

        from modules.incoming_requests_db import update_incoming_request

        msg = self._selected_request_msg or {}
        fields = {
            "messaggio": str(msg.get("messaggio") or "").strip(),
            "stato": self.detail_stato.currentText().strip() or "NUOVA",
            "risposta_gemini": str(msg.get("risposta_gemini") or "").strip(),
        }
        result = update_incoming_request(self._selected_request_id, fields)
        if not result.get("ok"):
            QMessageBox.warning(
                self,
                "Save to DB",
                result.get("error", "Salvataggio non riuscito."),
            )
            return

        for msg in self.messages_data:
            if str(msg.get("id")) == self._selected_request_id:
                msg.update(fields)
                break

        self._populate_request_detail(
            next(
                (m for m in self.messages_data if str(m.get("id")) == self._selected_request_id),
                None,
            )
        )
        self.load_messages_from_backend(force_api=False)
        QMessageBox.information(
            self,
            "Save to DB",
            "Modifiche salvate in incoming_request.",
        )

    def send_ai_message(self):
        """Gestisce l'invio del messaggio alla sezione Help."""
        import traceback
        
        try:
            message = self.ai_input.text().strip()
            if not message:
                return
            
            print(f"\n[QUOTATIONS HUB] Messaggio inviato: {message}")

            # Disabilita input durante la chiamata
            self.ai_input.setEnabled(False)
            self.start_ai_worker(message)

        except Exception as e:
            print("\n" + "="*80)
            print("ERRORE IN send_ai_message (QUOTATIONS HUB):")
            print("="*80)
            traceback.print_exc()
            print("="*80 + "\n")

    def start_ai_worker(self, message: str):
        """Avvia il worker Help in background."""
        if not hasattr(self, "ai"):
            self.ai = AIAssistant()

        class _AIWorker(QThread):
            result_ready = pyqtSignal(str)

            def __init__(self, assistant, prompt, parent=None):
                super().__init__(parent)
                self.assistant = assistant
                self.prompt = prompt

            def run(self):
                response = self.assistant.rispondi(self.prompt)
                self.result_ready.emit(response if response else "")

        prev = getattr(self, "_ai_worker", None)
        if prev is not None and prev.isRunning():
            prev.wait(500)
        worker = _AIWorker(self.ai, message, self)
        worker.result_ready.connect(self.on_ai_response)
        # Cleanup SOLO sul finished nativo (thread realmente terminato)
        worker.finished.connect(worker.deleteLater)
        self._ai_worker = worker
        worker.start()

    def on_ai_response(self, response: str):
        """Aggiorna la UI con la risposta ricevuta dal worker"""
        if not self._is_ui_active():
            return
        try:
            print(f"DEBUG: risposta Gemini inviata alla UI: {response}")
            print("Risposta inviata alla UI")
            # Rimuove lo stretch finale per aggiungere nuovi messaggi
            if self.ai_messages_layout.count() > 0:
                last_item = self.ai_messages_layout.itemAt(self.ai_messages_layout.count() - 1)
                if last_item and last_item.spacerItem():
                    self.ai_messages_layout.removeItem(last_item)

            # Aggiungi risposta come label
            reply_label = QLabel(response if response else "No response received.")
            reply_label.setWordWrap(True)
            reply_label.setStyleSheet("""
                QLabel {
                    background-color: #2a2a3a;
                    color: #FFFFFF;
                    border-radius: 12px;
                    padding: 12px;
                    font-size: 14px;
                }
            """)
            self.ai_messages_layout.addWidget(reply_label)
            self.ai_messages_layout.addStretch()

        finally:
            self.ai_input.clear()
            self.ai_input.setEnabled(True)
    
    def read_messages_from_json(self):
        """
        Legge i messaggi dal file JSON.
        Restituisce una lista di dizionari.
        """
        try:
            if not self.messages_json_file.exists():
                print(f"File JSON non trovato: {self.messages_json_file}")
                return []
            
            with open(self.messages_json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                messages = data.get("messages", [])
                print(f"Letti {len(messages)} messaggi dal file JSON")
                return messages
        except json.JSONDecodeError as e:
            print(f"Errore nel parsing del JSON: {e}")
            QMessageBox.warning(self, "JSON Error",
                              f"Error reading JSON file:\n{e}")
            return []
        except Exception as e:
            print(f"Errore nella lettura del file JSON: {e}")
            QMessageBox.warning(self, "Error", 
                              f"Error reading file:\n{e}")
            return []
    
    def read_messages_from_api(self):
        """Legge i messaggi dall'API FastAPI (timeout breve, non bloccare a lungo)."""
        return _fetch_messages_from_api(self.api_url)
    
    def _apply_messages_to_table(self, messages):
        """Aggiorna tabella e badge con la lista messaggi."""
        if not self._is_ui_active():
            return
        self.messages_data = messages or []

        filter_mode = getattr(self, "_request_filter", "all")
        visible: list = []
        for msg in self.messages_data:
            if not isinstance(msg, dict):
                continue
            stato = str(msg.get("stato") or "NUOVA")
            technical = is_technical_stato(stato)
            if filter_mode == "commercial" and technical:
                continue
            if filter_mode == "technical" and not technical:
                continue
            visible.append(msg)
        self._filtered_messages = visible

        table_data = []
        row_tooltips: dict = {}
        row_badge_labels: dict = {}
        row_badge_colors: dict = {}
        nuove_richieste = 0
        nuove_tecniche = 0
        selected_id = getattr(self, "_selected_request_id", None)

        for row_idx, msg in enumerate(visible):
            msg_id = str(msg.get("id") or "")
            timestamp = str(msg.get("timestamp") or "")
            nome = str(msg.get("nome") or "")
            email = str(msg.get("email") or "")
            messaggio = str(msg.get("messaggio") or "")
            stato = str(msg.get("stato") or "NUOVA")

            if stato.upper() in ("NUOVA", "NEW"):
                nuove_richieste += 1
            if stato.upper() == "NUOVA_TECNICA":
                nuove_tecniche += 1

            short_date = timestamp[:16].replace("T", " ") if timestamp else "—"
            nome_disp = nome if len(nome) <= 42 else nome[:39] + "..."
            email_disp = email if len(email) <= 38 else email[:35] + "..."
            msg_disp = messaggio if len(messaggio) <= 80 else messaggio[:77] + "..."
            stato_disp = stato if len(stato) <= 16 else stato[:14] + "..."

            badge_label, badge_color = request_type_badge(stato)
            table_data.append(["", short_date, nome_disp, email_disp, msg_disp, stato_disp])
            row_tooltips[row_idx] = (
                f"Tipo: [{badge_label}]\n"
                f"ID: {msg_id}\n"
                f"Email: {email}\n"
                f"Status: {stato}\n\n"
                f"{messaggio[:400]}"
            )
            row_badge_labels[row_idx] = badge_label
            row_badge_colors[row_idx] = badge_color

        if hasattr(self, "left_requests_model"):
            headers = ["Tipo", "Date", "Name", "Email", "Message", "Status"]
            self.left_requests_model = QuotationsTableModel(
                table_data,
                headers,
                row_tooltips=row_tooltips,
                row_badge_labels=row_badge_labels,
                row_badge_colors=row_badge_colors,
            )
            if hasattr(self, "left_requests_table"):
                self._updating_table = True
                try:
                    self.left_requests_table.setModel(self.left_requests_model)
                    configure_requests_table(self.left_requests_table)
                    sm = self.left_requests_table.selectionModel()
                    if sm is not None:
                        try:
                            sm.selectionChanged.disconnect(self._on_request_selection_changed)
                        except TypeError:
                            pass
                        sm.selectionChanged.connect(self._on_request_selection_changed)
                        if selected_id:
                            for row, row_msg in enumerate(visible):
                                if str(row_msg.get("id")) == selected_id:
                                    idx = self.left_requests_model.index(row, 0)
                                    sm.select(
                                        idx,
                                        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
                                    )
                                    break
                finally:
                    self._updating_table = False

        if hasattr(self, "left_badge_label"):
            if nuove_tecniche:
                self.left_badge_label.setText(
                    f"{nuove_richieste} NEW · {nuove_tecniche} TECNICA"
                )
            else:
                self.left_badge_label.setText(f"{nuove_richieste} NEW")

        if selected_id:
            msg = next(
                (
                    m
                    for m in self.messages_data
                    if str(m.get("id")) == selected_id
                ),
                None,
            )
            if msg:
                self._populate_request_detail(msg)

    def _request_pipeline_counts(self) -> dict:
        msgs = self.messages_data or []
        new_count = sum(
            1 for m in msgs if str(m.get("stato") or "NUOVA").upper() in ("NUOVA", "NEW")
        )
        done_count = sum(
            1
            for m in msgs
            if str(m.get("stato") or "").upper() in (
                "ELABORATA", "INVIATA", "COMPLETATA", "ORDINE_CONFERMATO",
            )
            or m.get("email_inviata")
        )
        return {"total": len(msgs), "new": new_count, "done": done_count}

    def update_neural_stats(self):
        """Aggiorna NEURAL STATS nel menu laterale (motore LLM + pipeline SQLite)."""
        if not self._is_ui_active():
            return
        if self._neural_stats_worker is not None and self._neural_stats_worker.isRunning():
            return
        worker = NeuralStatsPollWorker(self._request_pipeline_counts(), self)
        wire_worker(self, worker, self._apply_neural_stats, "_neural_stats_worker")

    def _apply_neural_stats(self, stats: dict):
        if not self._is_ui_active():
            return
        try:
            apply_neural_stats_to_labels(
                {
                    "model": self.neural_stat_model,
                    "engine": self.neural_stat_engine,
                    "tps": self.neural_stat_tps,
                    "queue": self.neural_stat_queue,
                    "pipeline": self.neural_stat_pipeline,
                },
                stats,
                pipeline_kind="quotations",
            )
        except RuntimeError:
            pass

    def load_messages_from_backend(self, *, force_api: bool = False):
        """
        Mostra subito SQLite, poi aggiorna da API in background se disponibile.
        """
        local_messages = self.read_messages_from_db()
        if local_messages is not None:
            self._apply_messages_to_table(local_messages)

        skip_api = (not force_api) and time.time() < self._api_offline_until
        if self._messages_worker is not None and self._messages_worker.isRunning():
            return

        worker = _MessagesRefreshWorker(
            self.api_url,
            self.project_root,
            skip_api=skip_api,
        )
        worker.loaded.connect(self._on_messages_refreshed)
        wire_worker(self, worker, lambda: None, "_messages_worker")

    def _on_messages_refreshed(self, messages, from_api: bool):
        if not self._is_ui_active():
            return
        if from_api:
            self._api_offline_until = 0.0
            if messages is not None:
                self._apply_messages_to_table(messages)
            return

        self._api_offline_until = time.time() + _API_OFFLINE_CACHE_SEC
        if messages is None:
            fallback = self.read_messages_from_json() or []
            if fallback:
                self._apply_messages_to_table(fallback)
        elif not self.messages_data:
            self._apply_messages_to_table(messages)
    def read_messages_from_db(self):
        """Legge richieste da data/nstonellm.db (incoming_request)."""
        return _fetch_messages_from_db(self.project_root)

    def _resolve_request_id_from_row(self, row: int) -> str | None:
        pool = self._filtered_messages if self._filtered_messages else self.messages_data
        if 0 <= row < len(pool):
            rid = pool[row].get("id")
            if rid:
                return str(rid)
        return None

    def delete_selected_request(self):
        """Elimina la richiesta selezionata (SQLite + API FastAPI)."""
        if not hasattr(self, "left_requests_table"):
            return
        selection = self.left_requests_table.selectionModel()
        if not selection or not selection.hasSelection():
            QMessageBox.information(
                self,
                "Selection",
                "Select a request from the table to delete.",
            )
            return
        rows = selection.selectedRows()
        if not rows:
            return
        row = rows[0].row()
        request_id = self._resolve_request_id_from_row(row)
        if not request_id:
            QMessageBox.warning(self, "Error", "Unable to determine the request ID.")
            return

        nome = ""
        row_msg = self._get_message_for_row(row)
        if row_msg:
            nome = str(row_msg.get("nome") or "")

        answer = QMessageBox.question(
            self,
            "Confirm deletion",
            f"Delete request from {nome or request_id}?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        deleted = False
        api_offline = time.time() < self._api_offline_until
        if not api_offline:
            try:
                response = requests.delete(
                    "http://localhost:8000/api/delete_request",
                    params={"request_id": request_id},
                    timeout=_HTTP_QUICK,
                )
                if response.status_code == 200:
                    deleted = True
            except requests.RequestException as exc:
                print(f"API delete failed: {exc}")
                self._api_offline_until = time.time() + _API_OFFLINE_CACHE_SEC

        if not deleted:
            try:
                from modules.incoming_requests_db import delete_incoming_request

                result = delete_incoming_request(request_id)
                if result.get("ok"):
                    deleted = True
                else:
                    QMessageBox.warning(
                        self,
                        "Error",
                        result.get("error", "Delete failed."),
                    )
                    return
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Delete failed:\n{e}")
                return

        self.load_messages_from_backend()
        QMessageBox.information(self, "Deleted", "Request removed from the database.")
    
    def load_email_log(self):
        """
        Carica le offerte/email inviate dal DB SQLite
        (quotation_email_turn, direction=outbound — destinatario da incoming_request).
        Aggiorna la tabella delle email inviate.
        """
        if not self._is_ui_active():
            return
        if not hasattr(self, 'right_email_model') or not hasattr(self, 'right_email_table'):
            return
        
        email_data = []
        parsed_emails: list = []
        row_colors: dict = {}
        row_tooltips: dict = {}
        _OPEN_CASE_STATES = ("OFFERTA_INVIATA", "IN_CONVERSAZIONE")
        _RISKY_TOOLTIP = (
            "⚠️ Negotiation still open: deleting this email may prevent customer replies "
            "from being linked to the quotation."
        )

        try:
            import sqlite3

            from modules.quotation_email_db import ensure_quotation_email_tables

            db_path = ensure_quotation_email_tables()
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT t.id AS turn_id, t.case_id, t.created_at, t.subject, t.body,
                           COALESCE(r.email, '') AS to_email,
                           COALESCE(r.stato, '') AS case_stato
                    FROM quotation_email_turn t
                    LEFT JOIN incoming_request r ON r.id = t.case_id
                    WHERE t.direction = 'outbound'
                    ORDER BY t.created_at DESC
                    LIMIT 100
                    """
                ).fetchall()
            finally:
                conn.close()

            for idx, row in enumerate(rows):
                timestamp = str(row["created_at"] or "")
                to_email = str(row["to_email"] or "")
                subject = str(row["subject"] or "")
                if "=?" in subject:
                    try:
                        from email.header import decode_header, make_header

                        subject = str(make_header(decode_header(subject)))
                    except Exception:
                        pass
                body = str(row["body"] or "")
                case_stato = str(row["case_stato"] or "").strip().upper()
                risky = case_stato in _OPEN_CASE_STATES
                parsed_emails.append({
                    "turn_id": row["turn_id"],
                    "case_id": row["case_id"],
                    "timestamp": timestamp,
                    "to": to_email,
                    "subject": subject,
                    "body": body,
                    "summary": subject or body,
                    "case_stato": case_stato,
                    "risky": risky,
                    "source": "quotation_email_turn",
                })
                summary = subject or body
                if len(timestamp) > 19:
                    timestamp = timestamp[:19]
                if len(summary) > 100:
                    summary = summary[:100] + "..."
                if risky:
                    timestamp = f"⚠️ {timestamp}"
                    row_colors[idx] = "#FFB347"
                    row_tooltips[idx] = _RISKY_TOOLTIP
                email_data.append([timestamp, to_email, summary])

        except Exception as e:
            print(f"Errore lettura email inviate dal DB: {e}")

        self.sent_emails_data = parsed_emails
        # Aggiorna il modello della tabella
        headers = ["Timestamp", "Destinatario", "Summary"]
        self.right_email_model = QuotationsTableModel(
            email_data, headers, row_colors=row_colors, row_tooltips=row_tooltips
        )
        self.right_email_table.setModel(self.right_email_model)
        self.right_email_table.horizontalHeader().setStretchLastSection(True)

        if getattr(self, "_selected_request_id", None):
            msg = next(
                (
                    m
                    for m in self.messages_data
                    if str(m.get("id")) == self._selected_request_id
                ),
                None,
            )
            if msg:
                self._populate_request_detail(msg)

    def _on_email_table_double_clicked(self, index):
        row = index.row()
        if row < 0 or row >= len(self.sent_emails_data):
            return
        self._open_sent_email_detail(self.sent_emails_data[row])

    def launch_backend_web_stack(self):
        """Avvia avvia_backend_web.bat (FastAPI + ngrok + push URL)."""
        try:
            from modules.backend_web_stack import start_backend_web

            ok, message = start_backend_web(self.project_root)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Avvio backend web",
                f"Error starting backend:\n{exc}",
            )
            return

        if ok:
            QMessageBox.information(self, "Start Web Backend", message)
            QTimer.singleShot(3000, self.update_status)
        else:
            QMessageBox.warning(self, "Start Web Backend", message)

    def shutdown_backend_web_stack(self):
        """Arresta FastAPI (:8000) e ngrok."""
        reply = QMessageBox.question(
            self,
            "Stop Web Backend",
            "Terminare FastAPI (porta 8000) e ngrok?\n\n"
            "Le finestre cmd aperte manualmente potrebbero restare visibili "
            "ma i servizi verranno arrestati.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from modules.backend_web_stack import stop_backend_web

            ok, message = stop_backend_web()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Stop Web Backend",
                f"Error stopping backend:\n{exc}",
            )
            return

        icon = QMessageBox.Information if ok else QMessageBox.Warning
        QMessageBox(icon, "Stop Web Backend", message)
        self.update_status()

    def run_quotations_health_check(self):
        """Verifica stack LOCALE per il flusso preventivi (no cloud legacy)."""
        lines: list[str] = []

        # SQLite incoming_request
        try:
            rows = self.read_messages_from_db()
            count = len(rows) if rows else 0
            lines.append(f"SQLite richieste: OK ({count} in coda/archivio)")
        except Exception as exc:
            lines.append(f"SQLite richieste: FAIL ({exc})")

        # FastAPI
        try:
            resp = requests.get("http://127.0.0.1:8000/health", timeout=_HTTP_QUICK)
            if resp.status_code == 200:
                lines.append("FastAPI :8000: ONLINE")
            else:
                lines.append(f"FastAPI :8000: risposta {resp.status_code}")
        except requests.RequestException:
            lines.append(
                "FastAPI :8000: OFFLINE (avvia backend per Generate Quotation / dettaglio API)"
            )

        # LLM
        try:
            from llm.llm_service import get_llm_service, load_llm_config

            cfg = load_llm_config()
            provider = cfg.get("provider", "ollama")
            llm = get_llm_service()
            if llm.is_configured():
                lines.append(f"Motore neurale ({provider}): configurato")
            else:
                lines.append(f"Motore neurale ({provider}): non pronto — controlla Settings")
        except Exception as exc:
            lines.append(f"Motore neurale: FAIL ({exc})")

        # Gmail SMTP
        try:
            from core.machine_plc_config import load_config

            gmail = (load_config().get("gmail") or {})
            if (gmail.get("email") or "").strip() and (gmail.get("app_password") or "").strip():
                lines.append("Gmail SMTP: credenziali presenti in config")
            else:
                lines.append(
                    "Gmail SMTP: non configurato (Settings → Invio risposte Gmail)"
                )
        except Exception as exc:
            lines.append(f"Gmail SMTP: FAIL ({exc})")

        # ngrok (opzionale)
        try:
            resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=_HTTP_QUICK)
            if resp.status_code == 200 and (resp.json().get("tunnels") or []):
                lines.append("ngrok: tunnel attivo (form web esterno)")
            else:
                lines.append("ngrok: non attivo (opzionale per form remoto)")
        except requests.RequestException:
            lines.append("ngrok: non attivo (opzionale)")

        report = "\n".join(f"• {line}" for line in lines)
        QMessageBox.information(
            self,
            "Check Pipeline Quotations",
            f"Stack LOCALE — preventivazione\n\n{report}",
        )

    def update_last_email_row(self):
        """Pulsante "Aggiorna Ultima Email": ricarica le email inviate dal DB."""
        self.load_email_log()

    def _poll_gmail_now(self):
        if not self._is_ui_active():
            return
        worker = getattr(self, "_gmail_poll_worker", None)
        if worker is not None and worker.isRunning():
            return
        self.poll_gmail_btn.setEnabled(False)
        self.poll_gmail_btn.setText("⏳ Poll…")

        worker = _GmailPollWorker(self)
        worker.result_ready.connect(self._on_gmail_poll_done)
        worker.error.connect(self._on_gmail_poll_error)
        # Cleanup SOLO sul finished nativo (thread realmente terminato)
        worker.finished.connect(lambda: setattr(self, "_gmail_poll_worker", None))
        worker.finished.connect(worker.deleteLater)
        self._gmail_poll_worker = worker
        worker.start()

    def _on_gmail_poll_done(self, result: dict):
        if hasattr(self, "poll_gmail_btn"):
            self.poll_gmail_btn.setEnabled(True)
            self.poll_gmail_btn.setText("📥 Poll Gmail")
        self.load_messages_from_backend(force_api=False)
        self.update_gmail_status()
        if result.get("skipped"):
            return
        if result.get("status") == "ERROR":
            QMessageBox.warning(
                self,
                "Poll Gmail",
                result.get("error_message") or "IMAP Error",
            )
            return
        n_in = int(result.get("quotation_inbound") or 0)
        n_rep = int(result.get("quotation_replies") or 0)
        n_proc = int(result.get("emails_processed") or 0)
        if n_in or n_rep:
            QMessageBox.information(
                self,
                "Poll Gmail",
                f"Email elaborate: {n_proc}\n"
                f"Nuove richieste preventivo: {n_in}\n"
                f"Risposte cliente elaborate: {n_rep}",
            )

    def _on_gmail_poll_error(self, msg: str):
        if hasattr(self, "poll_gmail_btn"):
            self.poll_gmail_btn.setEnabled(True)
            self.poll_gmail_btn.setText("📥 Poll Gmail")
        QMessageBox.warning(self, "Poll Gmail", msg)

    def update_gmail_status(self):
        """
        Stato IMAP (logs/gmail_orders_status.json) + SMTP locale se presente.
        """
        if not self._is_ui_active():
            return
        if not hasattr(self, 'gmail_status_label'):
            return
        
        try:
            status_lines: list[str] = []
            color = "#AAAAAA"

            imap_file = getattr(self, "gmail_imap_status_file", None)
            if imap_file and imap_file.exists():
                with open(imap_file, 'r', encoding='utf-8') as f:
                    imap_data = json.load(f)
                st = imap_data.get("status", "UNKNOWN")
                color = "#00FF00" if st == "OK" else "#FF0000" if st == "ERROR" else "#AAAAAA"
                last = str(imap_data.get("last_check") or "")[:19]
                status_lines.append(f"IMAP casella: {st}")
                if last:
                    status_lines.append(f"Ultimo poll: {last}")
                n_proc = imap_data.get("emails_processed")
                if n_proc is not None:
                    status_lines.append(f"Email elaborate (ultimo poll): {n_proc}")
                n_in = imap_data.get("quotation_inbound", 0)
                n_rep = imap_data.get("quotation_replies", 0)
                if n_in or n_rep:
                    status_lines.append(
                        f"Preventivi: +{n_in} richieste · {n_rep} risposte thread"
                    )
                err = imap_data.get("error_message")
                if err:
                    status_lines.append(f"IMAP errore: {err}")
            else:
                status_lines.append(
                    "IMAP: in attesa del primo poll (avvio automatico con l'app)"
                )

            if self.gmail_status_file.exists():
                with open(self.gmail_status_file, 'r', encoding='utf-8') as f:
                    smtp_data = json.load(f)
                smtp_st = smtp_data.get("status")
                if smtp_st:
                    status_lines.append(f"SMTP invio: {smtp_st}")
                last_ok = smtp_data.get("last_success") or smtp_data.get("timestamp")
                if last_ok:
                    status_lines.append(f"Ultimo invio SMTP: {str(last_ok)[:19]}")

            status_text = "\n".join(status_lines) if status_lines else "Nessun dato Gmail"
            self.gmail_status_label.setText(status_text)
            self.gmail_status_label.setStyleSheet(f"""
                QLabel {{
                    background-color: #0a0a1a;
                    border: 1px solid #2a2a3a;
                    border-radius: 6px;
                    color: {color};
                    padding: 8px;
                    font-size: 11px;
                }}
            """)
            return

        except json.JSONDecodeError as e:
            error_text = f"Error parsing Gmail status:\n{str(e)}"
            self.gmail_status_label.setText(error_text)
            self.gmail_status_label.setStyleSheet("""
                QLabel {
                    background-color: #0a0a1a;
                    border: 1px solid #FF0000;
                    border-radius: 6px;
                    color: #FF0000;
                    padding: 8px;
                    font-size: 11px;
                }
            """)
        except Exception as e:
            error_text = f"Error reading gmail_status.json:\n{str(e)}"
            self.gmail_status_label.setText(error_text)
            self.gmail_status_label.setStyleSheet("""
                QLabel {
                    background-color: #0a0a1a;
                    border: 1px solid #FF0000;
                    border-radius: 6px;
                    color: #FF0000;
                    padding: 8px;
                    font-size: 11px;
                }
            """)
    
    def update_status(self):
        """Aggiorna lo stato FastAPI/ngrok in background (non blocca la UI)."""
        if not self._is_ui_active():
            return
        if self._status_worker is not None and self._status_worker.isRunning():
            return

        worker = _InfrastructureStatusWorker(self)
        wire_worker(self, worker, self._apply_infrastructure_status, "_status_worker")

    def _apply_infrastructure_status(self, status: dict):
        if not self._is_ui_active():
            return
        try:
            fastapi_online = status.get("fastapi_online", False)
            if fastapi_online:
                self._api_offline_until = 0.0
            elif self._api_offline_until <= time.time():
                self._api_offline_until = time.time() + _API_OFFLINE_CACHE_SEC

            if self._timers_running:
                interval = (
                    _STATUS_INTERVAL_ONLINE_MS
                    if fastapi_online
                    else _STATUS_INTERVAL_OFFLINE_MS
                )
                if self.status_timer.interval() != interval:
                    self.status_timer.setInterval(interval)

            if hasattr(self, 'fastapi_status_label'):
                if fastapi_online:
                    self.fastapi_status_label.setText("FastAPI: ONLINE")
                    self.fastapi_status_label.setStyleSheet(_FASTAPI_ONLINE_STYLE)
                else:
                    self.fastapi_status_label.setText("FastAPI: OFFLINE")
                    self.fastapi_status_label.setStyleSheet(_FASTAPI_OFFLINE_STYLE)

            if hasattr(self, 'ngrok_status_label'):
                self.ngrok_status_label.setText(status.get("ngrok_text", "ngrok: OFFLINE"))
                self.ngrok_status_label.setStyleSheet(
                    status.get("ngrok_style", _NGROK_OFFLINE_STYLE)
                )
        except RuntimeError:
            pass

    def update_stats(self):
        """Aggiorna le statistiche (placeholder per future estensioni)"""
        # Metodo mantenuto per compatibilità, può essere esteso in futuro
        pass
    
    def on_request_table_double_clicked(self, index):
        """Gestisce il doppio click sulla tabella delle richieste"""
        if not HAS_REQUEST_DETAIL_WINDOW:
            return
        
        if not hasattr(self, 'left_requests_model'):
            return
        
        # Ottieni la riga selezionata
        row = index.row()
        if row < 0 or row >= self.left_requests_model.rowCount():
            return
        
        # Ottieni l'ID dalla prima colonna (ID)
        request_id_index = self.left_requests_model.index(row, 0)
        request_id_full = self.left_requests_model.data(request_id_index, Qt.DisplayRole)
        
        # Se l'ID è troncato (contiene "..."), recuperalo dai messaggi in memoria
        if request_id_full and "..." in str(request_id_full):
            if hasattr(self, 'messages_data'):
                prefix = str(request_id_full).replace("...", "")
                for msg in self.messages_data:
                    msg_id = str(msg.get("id", ""))
                    if msg_id.startswith(prefix):
                        request_id_full = msg_id
                        break
        
        if not request_id_full:
            QMessageBox.warning(
                self,
                "Attenzione",
                "Impossibile determinare l'ID della richiesta selezionata."
            )
            return
        
        # Apri la finestra di dettaglio
        self.open_request_detail(str(request_id_full))
    
    def on_open_detail_clicked(self):
        """Gestisce il click sul pulsante 'Apri dettaglio'"""
        if not HAS_REQUEST_DETAIL_WINDOW:
            QMessageBox.warning(
                self,
                "Attenzione",
                "Finestra dettaglio richiesta non disponibile."
            )
            return
        
        # Ottieni la riga selezionata
        if not hasattr(self, 'left_requests_table'):
            return
        
        selection = self.left_requests_table.selectionModel()
        if not selection or not selection.hasSelection():
            QMessageBox.information(
                self,
                "Informazione",
                "Select a request from the table to view its details."
            )
            return
        
        selected_indexes = selection.selectedRows()
        if not selected_indexes:
            return
        
        # Prendi la prima riga selezionata
        row = selected_indexes[0].row()
        if row < 0 or not hasattr(self, 'left_requests_model'):
            return
        
        # Ottieni l'ID dalla prima colonna
        request_id_index = self.left_requests_model.index(row, 0)
        request_id_full = self.left_requests_model.data(request_id_index, Qt.DisplayRole)
        
        # Se l'ID è troncato, recuperalo dai dati originali
        if request_id_full and "..." in str(request_id_full):
            # Cerca l'ID completo nei messaggi in memoria
            if hasattr(self, 'messages_data'):
                prefix = str(request_id_full).replace("...", "")
                for msg in self.messages_data:
                    msg_id = str(msg.get("id", ""))
                    if msg_id.startswith(prefix):
                        request_id_full = msg_id
                        break
        
        if not request_id_full:
            QMessageBox.warning(
                self,
                "Attenzione",
                "Impossibile determinare l'ID della richiesta selezionata."
            )
            return
        
        # Apri la finestra di dettaglio
        self.open_request_detail(str(request_id_full))
    
    def open_request_detail(self, request_id: str):
        """Apre la finestra di dettaglio per una richiesta"""
        if not HAS_REQUEST_DETAIL_WINDOW:
            return
        
        # Pulisci l'ID da eventuali caratteri di formattazione
        request_id = str(request_id).strip()
        
        # Rimuovi eventuali "..." se presenti
        if "..." in request_id:
            # Prova a recuperare l'ID completo dai messaggi
            if hasattr(self, 'messages_data'):
                for msg in self.messages_data:
                    msg_id = str(msg.get("id", ""))
                    if msg_id.startswith(request_id.replace("...", "")):
                        request_id = msg_id
                        break
        
        # Apri la finestra di dettaglio
        detail_window = RequestDetailWindow(request_id, parent=self)
        show_auxiliary_window(detail_window)
    
    
    def go_back(self):
        """Porta il focus alla dashboard (sezione resta aperta o in icona)."""
        self.go_back_to_dashboard()
    
    def apply_stylesheet(self):
        """Applica lo stylesheet con tema scuro"""
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
            QWidget {
                background: transparent;
            }
            QStackedWidget {
                background: transparent;
            }
        """)

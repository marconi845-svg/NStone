"""
Nstone LLM - Finestra Centro Ordini
Gestione conferme d'ordine (SQLite + Gmail IMAP) e help neurale
"""
import os
import sys
import csv
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional
from ui.common.section_window import SectionDialog, SectionMainWindow
from ui.common.window_helpers import show_auxiliary_window
from ui.common.neural_stats_sidebar import NeuralStatsPollWorker, apply_neural_stats_to_labels
from ui.common.worker_lifecycle import (
    ORDERS_WORKER_ATTRS,
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
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTableView,
                             QLineEdit, QHeaderView, QProgressBar, QScrollArea,
                             QMessageBox, QTextEdit, QStackedWidget, QListWidget,
                             QRadioButton, QButtonGroup, QGridLayout, QComboBox)
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
from PyQt5.QtGui import QFont, QColor, QBrush
import subprocess
import platform
from llm.ai_assistant import AIAssistant

try:
    from ui.windows.admin.database_window import DatabaseWindow
    HAS_DATABASE_WINDOW = True
except ImportError:
    HAS_DATABASE_WINDOW = False
    DatabaseWindow = None  # type: ignore

_HTTP_QUICK = 2.0
_PENDING_ORDER_STATUSES = frozenset(
    {"new", "nuovo", "pending", "in attesa", "da confermare", "received"}
)
_ORDER_SCROLL_STYLE = """
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
"""
_ORDER_TEXTEDIT_STYLE = """
    QTextEdit {
        background-color: #0a0a1a;
        color: #E8E8E8;
        border: 1px solid #2a2a3a;
        border-radius: 6px;
        padding: 8px;
        font-size: 12px;
    }
"""
_ORDER_DETAIL_BTN_STYLE = """
    QPushButton {
        color: #FFFFFF;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 12px;
        font-weight: bold;
        text-align: left;
    }
    QPushButton:disabled {
        background-color: #3a3a4a;
        color: #777;
        border-color: #4a4a5a;
    }
"""


class OrdersTableModel(QAbstractTableModel):
    """Model per la tabella orders con dati da CSV (stesso di QuotationsTableModel)"""

    def __init__(self, data, headers, parent=None, row_colors=None, row_tooltips=None):
        super().__init__(parent)
        self._data = data
        self._headers = headers
        self._row_colors = row_colors or {}
        self._row_tooltips = row_tooltips or {}

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
                return str(self._data[row][col])

        if role == Qt.ForegroundRole:
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


class SentOrdersLoadWorker(QThread):
    """Carica ordini inviati da SQLite in background (no scan JSON ripetuto)."""

    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(list, str)

    def __init__(self, orders_dir: Path, *, import_json: bool = False, parent=None):
        super().__init__(parent)
        self.orders_dir = orders_dir
        self.import_json = import_json

    def run(self):
        try:
            if self.isInterruptionRequested():
                return
            from modules.orders_database import (
                get_sent_confirmation_fingerprint,
                import_sent_confirmations_from_json_dir,
                list_sent_confirmation_orders,
            )

            if self.import_json:
                import_sent_confirmations_from_json_dir(self.orders_dir)

            if self.isInterruptionRequested():
                return
            orders = list_sent_confirmation_orders(limit=100)
            if not orders and self.orders_dir.exists():
                orders = self._legacy_json_sent_orders()

            table_data = []
            for order in orders:
                ts = str(order.get("sent_timestamp", ""))
                if len(ts) > 19:
                    ts = ts[:19]
                table_data.append([
                    order.get("order_id", ""),
                    order.get("client", ""),
                    ts,
                    order.get("sent_status", "Sent"),
                    str(order.get("status", "") or ""),
                ])

            fingerprint = get_sent_confirmation_fingerprint()
            if orders and fingerprint == "0":
                fingerprint = f"{len(orders)}:{table_data[0][0] if table_data else ''}"
            if not self.isInterruptionRequested():
                self.result_ready.emit(table_data, fingerprint)
        except Exception as exc:
            print(f"SentOrdersLoadWorker error: {exc}")
            self.result_ready.emit([], "error")

    def _legacy_json_sent_orders(self):
        sent_orders = []
        for order_file in self.orders_dir.glob("order_*.json"):
            try:
                with open(order_file, "r", encoding="utf-8") as handle:
                    order_data = json.load(handle)
                sent_email = order_data.get("sent_confirmation_email")
                if sent_email and isinstance(sent_email, dict) and sent_email.get("sent"):
                    sent_orders.append(order_data)
            except (json.JSONDecodeError, OSError):
                continue
        sent_orders.sort(
            key=lambda x: x.get("sent_confirmation_email", {}).get("timestamp", ""),
            reverse=True,
        )
        result = []
        for order in sent_orders[:100]:
            sent_info = order.get("sent_confirmation_email", {})
            result.append(
                {
                    "order_id": order.get("id", "UNKNOWN"),
                    "client": order.get("from", ""),
                    "sent_timestamp": sent_info.get("timestamp", ""),
                    "sent_status": "Sent" if sent_info.get("sent") else "Error",
                }
            )
        return result


class GmailCheckWorker(QThread):
    """Worker IMAP Gmail (solo I/O; creato sempre dal main thread Qt)."""

    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        try:
            if self.isInterruptionRequested():
                return
            from modules.orders_imap_service import check_gmail_orders

            result = check_gmail_orders()
            if not self.isInterruptionRequested():
                self.result_ready.emit(result)
        except ImportError as exc:
            self.error.emit(f"Impossibile importare check_gmail_orders: {exc}")
        except Exception as exc:
            self.error.emit(f"Errore controllo email: {exc}")


class OrdersWindow(SectionDialog):
    """Finestra Centro Ordini completa con navigazione tra sezioni"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Order Center")
        self.setMinimumSize(1800, 1000)
        self.setModal(False)
        
        project_root = Path(__file__).resolve().parents[3]
        self.project_root = project_root
        
        # Percorsi CSV
        self.csv_dir = Path(__file__).parent / "csv_data"
        self.csv_dir.mkdir(exist_ok=True)
        self.orders_csv = self.csv_dir / "orders.csv"
        
        self.logs_dir = project_root / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        self.orders_dir = self.logs_dir / "orders"
        self.orders_dir.mkdir(exist_ok=True)
        self.last_order_file = self.logs_dir / "last_order.json"
        self.gmail_orders_status_file = self.logs_dir / "gmail_orders_status.json"
        self.orders_services_status_file = self.logs_dir / "orders_services_status.json"
        
        # Dati
        self.table_data = []
        self.current_section = "Orders"
        self._detail_panel_collapsed = False
        
        # Inizializza CSV se non esiste
        self.init_csv_file()

        try:
            from modules.orders_database import init_database
            init_database()
        except Exception as e:
            print(f"Warning: init database ordini: {e}")

        self._orders_meta = []
        self._gmail_poll_manual = False
        self.gmail_check_worker = None
        self._sent_orders_worker = None
        self._sent_orders_fingerprint = ""
        self._sent_orders_json_imported = False
        self._sent_orders_meta = []
        self._selected_order_id: Optional[str] = None
        self._neural_stats_worker = None
        self._ui_active = False
        self._updating_table = False
        self._ai_worker = None
        self._order_ai_worker = None

        self.gmail_check_timer = QTimer(self)
        self.gmail_check_timer.timeout.connect(self._gmail_timer_tick)
        self.manage_section_timer(self.gmail_check_timer, self._gmail_poll_interval_ms())

        self.gmail_monitor_timer = QTimer(self)
        self.gmail_monitor_timer.timeout.connect(self.refresh_gmail_monitor_panel)
        self.manage_section_timer(self.gmail_monitor_timer, 15000)

        self.neural_stats_timer = QTimer(self)
        self.neural_stats_timer.timeout.connect(self.update_neural_stats)
        self.manage_section_timer(self.neural_stats_timer, 45000)
        
        self.init_ui()
        self.apply_stylesheet()

    def on_section_shown(self) -> None:
        self._ui_active = True
        if hasattr(self, "left_orders_table"):
            self.load_orders_from_files(maintenance=True)
        self.load_sent_orders_refresh(force=True)
        self.update_neural_stats()
        self.refresh_gmail_monitor_panel()
        QTimer.singleShot(800, self._gmail_timer_tick)

    def on_section_hidden(self) -> None:
        self._ui_active = False
        if getattr(self, "_fast_section_hide", False):
            return
        wait_workers(self, ORDERS_WORKER_ATTRS, timeout_ms=1500)

    def pause_for_system_suspend(self) -> None:
        """Sleep/ibernazione PC: ferma worker, sezione resta aperta."""
        self.pause_session_timers()
        wait_workers(self, ORDERS_WORKER_ATTRS, timeout_ms=3000)

    def resume_after_system_suspend(self) -> None:
        """Ripresa dopo sleep: riattiva timer e refresh leggero."""
        if not self.isVisible():
            return
        self._ui_active = True
        self.resume_session_timers()
        QTimer.singleShot(800, self._refresh_after_system_resume)

    def _refresh_after_system_resume(self) -> None:
        if not is_ui_active(self):
            return
        self.refresh_gmail_monitor_panel()
        self.load_orders_from_files(maintenance=False)
        self.load_sent_orders_refresh(force=True)
        
    def init_csv_file(self):
        """Inizializza il file CSV con dati di esempio se non esiste"""
        if not self.orders_csv.exists() or os.path.getsize(self.orders_csv) == 0:
            headers = ["OrderID", "Client", "Product", "Machine", "Status", "Scheduled"]
            with open(self.orders_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                # Dati di esempio
                sample_data = [
                    ["ORD-2025-882", "Cliente Test 01", "Top Cucina Calacatta Gold", "Linea Taglio 01", "In Lavorazione", "Oggi, 14:30"]
                ]
                writer.writerows(sample_data)
    
    def load_orders_from_files(self, *, maintenance: bool = False):
        """
        Carica gli ordini dal database SQLite (nstonellm.db)
        Fallback a file JSON se database non disponibile
        Ordina per timestamp decrescente — solo gli ultimi N (default 5).

        maintenance=True: purge spam + backfill (solo apertura sezione / pulsante Aggiorna).
        """
        if not is_ui_active(self):
            return
        if not hasattr(self, 'left_orders_model') or not hasattr(self, 'left_orders_table'):
            return

        selected_id = self._selected_order_id
        orders_data = []
        self._orders_meta = []

        sqlite_loaded_ok = False
        try:
            import sqlite3
            from pathlib import Path

            from modules.orders_database import (
                backfill_orders_from_email_logs,
                delete_orders_not_visible_in_table,
                order_visible_in_orders_table,
                orders_table_visibility_sql,
            )
            from modules.orders_imap_service import get_orders_table_max_rows

            table_max = get_orders_table_max_rows()
            project_root = Path(__file__).resolve().parents[3]
            db_path = project_root / "data" / "nstonellm.db"
            
            if db_path.exists():
                try:
                    if maintenance:
                        delete_orders_not_visible_in_table()
                        backfill_orders_from_email_logs(limit=table_max)

                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()

                    visibility = orders_table_visibility_sql()
                    cursor.execute(
                        f"""
                        SELECT order_id, client, client_email, product, status,
                               created_at, email_subject, email_body
                        FROM orders
                        WHERE 1=1 {visibility}
                        ORDER BY order_id DESC
                        LIMIT ?
                        """
                        ,
                        (table_max,),
                    )
                    
                    rows = cursor.fetchall()
                    conn.close()
                    sqlite_loaded_ok = True
                    
                    # Converti in formato tabella
                    for row in rows:
                        timestamp = str(row['created_at'] or "")
                        from_email = str(row['client_email'] or row['client'] or "")
                        subject = str(row['email_subject'] or row['product'] or "")
                        status = str(row['status'] or "NEW")
                        
                        # Formatta il timestamp (rimuovi microsecondi se presenti)
                        if timestamp and len(timestamp) > 19:
                            timestamp = timestamp[:19]
                        
                        # Limita subject a 100 caratteri
                        if subject and len(subject) > 100:
                            subject = subject[:100] + "..."
                        
                        orders_data.append([
                            timestamp,
                            from_email,
                            subject,
                            status,
                        ])
                        self._orders_meta.append({
                            "order_id": row["order_id"],
                            "client_email": from_email,
                            "subject": row["email_subject"] or row["product"] or "",
                        })

                except sqlite3.Error as e:
                    print(f"Errore lettura database: {e}, fallback a JSON")
                    # Fallback a JSON se database non disponibile
            else:
                print("Database non trovato, fallback a JSON")

            # JSON solo se il DB non esiste o la lettura SQLite è fallita (0 righe filtrate = OK)
            if not sqlite_loaded_ok and not orders_data:
                order_files = list(self.orders_dir.glob("order_*.json"))
                orders = []
                for order_file in order_files:
                    try:
                        with open(order_file, 'r', encoding='utf-8') as f:
                            order_data = json.load(f)
                            if not order_visible_in_orders_table(
                                email_subject=str(order_data.get("subject") or ""),
                                product=str(order_data.get("product") or ""),
                                status=str(order_data.get("status") or "NEW"),
                                quotation_case_id=str(order_data.get("quotation_case_id") or ""),
                            ):
                                continue
                            orders.append(order_data)
                    except (json.JSONDecodeError, Exception) as e:
                        print(f"Errore nella lettura di {order_file.name}: {e}")
                        continue

                orders.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
                orders = orders[:table_max]

                for order in orders:
                    timestamp = str(order.get("timestamp") or "")
                    from_email = str(order.get("from") or "")
                    subject = str(order.get("subject") or "")
                    status = str(order.get("status") or "NEW")

                    if len(timestamp) > 19:
                        timestamp = timestamp[:19]
                    if len(subject) > 100:
                        subject = subject[:100] + "..."

                    orders_data.append([timestamp, from_email, subject, status])

        except Exception as e:
            print(f"Errore nel caricamento degli ordini: {e}")

        headers = ["Date/Time", "Client", "Subject", "Status"]
        self._updating_table = True
        try:
            self.left_orders_model = OrdersTableModel(orders_data, headers)
            self.left_orders_table.setModel(self.left_orders_model)
            self.left_orders_table.horizontalHeader().setStretchLastSection(True)
            sm = self.left_orders_table.selectionModel()
            if sm is not None:
                try:
                    sm.selectionChanged.disconnect(self._on_order_selection_changed)
                except TypeError:
                    pass
                sm.selectionChanged.connect(self._on_order_selection_changed)
                if selected_id:
                    for row, meta in enumerate(self._orders_meta):
                        if str(meta.get("order_id")) == str(selected_id):
                            idx = self.left_orders_model.index(row, 0)
                            sm.select(
                                idx,
                                QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
                            )
                            break
        finally:
            self._updating_table = False

        if selected_id:
            try:
                from modules.orders_database import get_order_by_order_id

                self._populate_order_detail(get_order_by_order_id(selected_id))
            except Exception:
                pass
    
    def update_last_order_row(self):
        """
        Aggiorna solo la prima riga della tabella Incoming Orders leggendo logs/last_order.json
        Non ricarica tutti i file, solo aggiorna l'ultimo ordine inviato.
        """
        if not hasattr(self, 'left_orders_model') or not hasattr(self, 'left_orders_table'):
            return
        
        try:
            # Leggi il file last_order.json
            if not self.last_order_file.exists():
                # File non esiste, mostra messaggio nella prima riga
                headers = ["Date/Time", "Client", "Subject", "Status"]
                no_data_message = ["-", "-", "No recent order", "-"]
                
                # Se la tabella è vuota, crea una nuova con il messaggio
                if not hasattr(self.left_orders_model, '_data') or len(self.left_orders_model._data) == 0:
                    self.left_orders_model = OrdersTableModel([no_data_message], headers)
                else:
                    # Aggiorna solo la riga 0 mantenendo le altre righe
                    existing_data = [row.copy() if isinstance(row, list) else row for row in self.left_orders_model._data]
                    if len(existing_data) > 0:
                        existing_data[0] = no_data_message
                    else:
                        existing_data = [no_data_message]
                    self.left_orders_model = OrdersTableModel(existing_data, headers)
                
                self.left_orders_table.setModel(self.left_orders_model)
                self.left_orders_table.horizontalHeader().setStretchLastSection(True)
                return
            
            # Apri e leggi il file JSON
            with open(self.last_order_file, 'r', encoding='utf-8') as f:
                order_data = json.load(f)
            
            # Estrai i dati
            from_email = order_data.get("from", "")
            subject = order_data.get("subject", "")
            timestamp = order_data.get("timestamp", "")
            status = order_data.get("status", "NEW")
            
            # Formatta il timestamp (rimuovi microsecondi se presenti)
            if timestamp and len(timestamp) > 19:
                timestamp = timestamp[:19]
            
            # Limita subject a 100 caratteri
            if subject and len(subject) > 100:
                subject = subject[:100] + "..."
            
            # Prepara la nuova riga
            new_row = [timestamp, from_email, subject, status]
            headers = ["Date/Time", "Client", "Subject", "Status"]
            
            # Ottieni i dati esistenti dalla tabella
            if hasattr(self.left_orders_model, '_data') and len(self.left_orders_model._data) > 0:
                # Tabella ha già righe: aggiorna solo la riga 0 mantenendo le altre righe
                existing_data = [row.copy() if isinstance(row, list) else row for row in self.left_orders_model._data]
                existing_data[0] = new_row
                self.left_orders_model = OrdersTableModel(existing_data, headers)
            else:
                # Tabella vuota: crea la prima riga
                self.left_orders_model = OrdersTableModel([new_row], headers)
            
            # Aggiorna la vista
            self.left_orders_table.setModel(self.left_orders_model)
            self.left_orders_table.horizontalHeader().setStretchLastSection(True)
            
        except json.JSONDecodeError as e:
            print(f"Errore nel parsing del file last_order.json: {e}")
            # Mostra messaggio di errore nella prima riga
            headers = ["Date/Time", "Client", "Subject", "Status"]
            error_message = ["-", "-", f"JSON parse error: {str(e)}", "-"]
            if hasattr(self.left_orders_model, '_data') and len(self.left_orders_model._data) > 0:
                existing_data = [row.copy() if isinstance(row, list) else row for row in self.left_orders_model._data]
                existing_data[0] = error_message
                self.left_orders_model = OrdersTableModel(existing_data, headers)
            else:
                self.left_orders_model = OrdersTableModel([error_message], headers)
            self.left_orders_table.setModel(self.left_orders_model)
            self.left_orders_table.horizontalHeader().setStretchLastSection(True)
        except Exception as e:
            print(f"Errore nella lettura del file last_order.json: {e}")
            # Mostra messaggio di errore nella prima riga
            headers = ["Date/Time", "Client", "Subject", "Status"]
            error_message = ["-", "-", f"Error: {str(e)}", "-"]
            if hasattr(self.left_orders_model, '_data') and len(self.left_orders_model._data) > 0:
                existing_data = [row.copy() if isinstance(row, list) else row for row in self.left_orders_model._data]
                existing_data[0] = error_message
                self.left_orders_model = OrdersTableModel(existing_data, headers)
            else:
                self.left_orders_model = OrdersTableModel([error_message], headers)
            self.left_orders_table.setModel(self.left_orders_model)
            self.left_orders_table.horizontalHeader().setStretchLastSection(True)
    
    def _gmail_poll_interval_ms(self) -> int:
        """Intervallo polling IMAP (default 5 min). Gemini non viene usato nel poll automatico."""
        try:
            from modules.orders_imap_service import get_orders_imap_settings
            seconds = get_orders_imap_settings().get("gmail_poll_seconds", 300)
            return max(60, int(seconds)) * 1000
        except Exception:
            return 300000

    def _set_poll_button_busy(self, busy: bool) -> None:
        btn = getattr(self, "poll_gmail_btn", None)
        if not btn:
            return
        if busy:
            btn.setEnabled(False)
            btn.setText("⏳ Polling Gmail…")
        else:
            btn.setEnabled(True)
            btn.setText("📥 Poll Gmail Inbox (orders)")

    def _gmail_timer_tick(self) -> None:
        """Poll IMAP locale solo se lo scheduler globale non è attivo; altrimenti refresh UI."""
        if not is_ui_active(self):
            return
        try:
            from ui.common.gmail_imap_scheduler import is_gmail_imap_scheduler_active

            if is_gmail_imap_scheduler_active():
                self.refresh_gmail_monitor_panel()
                return
        except Exception:
            pass
        self.check_new_gmail_orders_async()

    def check_new_gmail_orders_async(self):
        """
        Avvia il controllo email in un thread separato per evitare freeze UI.
        Deve essere invocato solo dal main thread Qt (QTimer / click UI).
        """
        if QThread.currentThread() != self.thread():
            QTimer.singleShot(0, self.check_new_gmail_orders_async)
            return
        if not is_ui_active(self):
            return
        if self.gmail_check_worker and self.gmail_check_worker.isRunning():
            return
        self._set_poll_button_busy(True)

        worker = GmailCheckWorker(parent=self)
        worker.result_ready.connect(self.on_gmail_check_finished)
        worker.error.connect(self.on_gmail_check_error)
        # Cleanup SOLO sul finished nativo (thread realmente terminato)
        worker.finished.connect(lambda: setattr(self, "gmail_check_worker", None))
        worker.finished.connect(worker.deleteLater)
        self.gmail_check_worker = worker
        worker.start()
    
    def on_gmail_check_finished(self, result: dict):
        """
        Callback quando il controllo email è completato
        """
        if not is_ui_active(self):
            return
        self._set_poll_button_busy(False)
        try:
            try:
                from ui.common.background_services import (
                    record_service_tick,
                    register_service,
                    set_service_running,
                )

                register_service("orders_imap", "Poll Gmail (ordini + preventivi inbound)")
                set_service_running("orders_imap", True)
                record_service_tick(
                    "orders_imap",
                    ok=result.get("status") != "ERROR",
                    error=str(result.get("error_message") or "") or None,
                )
            except Exception:
                pass

            # Salva stato + log poll condiviso (scheduler globale + UI)
            try:
                from ui.common.gmail_imap_poll_log import record_imap_poll_result

                record_imap_poll_result(
                    result,
                    source="manual" if getattr(self, "_gmail_poll_manual", False) else "auto",
                )
            except Exception as e:
                print(f"Errore salvataggio stato Gmail: {e}")

            self.refresh_gmail_monitor_panel()
            
            # Ricarica ordini per mostrare eventuali nuovi ordini
            self.load_orders_from_files()
            
            if getattr(self, "_gmail_poll_manual", False):
                self._gmail_poll_manual = False
                if result.get("status") == "ERROR":
                    QMessageBox.warning(
                        self,
                        "Poll Gmail",
                        result.get("error_message") or "Error during IMAP poll.",
                    )
                else:
                    n_proc = result.get("emails_processed", 0)
                    n_ord = result.get("orders_saved", 0)
                    QMessageBox.information(
                        self,
                        "Poll Gmail",
                        f"Emails processed: {n_proc}\n"
                        f"New orders saved: {n_ord}\n"
                        f"Confirmations sent: {result.get('confirmations_sent', 0)}\n\n"
                        f"IMAP filter: orders + customer confirmations "
                        f"(config: orders.subject_keywords).",
                    )
        except Exception as e:
            print(f"Errore gestione risultato controllo email: {e}")
    
    def on_gmail_check_error(self, error_msg: str):
        """
        Callback quando il controllo email genera un errore
        """
        if not is_ui_active(self):
            return
        self._set_poll_button_busy(False)
        self._gmail_poll_manual = False
        print(f"⚠️ Errore controllo email: {error_msg}")
        QMessageBox.warning(self, "Poll Gmail", error_msg)
        # Non mostrare QMessageBox per non bloccare l'UI durante operazioni automatiche
    
    def check_new_gmail_orders(self):
        """
        Poll manuale casella Gmail (ordini) — usa thread per non bloccare la GUI
        """
        self._gmail_poll_manual = True
        self.check_new_gmail_orders_async()

    def _get_selected_order_rows(self) -> list:
        """Indici riga selezionati nella tabella ordini."""
        if not hasattr(self, "left_orders_table"):
            return []
        selection = self.left_orders_table.selectionModel()
        if not selection:
            return []
        indexes = selection.selectedRows()
        if indexes:
            return sorted({idx.row() for idx in indexes if idx.row() >= 0})
        current = selection.currentIndex()
        if current.isValid():
            return [current.row()]
        return []

    def _get_order_ids_for_rows(self, rows: list) -> list:
        ids = []
        meta = getattr(self, "_orders_meta", None) or []
        for row in rows:
            if 0 <= row < len(meta):
                oid = meta[row].get("order_id")
                if oid:
                    ids.append(oid)
        return ids

    def delete_selected_orders(self):
        """Elimina dalla lista (e dal DB) gli ordini selezionati."""
        rows = self._get_selected_order_rows()
        if not rows:
            QMessageBox.information(
                self,
                "Delete order",
                "Select one or more rows in the orders table.",
            )
            return

        order_ids = list(dict.fromkeys(self._get_order_ids_for_rows(rows)))
        if not order_ids:
            QMessageBox.warning(
                self,
                "Delete order",
                "Unable to resolve order IDs for selected rows.",
            )
            return

        meta = getattr(self, "_orders_meta", []) or []
        preview_lines = []
        for row in rows[:5]:
            if 0 <= row < len(meta):
                subj = (meta[row].get("subject") or "")[:60]
                preview_lines.append(f"• {subj or meta[row].get('order_id', '?')}")
        if len(rows) > 5:
            preview_lines.append(f"… and {len(rows) - 5} more")

        reply = QMessageBox.question(
            self,
            "Delete order",
            f"Delete {len(order_ids)} order(s) from the database?\n\n"
            + "\n".join(preview_lines)
            + "\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from modules.orders_database import delete_orders

            deleted = delete_orders(order_ids)
        except Exception as e:
            QMessageBox.critical(self, "Delete order", f"Error: {e}")
            return

        project_root = Path(__file__).resolve().parents[3]
        orders_log_dir = project_root / "logs" / "orders"
        for oid in order_ids:
            for pattern in (f"order_{oid}.json", f"{oid}.json"):
                path = orders_log_dir / pattern
                if path.is_file():
                    try:
                        path.unlink()
                    except OSError:
                        pass

        self.load_orders_from_files()
        QMessageBox.information(
            self,
            "Delete order",
            f"Deleted {deleted} order(s).",
        )

    def _get_selected_order_id(self) -> Optional[str]:
        rows = self._get_selected_order_rows()
        if not rows:
            return None
        ids = self._get_order_ids_for_rows([rows[0]])
        return ids[0] if ids else None

    def run_confirmation_pipeline_on_selected(self):
        """Pipeline conferma: stock catalogo + email NStone per ordine selezionato."""
        order_id = self._get_selected_order_id()
        if not order_id:
            QMessageBox.warning(
                self, "Confirm Order", "Select an order from the table.",
            )
            return
        try:
            from modules.orders_database import get_order_by_order_id
            from modules.order_confirmation_pipeline import (
                process_client_confirmation_email,
            )

            order = get_order_by_order_id(order_id)
            if not order:
                QMessageBox.warning(self, "Confirm Order", "Order not found in database.")
                return

            email_data = {
                "from": order.get("client_email") or order.get("client", ""),
                "subject": f"Re: {order.get('email_subject') or order.get('product', '')}",
                "body": (
                    "Confermo l'ordine come da vostro preventivo. "
                    "Procedete con la lavorazione."
                ),
                "timestamp": datetime.now().isoformat(),
            }
            ok = process_client_confirmation_email(email_data, force_send=True, use_llm=True)
            self.load_orders_from_files()
            if ok:
                QMessageBox.information(
                    self,
                    "Confirm Order",
                    "Stock verified and NStone confirmation email sent to the customer.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "Confirm Order",
                    "Pipeline not completed (Gemini API, stock, or SMTP send). "
                    "Check the logs.",
                )
        except Exception as e:
            QMessageBox.critical(self, "Confirm Order", str(e))

    def classify_selected_order_with_ai(self):
        """Gemini on-demand sull'ordine selezionato (non nel poll IMAP)."""
        order_id = self._get_selected_order_id()
        if not order_id:
            QMessageBox.warning(
                self,
                "Orders",
                'Select an order in the "Incoming Orders" table.',
            )
            return

        class _OrderAIWorker(QThread):
            result_ready = pyqtSignal(dict)
            error = pyqtSignal(str)

            def __init__(self, oid: str, parent=None):
                super().__init__(parent)
                self.order_id = oid

            def run(self):
                try:
                    from modules.orders_database import get_order_by_order_id, update_order_ai_fields
                    from modules.order_ai_analysis import (
                        analyze_order_email_with_ai,
                        OrderAIAnalysisError,
                    )

                    order = get_order_by_order_id(self.order_id)
                    if not order:
                        self.error.emit(f"Ordine {self.order_id} non trovato nel database.")
                        return
                    analysis = analyze_order_email_with_ai(order)
                    update_order_ai_fields(self.order_id, analysis)
                    self.result_ready.emit({"order_id": self.order_id, "analysis": analysis})
                except OrderAIAnalysisError as exc:
                    self.error.emit(str(exc))
                except Exception as exc:
                    self.error.emit(str(exc))

        if getattr(self, "_order_ai_worker", None) and self._order_ai_worker.isRunning():
            QMessageBox.information(self, "Orders", "AI analysis already in progress…")
            return

        if hasattr(self, "order_detail_classify_btn"):
            self.order_detail_classify_btn.setEnabled(False)
        if hasattr(self, "order_detail_draft") and self._selected_order_id == order_id:
            self.order_detail_draft.setPlainText("AI classification in progress…")

        prev = getattr(self, "_order_ai_worker", None)
        if prev is not None and prev.isRunning():
            prev.wait(500)
        worker = _OrderAIWorker(order_id, self)
        worker.result_ready.connect(self._on_order_ai_finished)
        worker.error.connect(lambda msg: QMessageBox.critical(self, "AI Analysis", msg))
        # Cleanup SOLO sul finished nativo (thread realmente terminato)
        worker.finished.connect(lambda: setattr(self, "_order_ai_worker", None))
        worker.finished.connect(worker.deleteLater)
        self._order_ai_worker = worker
        worker.start()

    def _on_order_ai_finished(self, payload: dict):
        analysis = payload.get("analysis", {})
        order_id = payload.get("order_id")
        if hasattr(self, "order_detail_classify_btn"):
            self.order_detail_classify_btn.setEnabled(True)

        summary = (
            f"Materiale: {analysis.get('materiale', '—')}\n"
            f"Quantity (sqm): {analysis.get('quantita_mq', '—')}\n"
            f"Macchina: {analysis.get('machine', '—')}\n\n"
            f"{analysis.get('note', '')}"
        )
        if order_id == self._selected_order_id and hasattr(self, "order_detail_draft"):
            self.order_detail_draft.setPlainText(summary.strip())

        self.load_orders_from_files()
        if order_id == self._selected_order_id:
            try:
                from modules.orders_database import get_order_by_order_id

                self._populate_order_detail(get_order_by_order_id(str(order_id)))
            except Exception:
                pass

        QMessageBox.information(
            self,
            "Classification Complete",
            f"Ordine: {order_id}\n\n{summary}",
        )
    
    def refresh_gmail_monitor_panel(self) -> None:
        """Aggiorna riepilogo stato + log poll IMAP (tempo reale)."""
        if not is_ui_active(self):
            return
        self.update_gmail_orders_status()
        self.update_gmail_poll_log_panel()

    def update_gmail_poll_log_panel(self) -> None:
        if not hasattr(self, "gmail_poll_log_view"):
            return
        try:
            from ui.common.gmail_imap_poll_log import get_poll_log_text

            text = get_poll_log_text(max_lines=60)
            view = self.gmail_poll_log_view
            at_bottom = view.verticalScrollBar().value() >= view.verticalScrollBar().maximum() - 8
            view.setPlainText(text)
            if at_bottom or not view.toPlainText().strip():
                view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        except Exception as exc:
            self.gmail_poll_log_view.setPlainText(f"Poll log error: {exc}")

    def update_gmail_orders_status(self):
        """
        Aggiorna il monitor pipeline ordini (IMAP + servizi background).
        """
        if not hasattr(self, 'gmail_orders_status_label'):
            return

        label_style_idle = """
            QLabel {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #888899;
                padding: 10px;
                font-size: 11px;
            }
        """

        def _append_background_services(lines: list) -> None:
            try:
                from ui.common.background_services import get_services_snapshot

                snap = get_services_snapshot()
                if not snap:
                    return
                lines.append("")
                lines.append("Servizi automatici:")
                for name, data in sorted(snap.items()):
                    desc = (data.get("description") or name)[:48]
                    running = "attivo" if data.get("running") else "fermo"
                    ticks = int(data.get("tick_count") or 0)
                    lines.append(f"  • {desc}: {running} ({ticks} cicli)")
                    err = data.get("last_error")
                    if err:
                        lines.append(f"    errore: {str(err)[:80]}")
            except Exception:
                pass

        try:
            status_lines: list = []
            status_data = None

            try:
                from ui.common.gmail_imap_poll_log import read_status_snapshot

                status_data = read_status_snapshot()
            except Exception:
                status_data = None

            if status_data is None and self.gmail_orders_status_file.exists():
                with open(self.gmail_orders_status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)

            if status_data is None:
                status_lines.append("IMAP ordini: in attesa del primo poll")
                status_lines.append("(poll automatico globale attivo all'avvio app)")
                _append_background_services(status_lines)
                self.gmail_orders_status_label.setText("\n".join(status_lines))
                self.gmail_orders_status_label.setStyleSheet(label_style_idle)
                return

            try:
                from ui.common.gmail_imap_scheduler import is_gmail_imap_scheduler_active

                if is_gmail_imap_scheduler_active():
                    status_lines.append("Scheduler IMAP globale: attivo")
            except Exception:
                pass

            status = status_data.get("status", "UNKNOWN")
            last_check = status_data.get("last_check", "")
            last_email_from = status_data.get("last_email_from", "")
            last_email_subject = status_data.get("last_email_subject", "")
            error_message = status_data.get("error_message", "")
            poll_sec = status_data.get("poll_interval_seconds")
            imap_mode = status_data.get("imap_mode", "poll")
            imap_filter = status_data.get("imap_filter_summary") or status_data.get("imap_search", "")

            if status == "OK":
                status_lines.append("IMAP ordini: operativo")
            elif status == "ERROR":
                status_lines.append("IMAP ordini: errore")
            else:
                status_lines.append(f"IMAP ordini: {status}")

            if poll_sec:
                status_lines.append(f"Poll {imap_mode}: ogni {poll_sec}s")
            if imap_filter:
                if len(imap_filter) > 120:
                    imap_filter = imap_filter[:120] + "…"
                status_lines.append(f"Filtro IMAP: {imap_filter}")

            n_proc = status_data.get("emails_processed")
            n_ord = status_data.get("orders_saved")
            n_conf = status_data.get("confirmations_sent")
            if n_proc is not None:
                conf_part = f" · {n_conf or 0} conferme" if n_conf is not None else ""
                status_lines.append(f"Ultimo ciclo: {n_proc} email · {n_ord or 0} ordini{conf_part}")
            llm_poll = status_data.get("confirmation_use_llm_on_poll")
            if llm_poll is not None:
                status_lines.append(
                    f"Conferme su poll: {'LLM attivo' if llm_poll else 'rule-based (veloce)'}"
                )

            if last_check:
                if len(last_check) > 19:
                    last_check = last_check[:19]
                status_lines.append(f"Ultimo controllo: {last_check}")

            if last_email_from:
                status_lines.append(f"Ultima mail: {last_email_from}")

            if last_email_subject:
                subject_display = (
                    last_email_subject[:60] + "..."
                    if len(last_email_subject) > 60
                    else last_email_subject
                )
                status_lines.append(f"Subject: {subject_display}")

            if error_message:
                status_lines.append(f"IMAP Error: {error_message}")

            _append_background_services(status_lines)

            status_text = "\n".join(status_lines)

            if status == "OK":
                color = "#8FD4A0"
                border = "#2a4a3a"
            elif status == "ERROR":
                color = "#FF9999"
                border = "#4a2a2a"
            else:
                color = "#CCCCCC"
                border = "#2a2a3a"

            self.gmail_orders_status_label.setText(status_text)
            self.gmail_orders_status_label.setStyleSheet(f"""
                QLabel {{
                    background-color: #0a0a1a;
                    border: 1px solid {border};
                    border-radius: 6px;
                    color: {color};
                    padding: 10px;
                    font-size: 11px;
                }}
            """)
            
        except json.JSONDecodeError as e:
            error_text = f"Error parsing gmail_orders_status.json:\n{str(e)}"
            self.gmail_orders_status_label.setText(error_text)
            self.gmail_orders_status_label.setStyleSheet("""
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
            error_text = f"Error reading gmail_orders_status.json:\n{str(e)}"
            self.gmail_orders_status_label.setText(error_text)
            self.gmail_orders_status_label.setStyleSheet("""
                QLabel {
                    background-color: #0a0a1a;
                    border: 1px solid #FF0000;
                    border-radius: 6px;
                    color: #FF0000;
                    padding: 8px;
                    font-size: 11px;
                }
            """)
    
    def update_orders_services_status(self):
        """
        Aggiorna lo stato dei servizi legati agli ordini leggendo da logs/orders_services_status.json
        """
        if not hasattr(self, 'orders_services_status_label'):
            return
        
        try:
            # Leggi il file orders_services_status.json
            if not self.orders_services_status_file.exists():
                # File non esiste, mostra messaggio di attesa
                status_text = "In attesa di dati dal backend..."
                self.orders_services_status_label.setText(status_text)
                self.orders_services_status_label.setStyleSheet("""
                    QLabel {
                        background-color: #0a0a1a;
                        border: 1px solid #2a2a3a;
                        border-radius: 6px;
                        color: #AAAAAA;
                        padding: 8px;
                        font-size: 11px;
                    }
                """)
                return
            
            # Apri e leggi il file JSON
            with open(self.orders_services_status_file, 'r', encoding='utf-8') as f:
                status_data = json.load(f)
            
            # Estrai i dati dallo stato
            status = status_data.get("status", "UNKNOWN")
            last_check = status_data.get("last_check", "")
            last_event = status_data.get("last_event", "")
            error_message = status_data.get("error_message", "")
            
            # Costruisci il testo formattato
            status_lines = []
            status_lines.append(f"Stato: {status}")
            
            if last_check:
                # Formatta il timestamp dell'ultimo check
                if len(last_check) > 19:
                    last_check = last_check[:19]
                status_lines.append(f"Ultimo controllo: {last_check}")
            
            if last_event:
                status_lines.append(f"Ultimo evento: {last_event}")
            
            if error_message:
                status_lines.append(f"Error: {error_message}")
            
            status_text = "\n".join(status_lines)
            
            # Imposta il colore in base allo stato
            if status == "OK":
                color = "#00FF00"  # Verde per OK
            elif status == "ERROR":
                color = "#FF0000"  # Rosso per ERROR
            else:
                color = "#AAAAAA"  # Grigio per altri stati
            
            self.orders_services_status_label.setText(status_text)
            self.orders_services_status_label.setStyleSheet(f"""
                QLabel {{
                    background-color: #0a0a1a;
                    border: 1px solid #2a2a3a;
                    border-radius: 6px;
                    color: {color};
                    padding: 8px;
                    font-size: 11px;
                }}
            """)
            
        except json.JSONDecodeError as e:
            error_text = f"Error parsing orders_services_status.json:\n{str(e)}"
            self.orders_services_status_label.setText(error_text)
            self.orders_services_status_label.setStyleSheet("""
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
            error_text = f"Error reading orders_services_status.json:\n{str(e)}"
            self.orders_services_status_label.setText(error_text)
            self.orders_services_status_label.setStyleSheet("""
                QLabel {
                    background-color: #0a0a1a;
                    border: 1px solid #FF0000;
                    border-radius: 6px;
                    color: #FF0000;
                    padding: 8px;
                    font-size: 11px;
                }
            """)
    
    def load_sent_orders_refresh(self, *, force: bool = False) -> None:
        """Refresh pannello ordini inviati (SQLite, background thread)."""
        if not hasattr(self, "right_orders_model"):
            return
        worker = getattr(self, "_sent_orders_worker", None)
        if worker is not None and worker.isRunning():
            return

        import_json = not self._sent_orders_json_imported
        if import_json:
            self._sent_orders_json_imported = True

        worker = SentOrdersLoadWorker(
            self.orders_dir,
            import_json=import_json,
            parent=self,
        )
        worker.result_ready.connect(
            lambda rows, fp: self._on_sent_orders_loaded(rows, fp, force)
        )
        # Cleanup SOLO sul finished nativo (thread realmente terminato)
        worker.finished.connect(lambda: setattr(self, "_sent_orders_worker", None))
        worker.finished.connect(worker.deleteLater)
        self._sent_orders_worker = worker
        worker.start()

    def _on_sent_orders_loaded(self, table_data: list, fingerprint: str, force: bool) -> None:
        if not is_ui_active(self):
            return
        if not hasattr(self, "right_orders_table"):
            return
        if not force and fingerprint == self._sent_orders_fingerprint:
            return
        self._sent_orders_fingerprint = fingerprint
        self._apply_sent_orders_table(table_data)

    _SENT_ORDER_ACTIVE_STATUSES = frozenset({
        "new", "nuovo", "pending", "in attesa", "da confermare", "received",
        "confirmed", "confermato", "inviato", "in produzione",
    })

    def _apply_sent_orders_table(self, table_data: list) -> None:
        if not hasattr(self, "right_orders_model") or not hasattr(self, "right_orders_table"):
            return
        headers = ["Order ID", "Client", "Sent at", "Status"]
        display_rows = []
        row_colors: dict = {}
        row_tooltips: dict = {}
        self._sent_orders_meta = []
        for idx, row in enumerate(table_data):
            order_id, client, ts, sent_status = row[0], row[1], row[2], row[3]
            order_status = (row[4] if len(row) > 4 else "").strip().lower()
            risky = order_status in self._SENT_ORDER_ACTIVE_STATUSES
            self._sent_orders_meta.append(
                {"order_id": order_id, "risky": risky, "status": order_status}
            )
            if risky:
                sent_status = f"⚠️ {sent_status}"
                row_colors[idx] = "#FFB347"
                row_tooltips[idx] = (
                    "⚠️ Order still in progress: this record is the "
                    "trace of the confirmation sent to the customer."
                )
            display_rows.append([order_id, client, ts, sent_status])
        self.right_orders_model = OrdersTableModel(
            display_rows, headers, row_colors=row_colors, row_tooltips=row_tooltips
        )
        self.right_orders_table.setModel(self.right_orders_model)
        self.right_orders_table.horizontalHeader().setStretchLastSection(True)

    def load_sent_orders_from_files(self):
        """Compat: refresh manuale ordini inviati."""
        self.load_sent_orders_refresh(force=True)
    
    def delete_selected_sent_order(self):
        """Elimina la registrazione dell'email di conferma (DB + JSON legacy)."""
        if not hasattr(self, "right_orders_table"):
            return
        selected_indexes = self.right_orders_table.selectedIndexes()
        if not selected_indexes:
            QMessageBox.warning(
                self, "No Selection", "Select an order from the table first."
            )
            return
        row = selected_indexes[0].row()
        meta = (
            self._sent_orders_meta[row]
            if 0 <= row < len(self._sent_orders_meta)
            else {}
        )
        order_id = meta.get("order_id") or self.right_orders_model.data(
            self.right_orders_model.index(row, 0), Qt.DisplayRole
        )
        if not order_id:
            QMessageBox.warning(self, "Error", "Unable to get order ID.")
            return

        if meta.get("risky"):
            msg = (
                "⚠️ ORDER STILL IN PROGRESS\n\n"
                f"Order: {order_id}\n\n"
                "This record is the trace of the confirmation sent to the customer. "
                "It will be permanently removed from the database and JSON files "
                "(the order itself remains in the database).\n\n"
                "Delete anyway?"
            )
        else:
            msg = (
                f"Order: {order_id}\n\n"
                "Permanently remove the confirmation email send record? "
                "(the order remains in the database)"
            )
        reply = QMessageBox.question(
            self, "Delete Send Record", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from modules.orders_database import delete_sent_confirmation

            ok, message = delete_sent_confirmation(str(order_id), logs_dir=self.orders_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Deletion failed:\n{exc}")
            return

        if ok:
            self.load_sent_orders_refresh(force=True)
        else:
            QMessageBox.warning(self, "Deletion Failed", message)

    def show_sent_order_details(self, index=None):
        """
        Mostra i dettagli dell'email di conferma inviata per un ordine selezionato
        """
        if not hasattr(self, 'right_orders_table'):
            return
        
        # Se index non è fornito, usa la selezione corrente
        if index is None:
            selected_indexes = self.right_orders_table.selectedIndexes()
            if not selected_indexes:
                QMessageBox.warning(self, "No Selection", "Select an order from the table.")
                return
            index = selected_indexes[0]
        
        # Ottieni l'ID ordine dalla riga selezionata
        row = index.row()
        order_id = self.right_orders_model.data(self.right_orders_model.index(row, 0), Qt.DisplayRole)
        
        if not order_id:
            QMessageBox.warning(self, "Error", "Unable to get order ID.")
            return
        
        # Cerca dettaglio ordine (SQLite, fallback JSON legacy)
        order_data = None
        try:
            from modules.orders_database import get_order_sent_confirmation_detail

            order_data = get_order_sent_confirmation_detail(str(order_id))
        except Exception:
            order_data = None

        order_file = self.orders_dir / f"order_{order_id}.json"
        if order_data is None and order_file.exists():
            try:
                with open(order_file, "r", encoding="utf-8") as f:
                    order_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                order_data = None

        if order_data is None:
            QMessageBox.warning(
                self,
                "Not found",
                f"Sent order details not found for {order_id}.",
            )
            return
        
        # Estrai informazioni email inviata
        sent_email_info = order_data.get("sent_confirmation_email") or order_data.get(
            "confirmation_email"
        )

        if not sent_email_info or not sent_email_info.get("sent", False):
            QMessageBox.warning(
                self,
                "Email not sent",
                "This order has no sent confirmation email.",
            )
            return

        details_dialog = QDialog(self)
        details_dialog.setWindowTitle(f"Confirmation email — Order #{order_id}")
        details_dialog.setMinimumSize(700, 600)

        layout = QVBoxLayout(details_dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        details_dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1a2a;
            }
            QLabel {
                color: #FFFFFF;
            }
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 11px;
            }
        """)

        to_label = QLabel(f"<b>To:</b> {sent_email_info.get('to', 'N/A')}")
        to_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        layout.addWidget(to_label)

        subject_label = QLabel(f"<b>Subject:</b> {sent_email_info.get('subject', 'N/A')}")
        subject_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        layout.addWidget(subject_label)

        timestamp = sent_email_info.get("timestamp", "N/A")
        if isinstance(timestamp, str) and len(timestamp) > 19:
            timestamp = timestamp[:19]
        timestamp_label = QLabel(f"<b>Sent at:</b> {timestamp}")
        timestamp_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        layout.addWidget(timestamp_label)

        body_label = QLabel("<b>Body:</b>")
        body_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        layout.addWidget(body_label)

        body_text = QTextEdit()
        body_text.setReadOnly(True)
        body_text.setPlainText(sent_email_info.get("body", "N/A"))
        body_text.setMinimumHeight(300)
        layout.addWidget(body_text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
            }
        """)
        close_btn.clicked.connect(details_dialog.close)
        layout.addWidget(close_btn)

        show_auxiliary_window(details_dialog)
    
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
        
        # Sezione Orders - Conferme d'ordine
        orders_section = self.create_orders_section()
        self.stacked_widget.addWidget(orders_section)
        self.section_index_map["Orders"] = current_index
        current_index += 1
        
        # Sezione Help
        help_section = self.create_help_section()
        self.stacked_widget.addWidget(help_section)
        self.section_index_map["Help"] = current_index
        current_index += 1
        
        content_layout.addWidget(self.stacked_widget, 1)
        
        main_layout.addWidget(content_widget, 1)
        
        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)
        
        # Imposta sezione iniziale
        self.show_section("Orders")
        
    def create_top_bar(self):
        """Crea la top bar con Dashboard, logo e titolo"""
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
        dashboard_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
                border: 1px solid #4a4a5a;
            }
        """)
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
        
        title_label = QLabel("Order Center")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        title_layout.addWidget(title_label)
        
        subtitle_label = QLabel("• NEURAL SYNC ACTIVE")
        subtitle_label.setStyleSheet("color: #00FF00; font-size: 11px;")
        title_layout.addWidget(subtitle_label)
        
        top_layout.addLayout(title_layout)
        top_layout.addStretch()
        
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
        menu_scroll.setStyleSheet(_ORDER_SCROLL_STYLE)

        menu_content = QWidget()
        menu_content.setStyleSheet("background-color: #1a1a2a;")
        menu_layout = QVBoxLayout(menu_content)
        menu_layout.setContentsMargins(15, 20, 15, 20)
        menu_layout.setSpacing(10)
        
        # Titolo NAVIGATION
        nav_title = QLabel("NAVIGATION")
        nav_title.setStyleSheet("color: #AAAAAA; font-size: 12px; font-weight: bold; padding: 10px 0;")
        menu_layout.addWidget(nav_title)
        
        # Voci menu
        self.menu_items = []
        
        # Aggiungi voci menu
        self.menu_items.extend([
            ("Orders", "📦", 0),
            ("Help", "❓", 1),
        ])
        
        self.menu_buttons = {}
        for text, icon, section_idx in self.menu_items:
            button = QPushButton(f"{icon} {text}")
            button.setMinimumHeight(45)
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
            button.clicked.connect(lambda checked, name=text: self.show_section(name))
            menu_layout.addWidget(button)
            self.menu_buttons[text] = button
        
        menu_layout.addSpacing(20)
        
        # Neural Stats
        stats_title = QLabel("NEURAL STATS")
        stats_title.setStyleSheet("color: #AAAAAA; font-size: 12px; font-weight: bold; padding: 10px 0;")
        menu_layout.addWidget(stats_title)
        
        self.neural_stat_model = QLabel("Model: —")
        self.neural_stat_engine = QLabel("Engine: —")
        self.neural_stat_tps = QLabel("Tokens/s: —")
        self.neural_stat_queue = QLabel("Inference queue: —")
        self.neural_stat_pipeline = QLabel("Orders: —")
        for lbl in (
            self.neural_stat_model,
            self.neural_stat_engine,
            self.neural_stat_tps,
            self.neural_stat_queue,
            self.neural_stat_pipeline,
        ):
            lbl.setStyleSheet("color: #CCCCCC; font-size: 11px;")
            lbl.setWordWrap(True)
            menu_layout.addWidget(lbl)

        menu_layout.addSpacing(12)
        menu_layout.addWidget(self.create_gmail_monitor_box())

        menu_layout.addStretch()

        db_button = QPushButton("🗄 Browse / Edit DB")
        db_button.setMinimumHeight(45)
        db_button.setToolTip("Apre SQL Databaser su data/nstonellm.db (ordini, conferme, ecc.)")
        db_button.setStyleSheet("""
            QPushButton {
                background-color: #2a4a6a;
                color: #FFFFFF;
                border: 1px solid #3a5a7a;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 10px 15px;
            }
            QPushButton:hover {
                background-color: #3a5a8a;
                border: 1px solid #4a6a9a;
            }
        """)
        db_button.clicked.connect(self.open_sql_database)
        menu_layout.addWidget(db_button)

        menu_scroll.setWidget(menu_content)
        outer_layout.addWidget(menu_scroll)

        return menu_frame

    def create_gmail_monitor_box(self) -> QFrame:
        """Pipeline Monitor ordini + log IMAP (navigation sidebar)."""
        gmail_status_box = QFrame()
        gmail_status_box.setStyleSheet("""
            QFrame {
                background-color: #12121f;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
            }
        """)
        gmail_status_layout = QVBoxLayout(gmail_status_box)
        gmail_status_layout.setContentsMargins(8, 8, 8, 8)
        gmail_status_layout.setSpacing(6)

        monitor_header = QHBoxLayout()
        monitor_header.setSpacing(6)
        gmail_status_title = QLabel("Pipeline Monitor")
        gmail_status_title.setStyleSheet(
            "color: #FFFFFF; font-size: 11px; font-weight: bold;"
        )
        monitor_header.addWidget(gmail_status_title)
        monitor_header.addStretch()

        update_gmail_btn = QPushButton("↻")
        update_gmail_btn.setToolTip(
            "Refresh IMAP poll status and log (auto-refresh every 5 s)."
        )
        update_gmail_btn.setFixedSize(26, 26)
        update_gmail_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a3a5a;
                color: #E8E8E8;
                border: 1px solid #3a4a6a;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #3a4a6a; }
        """)
        update_gmail_btn.clicked.connect(self.refresh_gmail_monitor_panel)
        monitor_header.addWidget(update_gmail_btn)
        gmail_status_layout.addLayout(monitor_header)

        gmail_status_label = QLabel("IMAP status — updates every 5 s")
        gmail_status_label.setStyleSheet("""
            QLabel {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #888899;
                padding: 6px;
                font-size: 10px;
            }
        """)
        gmail_status_label.setWordWrap(True)
        gmail_status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        gmail_status_label.setMinimumHeight(72)
        gmail_status_label.setTextFormat(Qt.PlainText)
        gmail_status_layout.addWidget(gmail_status_label)

        gmail_log_title = QLabel("IMAP Poll Log")
        gmail_log_title.setStyleSheet(
            "color: #AAAAAA; font-size: 10px; font-weight: bold;"
        )
        gmail_status_layout.addWidget(gmail_log_title)

        gmail_poll_log_view = QTextEdit()
        gmail_poll_log_view.setReadOnly(True)
        gmail_poll_log_view.setMinimumHeight(100)
        gmail_poll_log_view.setMaximumHeight(140)
        gmail_poll_log_view.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                color: #B8B8CC;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                padding: 4px;
                font-size: 9px;
                font-family: Consolas, monospace;
            }
        """)
        gmail_poll_log_view.setPlaceholderText("[AUTO] / [MAN] poll…")
        gmail_status_layout.addWidget(gmail_poll_log_view)

        self.gmail_orders_status_label = gmail_status_label
        self.gmail_poll_log_view = gmail_poll_log_view
        return gmail_status_box
    
    def create_orders_section(self):
        """Crea la sezione Orders con layout a 3 colonne orizzontali"""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(20, 20, 20, 20)
        section_layout.setSpacing(15)
        
        # Titolo e descrizione
        title_label = QLabel("Orders")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        section_layout.addWidget(title_label)
        
        desc_label = QLabel("Manage received order confirmations")
        desc_label.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        section_layout.addWidget(desc_label)
        
        # Layout a 3 colonne — tabelle laterali ampie, centro on-demand
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(0)

        self._orders_center_left = self.create_left_orders_box()
        self._orders_center_center = self.create_center_column()
        self._orders_center_right = self.create_right_orders_box()
        self._orders_center_splitter = create_hub_three_column_splitter(
            self._orders_center_left,
            self._orders_center_center,
            self._orders_center_right,
        )
        columns_layout.addWidget(self._orders_center_splitter)
        schedule_hub_splitter_collapsed(self._orders_center_splitter)

        section_layout.addLayout(columns_layout, 1)
        
        return section_widget
    
    def create_left_orders_box(self):
        """Crea il box sinistro: Incoming Orders"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(12)
        
        # Titolo colonna
        title_label = QLabel("Incoming Orders")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        column_layout.addWidget(title_label)

        self.poll_gmail_btn = QPushButton("📥 Poll Gmail Inbox (orders)")
        self.poll_gmail_btn.setFixedHeight(40)
        self.poll_gmail_btn.setToolTip(
            "Reads UNREAD emails whose subject contains order or quotation. "
            "Non usa token Gemini. Max 20 mail per ciclo."
        )
        self.poll_gmail_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a6a4a;
                color: #FFFFFF;
                border: 1px solid #3a7a5a;
                border-radius: 6px;
                padding: 10px 15px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a7a5a; }
            QPushButton:disabled { background-color: #1a3a2a; color: #888888; }
        """)
        self.poll_gmail_btn.clicked.connect(self.check_new_gmail_orders)
        column_layout.addWidget(self.poll_gmail_btn)
        
        # Tabella ordini ricevuti
        orders_table = QTableView()
        orders_table.setStyleSheet("""
            QTableView {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
            }
            QTableView::item {
                padding: 8px;
                border: none;
            }
            QTableView::item:selected {
                background-color: #4a2a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        
        # Model per la tabella con colonne: Data/Ora, Cliente, Oggetto, Stato
        headers = ["Date/Time", "Client", "Subject", "Status"]
        model = OrdersTableModel([], headers)
        orders_table.setModel(model)
        orders_table.horizontalHeader().setStretchLastSection(True)
        orders_table.setAlternatingRowColors(True)
        orders_table.setSelectionBehavior(QTableView.SelectRows)
        orders_table.setSelectionMode(QTableView.ExtendedSelection)
        orders_table.setEditTriggers(QTableView.NoEditTriggers)
        
        column_layout.addWidget(orders_table, 1)

        footer = QWidget()
        footer.setMinimumHeight(HUB_SIDE_FOOTER_HEIGHT)
        actions_layout = QHBoxLayout(footer)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        
        refresh_btn = QPushButton("🔄 Refresh Order List")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
            }
        """)
        refresh_btn.clicked.connect(lambda: self.load_orders_from_files(maintenance=True))
        actions_layout.addWidget(refresh_btn)
        
        update_last_btn = QPushButton("🔄 Refresh Last Order")
        update_last_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
            }
        """)
        update_last_btn.clicked.connect(self.update_last_order_row)
        actions_layout.addWidget(update_last_btn)
        
        delete_order_btn = QPushButton("🗑 Delete Selected")
        delete_order_btn.setToolTip(
            "Removes selected orders from the database (Ctrl+click for multiple rows)."
        )
        delete_order_btn.setStyleSheet("""
            QPushButton {
                background-color: #6a2a2a;
                color: #FFFFFF;
                border: 1px solid #8a3a3a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #8a3a3a;
            }
        """)
        delete_order_btn.clicked.connect(self.delete_selected_orders)
        actions_layout.addWidget(delete_order_btn)

        detail_btn = QPushButton("📋 Open Order Details")
        detail_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border: 1px solid #9B6CF6;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #9B6CF6;
            }
        """)
        detail_btn.clicked.connect(self.open_selected_order_detail)
        actions_layout.addWidget(detail_btn)

        column_layout.addWidget(footer)

        # Salva riferimenti
        self.left_orders_table = orders_table
        self.left_orders_model = model

        orders_table.selectionModel().selectionChanged.connect(
            self._on_order_selection_changed
        )
        orders_table.clicked.connect(self._on_order_table_clicked)

        return column_widget
    
    def create_center_column(self):
        """Colonna centrale: dettaglio ordine, materiali, analisi AI (come Quotations)."""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        title_label = QLabel("Order Details")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        header_row.addWidget(title_label)
        header_row.addStretch()
        self.order_detail_close_btn = QPushButton("×")
        self.order_detail_close_btn.setToolTip("Close detail panel")
        self.order_detail_close_btn.setVisible(False)
        self.order_detail_close_btn.setStyleSheet("""
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
        self.order_detail_close_btn.clicked.connect(self._collapse_order_detail_panel)
        header_row.addWidget(self.order_detail_close_btn)
        column_layout.addLayout(header_row)

        self._order_detail_empty_default_text = (
            "Select an order from the table on the left to view "
            "email, materiali, stato e azioni di classificazione/conferma."
        )
        self.order_detail_empty_label = QLabel(self._order_detail_empty_default_text)
        self.order_detail_empty_label.setWordWrap(True)
        self.order_detail_empty_label.setAlignment(Qt.AlignCenter)
        self.order_detail_empty_label.setStyleSheet(
            "color: #888899; font-size: 13px; padding: 40px 20px;"
        )
        column_layout.addWidget(self.order_detail_empty_label)

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

        self.order_detail_meta_label = QLabel("—")
        self.order_detail_meta_label.setStyleSheet("color: #AAAAAA; font-size: 11px;")
        self.order_detail_meta_label.setWordWrap(True)
        panel_layout.addWidget(self.order_detail_meta_label)

        self.order_detail_contact_label = QLabel("—")
        self.order_detail_contact_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        self.order_detail_contact_label.setWordWrap(True)
        panel_layout.addWidget(self.order_detail_contact_label)

        self.order_detail_quotation_label = QLabel("")
        self.order_detail_quotation_label.setWordWrap(True)
        self.order_detail_quotation_label.setStyleSheet("color: #9B8CF6; font-size: 11px;")
        panel_layout.addWidget(self.order_detail_quotation_label)

        self.order_detail_open_quotation_btn = QPushButton("Open NS-Q Quotation")
        self.order_detail_open_quotation_btn.setMinimumHeight(36)
        self.order_detail_open_quotation_btn.setToolTip(
            "Opens the linked quotation request for this order"
        )
        self.order_detail_open_quotation_btn.setStyleSheet(_ORDER_DETAIL_BTN_STYLE + """
            QPushButton {
                background-color: #3a2a5a;
                border: 1px solid #4a3a6a;
            }
            QPushButton:hover { background-color: #4a3a6a; }
        """)
        self.order_detail_open_quotation_btn.clicked.connect(self._on_center_open_quotation)
        self.order_detail_open_quotation_btn.setVisible(False)
        panel_layout.addWidget(self.order_detail_open_quotation_btn)

        subj_title = QLabel("Email Subject")
        subj_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(subj_title)

        self.order_detail_subject = QLineEdit()
        self.order_detail_subject.setStyleSheet("""
            QLineEdit {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                padding: 8px 10px;
                font-size: 12px;
            }
        """)
        panel_layout.addWidget(self.order_detail_subject)

        body_title = QLabel("Email Body / Customer Request")
        body_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(body_title)

        self.order_detail_message = QTextEdit()
        self.order_detail_message.setMaximumHeight(120)
        self.order_detail_message.setStyleSheet(_ORDER_TEXTEDIT_STYLE)
        panel_layout.addWidget(self.order_detail_message)

        mat_title = QLabel("Materials / Product / Machine")
        mat_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(mat_title)

        self.order_detail_materials = QTextEdit()
        self.order_detail_materials.setReadOnly(True)
        self.order_detail_materials.setMaximumHeight(56)
        self.order_detail_materials.setStyleSheet(_ORDER_TEXTEDIT_STYLE)
        panel_layout.addWidget(self.order_detail_materials)

        stato_title = QLabel("Order Status")
        stato_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(stato_title)

        self.order_detail_stato = QComboBox()
        self.order_detail_stato.setEditable(True)
        self.order_detail_stato.addItems(
            [
                "NEW",
                "DA_VALIDARE",
                "CONFIRMED",
                "IN LAVORAZIONE",
                "COMPLETED",
                "ARCHIVIATO",
            ]
        )
        self.order_detail_stato.setStyleSheet("""
            QComboBox {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
        """)
        panel_layout.addWidget(self.order_detail_stato)

        draft_title = QLabel("AI / Operator Notes")
        draft_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(draft_title)

        self.order_detail_draft = QTextEdit()
        self.order_detail_draft.setPlaceholderText(
            'After "Classify with AI", material/machine extraction appears here. '
            "You can add operator notes."
        )
        self.order_detail_draft.setMinimumHeight(72)
        self.order_detail_draft.setMaximumHeight(120)
        self.order_detail_draft.setStyleSheet(_ORDER_TEXTEDIT_STYLE)
        panel_layout.addWidget(self.order_detail_draft)

        conf_title = QLabel("Confirmation Sent to Customer")
        conf_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        panel_layout.addWidget(conf_title)

        self.order_detail_confirmation_status = QLabel("No linked confirmation")
        self.order_detail_confirmation_status.setWordWrap(True)
        self.order_detail_confirmation_status.setStyleSheet("color: #888899; font-size: 11px;")
        panel_layout.addWidget(self.order_detail_confirmation_status)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet(_ORDER_SCROLL_STYLE)
        scroll_area.setWidget(panel)

        order_detail_actions = QWidget()
        order_detail_actions_layout = QVBoxLayout(order_detail_actions)
        order_detail_actions_layout.setContentsMargins(0, 8, 0, 0)
        order_detail_actions_layout.setSpacing(8)

        actions_title = QLabel("Actions")
        actions_title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        order_detail_actions_layout.addWidget(actions_title)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)

        self.order_detail_classify_btn = QPushButton("Classify with AI")
        self.order_detail_classify_btn.setMinimumHeight(36)
        self.order_detail_classify_btn.setStyleSheet(_ORDER_DETAIL_BTN_STYLE + """
            QPushButton {
                background-color: #8B5CF6;
                border: 1px solid #9B6CF6;
            }
            QPushButton:hover { background-color: #9B6CF6; }
        """)
        self.order_detail_classify_btn.clicked.connect(self.classify_selected_order_with_ai)
        btn_col.addWidget(self.order_detail_classify_btn)

        self.order_detail_confirm_btn = QPushButton("Confirm → stock + email")
        self.order_detail_confirm_btn.setMinimumHeight(36)
        self.order_detail_confirm_btn.setToolTip(
            "Confirmation pipeline: verify catalog stock and send NStone email to customer"
        )
        self.order_detail_confirm_btn.setStyleSheet(_ORDER_DETAIL_BTN_STYLE + """
            QPushButton {
                background-color: #2a5a6a;
                border: 1px solid #3a6a7a;
            }
            QPushButton:hover { background-color: #3a6a7a; }
        """)
        self.order_detail_confirm_btn.clicked.connect(self.run_confirmation_pipeline_on_selected)
        btn_col.addWidget(self.order_detail_confirm_btn)

        self.order_detail_open_conf_btn = QPushButton("Open Sent Confirmation")
        self.order_detail_open_conf_btn.setMinimumHeight(36)
        self.order_detail_open_conf_btn.setStyleSheet(_ORDER_DETAIL_BTN_STYLE + """
            QPushButton {
                background-color: #2a4a6a;
                border: 1px solid #3a5a7a;
            }
            QPushButton:hover { background-color: #3a5a8a; }
        """)
        self.order_detail_open_conf_btn.clicked.connect(self._on_center_open_sent_confirmation)
        btn_col.addWidget(self.order_detail_open_conf_btn)

        self.order_detail_open_btn = QPushButton("Advanced Management")
        self.order_detail_open_btn.setMinimumHeight(36)
        self.order_detail_open_btn.setStyleSheet(_ORDER_DETAIL_BTN_STYLE + """
            QPushButton {
                background-color: #4a2a6a;
                border: 1px solid #5a3a7a;
            }
            QPushButton:hover { background-color: #5a3a7a; }
        """)
        self.order_detail_open_btn.clicked.connect(self._on_center_open_order_detail)
        btn_col.addWidget(self.order_detail_open_btn)

        self.order_detail_save_db_btn = QPushButton("💾 Save to DB")
        self.order_detail_save_db_btn.setMinimumHeight(36)
        self.order_detail_save_db_btn.setToolTip(
            "Save subject, email body, and status to the orders table (SQLite)"
        )
        self.order_detail_save_db_btn.setStyleSheet(_ORDER_DETAIL_BTN_STYLE + """
            QPushButton {
                background-color: #1a5a3a;
                border: 1px solid #2a6a4a;
            }
            QPushButton:hover { background-color: #2a6a4a; }
        """)
        self.order_detail_save_db_btn.clicked.connect(self.save_selected_order_to_db)
        btn_col.addWidget(self.order_detail_save_db_btn)

        order_detail_actions_layout.addLayout(btn_col)

        self.order_detail_content = QWidget()
        order_detail_content_layout = QVBoxLayout(self.order_detail_content)
        order_detail_content_layout.setContentsMargins(0, 0, 0, 0)
        order_detail_content_layout.setSpacing(0)
        order_detail_content_layout.addWidget(scroll_area, 1)
        order_detail_content_layout.addWidget(order_detail_actions)

        self.order_detail_panel = self.order_detail_content
        self.order_detail_panel.setVisible(False)
        column_layout.addWidget(self.order_detail_panel, 1)

        return column_widget

    @staticmethod
    def _format_order_materials_line(order: dict) -> str:
        parts: list[str] = []
        if order.get("materiale"):
            parts.append(str(order["materiale"]))
        if order.get("product") and str(order.get("product")) not in parts:
            parts.append(str(order["product"]))
        if order.get("quantita") not in (None, ""):
            parts.append(f"{order['quantita']} mq")
        if order.get("machine"):
            parts.append(str(order["machine"]))
        return " · ".join(parts) if parts else "Non estratto — usa Classify with AI"

    def _set_orders_center_splitter_expanded(self, expanded: bool) -> None:
        splitter = getattr(self, "_orders_center_splitter", None)
        if splitter is None:
            return
        if expanded:
            expand_hub_center_column(splitter)
        else:
            collapse_hub_center_column(splitter)

    def _collapse_order_detail_panel(self) -> None:
        self._detail_panel_collapsed = True
        if hasattr(self, "order_detail_empty_label"):
            self.order_detail_empty_label.setText(
                "Detail panel closed — click the row again or select another order."
            )
            self.order_detail_empty_label.setVisible(True)
        if hasattr(self, "order_detail_panel"):
            self.order_detail_panel.setVisible(False)
        if hasattr(self, "order_detail_close_btn"):
            self.order_detail_close_btn.setVisible(False)
        self._set_orders_center_splitter_expanded(False)

    def _show_order_detail_panel(self) -> None:
        self._detail_panel_collapsed = False
        if hasattr(self, "order_detail_empty_label"):
            self.order_detail_empty_label.setText(self._order_detail_empty_default_text)
            self.order_detail_empty_label.setVisible(False)
        if hasattr(self, "order_detail_panel"):
            self.order_detail_panel.setVisible(True)
        if hasattr(self, "order_detail_close_btn"):
            self.order_detail_close_btn.setVisible(True)
        self._set_orders_center_splitter_expanded(True)

    def _on_order_table_clicked(self, index: QModelIndex) -> None:
        if getattr(self, "_updating_table", False):
            return
        if not index.isValid():
            return
        self._detail_panel_collapsed = False
        row = index.row()
        order_id = None
        meta = getattr(self, "_orders_meta", []) or []
        if 0 <= row < len(meta):
            order_id = meta[row].get("order_id")
        if not order_id:
            self._populate_order_detail(None)
            return
        try:
            from modules.orders_database import get_order_by_order_id

            order = get_order_by_order_id(str(order_id))
        except Exception as exc:
            print(f"Errore caricamento ordine {order_id}: {exc}")
            order = None
        self._populate_order_detail(order)

    def _on_order_selection_changed(self):
        if getattr(self, "_updating_table", False):
            return
        if not is_ui_active(self):
            return
        if not hasattr(self, "left_orders_table"):
            return
        selection = self.left_orders_table.selectionModel()
        if not selection or not selection.hasSelection():
            self._populate_order_detail(None)
            return
        rows = selection.selectedRows()
        if not rows:
            self._populate_order_detail(None)
            return
        self._detail_panel_collapsed = False
        row = rows[0].row()
        order_id = None
        meta = getattr(self, "_orders_meta", []) or []
        if 0 <= row < len(meta):
            order_id = meta[row].get("order_id")
        if not order_id:
            self._populate_order_detail(None)
            return
        try:
            from modules.orders_database import get_order_by_order_id

            order = get_order_by_order_id(str(order_id))
        except Exception as exc:
            print(f"Errore caricamento ordine {order_id}: {exc}")
            order = None
        self._populate_order_detail(order)

    def _populate_order_detail(self, order: Optional[dict]):
        if not is_ui_active(self):
            return
        try:
            self._populate_order_detail_impl(order)
        except RuntimeError:
            pass

    def _populate_order_detail_impl(self, order: Optional[dict]):
        if not order:
            self._selected_order_id = None
            self._linked_quotation_case_id = None
            self.order_detail_quotation_label.clear()
            self.order_detail_open_quotation_btn.setVisible(False)
            self._detail_panel_collapsed = False
            self.order_detail_empty_label.setText(self._order_detail_empty_default_text)
            self.order_detail_empty_label.setVisible(True)
            self.order_detail_panel.setVisible(False)
            self.order_detail_close_btn.setVisible(False)
            for btn in (
                self.order_detail_classify_btn,
                self.order_detail_confirm_btn,
                self.order_detail_open_conf_btn,
                self.order_detail_open_btn,
                self.order_detail_save_db_btn,
            ):
                btn.setEnabled(False)
            self._set_orders_center_splitter_expanded(False)
            return

        self._selected_order_id = str(order.get("order_id") or "")
        for btn in (
            self.order_detail_classify_btn,
            self.order_detail_confirm_btn,
            self.order_detail_open_btn,
            self.order_detail_save_db_btn,
        ):
            btn.setEnabled(bool(self._selected_order_id))

        stato = str(order.get("status") or "NEW")
        ts = str(order.get("created_at") or "—")
        if len(ts) > 19:
            ts = ts[:19]
        oid = self._selected_order_id
        short_id = oid[:12] + "…" if len(oid) > 12 else oid
        self.order_detail_meta_label.setText(f"ID {short_id} · {ts} · Status: {stato}")

        idx = self.order_detail_stato.findText(stato, Qt.MatchFixedString)
        if idx >= 0:
            self.order_detail_stato.setCurrentIndex(idx)
        else:
            self.order_detail_stato.setEditText(stato)

        client = str(order.get("client") or "—")
        email = str(order.get("client_email") or "—")
        self.order_detail_contact_label.setText(f"{client} · {email}")

        case_id = str(order.get("quotation_case_id") or "").strip()
        if case_id:
            try:
                from modules.quotation_email_thread import case_token

                token = case_token(case_id)
            except Exception:
                token = case_id[:8]
            self.order_detail_quotation_label.setText(
                f"Origine: preventivo {token}"
            )
            self.order_detail_open_quotation_btn.setVisible(True)
            self._linked_quotation_case_id = case_id
        else:
            self.order_detail_quotation_label.clear()
            self.order_detail_open_quotation_btn.setVisible(False)
            self._linked_quotation_case_id = None

        self.order_detail_subject.setText(str(order.get("email_subject") or order.get("product") or ""))
        self.order_detail_message.setPlainText(str(order.get("email_body") or ""))
        self.order_detail_materials.setPlainText(self._format_order_materials_line(order))

        notes = ""
        try:
            from modules.orders_database import get_order_confirmation_meta

            meta = get_order_confirmation_meta(self._selected_order_id)
            if meta.get("notes"):
                notes = str(meta["notes"])
            elif meta.get("availability"):
                notes = f"Availability: {meta['availability']}"
        except Exception:
            pass
        if notes:
            self.order_detail_draft.setPlainText(notes)
        else:
            self.order_detail_draft.clear()

        self._update_order_confirmation_status(order)
        if self._detail_panel_collapsed:
            return
        self._show_order_detail_panel()

    def _update_order_confirmation_status(self, order: dict) -> None:
        has_sent = False
        try:
            from modules.orders_database import get_order_confirmation_meta

            meta = get_order_confirmation_meta(str(order.get("order_id") or ""))
            for key in ("confirmation_email", "sent_confirmation_email"):
                info = meta.get(key)
                if isinstance(info, dict) and info.get("sent"):
                    has_sent = True
                    ts = info.get("timestamp") or info.get("sent_at") or "—"
                    self.order_detail_confirmation_status.setText(
                        f"Conferma inviata · {ts}"
                    )
                    break
        except Exception:
            pass
        if not has_sent:
            self.order_detail_confirmation_status.setText(
                "Nessuna email di conferma inviata per questo ordine."
            )
        self.order_detail_open_conf_btn.setEnabled(has_sent)

    def _on_center_open_quotation(self):
        case_id = getattr(self, "_linked_quotation_case_id", None)
        if not case_id:
            return
        try:
            from modules.incoming_requests_db import get_incoming_request
            from ui.windows.quotations.quotation_request_detail_dialog import (
                QuotationRequestDetailDialog,
            )

            request = get_incoming_request(str(case_id))
            if not request:
                QMessageBox.information(
                    self,
                    "Preventivo",
                    "Richiesta preventivo collegata non trovata nel database.",
                )
                return
            dialog = QuotationRequestDetailDialog(
                parent=self,
                request=request,
                case_id=str(case_id),
            )
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Preventivo",
                f"Impossibile aprire il preventivo collegato:\n{exc}",
            )

    def _on_center_open_sent_confirmation(self):
        if not self._selected_order_id:
            return
        try:
            from modules.orders_database import get_order_sent_confirmation_detail

            detail = get_order_sent_confirmation_detail(self._selected_order_id)
        except Exception:
            detail = None
        if not detail:
            QMessageBox.information(
                self,
                "Confirmation",
                "No sent confirmation found for this order.",
            )
            return
        sent_info = detail.get("sent_confirmation_email") or detail.get("confirmation_email")
        if not sent_info:
            QMessageBox.information(self, "Confirmation", "Confirmation details unavailable.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Sent confirmation — {self._selected_order_id}")
        dialog.setMinimumSize(620, 480)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            f"A: {sent_info.get('to', '—')}\n"
            f"Subject: {sent_info.get('subject', '—')}\n"
            f"When: {sent_info.get('timestamp', sent_info.get('sent_at', '—'))}\n\n"
            f"{sent_info.get('body', sent_info.get('message', ''))}"
        )
        layout.addWidget(text)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        show_auxiliary_window(dialog)

    def open_selected_order_detail(self):
        """Apre il dettaglio ordine per la riga selezionata nella tabella sinistra."""
        order_id = self._get_selected_order_id()
        if not order_id:
            QMessageBox.information(self, "Order", "Select an order from the table.")
            return
        self._selected_order_id = order_id
        self._on_center_open_order_detail()

    def _on_center_open_order_detail(self):
        if not self._selected_order_id:
            QMessageBox.information(self, "Order", "Select an order from the table.")
            return
        try:
            from modules.orders_database import get_order_by_order_id
            from ui.windows.orders.dettaglio_ordine_window import DettaglioOrdineWindow

            order = get_order_by_order_id(self._selected_order_id)
            if not order:
                QMessageBox.warning(self, "Order", "Order not found in database.")
                return
            show_auxiliary_window(DettaglioOrdineWindow(order, parent=self))
        except Exception as exc:
            QMessageBox.critical(self, "Order", f"Unable to open order details:\n{exc}")

    def save_selected_order_to_db(self):
        if not self._selected_order_id:
            QMessageBox.information(self, "Save to DB", "Select an order.")
            return
        from modules.orders_database import update_order_fields, get_order_by_order_id

        fields = {
            "email_subject": self.order_detail_subject.text().strip(),
            "email_body": self.order_detail_message.toPlainText().strip(),
            "status": self.order_detail_stato.currentText().strip() or "NEW",
        }
        result = update_order_fields(self._selected_order_id, fields)
        if not result.get("ok"):
            QMessageBox.warning(
                self,
                "Save to DB",
                result.get("error", "Salvataggio non riuscito."),
            )
            return
        order = get_order_by_order_id(self._selected_order_id)
        if order:
            self._populate_order_detail(order)
        self.load_orders_from_files()
        QMessageBox.information(self, "Save to DB", "Order updated in SQLite.")

    def create_right_orders_box(self):
        """Crea il box destro: Ordini Inviati"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(12)
        
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_label = QLabel("Sent Orders")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        title_row.addWidget(title_label)
        title_row.addStretch()
        column_layout.addLayout(title_row)

        column_layout.addWidget(hub_side_toolbar_spacer(40))
        
        # Tabella ordini inviati
        orders_table = QTableView()
        orders_table.setStyleSheet("""
            QTableView {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
            }
            QTableView::item {
                padding: 8px;
                border: none;
            }
            QTableView::item:selected {
                background-color: #4a2a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        
        # Model per la tabella con colonne: ID Ordine, Cliente, Timestamp Invio, Stato
        headers = ["Order ID", "Client", "Sent At", "Status"]
        model = OrdersTableModel([], headers)
        orders_table.setModel(model)
        orders_table.horizontalHeader().setStretchLastSection(True)
        orders_table.setAlternatingRowColors(True)
        orders_table.setSelectionBehavior(QTableView.SelectRows)
        orders_table.setEditTriggers(QTableView.NoEditTriggers)
        
        # Connessione doppio click per vedere dettagli
        orders_table.doubleClicked.connect(self.show_sent_order_details)
        
        column_layout.addWidget(orders_table, 1)

        footer = QWidget()
        footer.setMinimumHeight(HUB_SIDE_FOOTER_HEIGHT)
        actions_layout = QHBoxLayout(footer)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        
        refresh_sent_btn = QPushButton("🔄 Refresh Ordini Inviati")
        refresh_sent_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
            }
        """)
        refresh_sent_btn.clicked.connect(lambda: self.load_sent_orders_refresh(force=True))
        actions_layout.addWidget(refresh_sent_btn)
        
        details_btn = QPushButton("👁 Vedi Dettagli")
        details_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
            }
        """)
        details_btn.clicked.connect(self.show_sent_order_details)
        actions_layout.addWidget(details_btn)

        delete_sent_btn = QPushButton("🗑 Elimina selezionato")
        delete_sent_btn.setToolTip(
            "Rimuove definitivamente la registrazione dell'email di conferma "
            "(DB + JSON) — l'ordine resta nel database. "
            "⚠️ righe arancioni = ordine ancora in lavorazione"
        )
        delete_sent_btn.setStyleSheet("""
            QPushButton {
                background-color: #6a2a2a;
                color: #FFFFFF;
                border: 1px solid #8a3a3a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #8a3a3a;
            }
        """)
        delete_sent_btn.clicked.connect(self.delete_selected_sent_order)
        actions_layout.addWidget(delete_sent_btn)

        column_layout.addWidget(footer)
        
        # Salva riferimenti
        self.right_orders_table = orders_table
        self.right_orders_model = model
        
        self.sent_orders_timer = QTimer(self)
        self.sent_orders_timer.timeout.connect(lambda: self.load_sent_orders_refresh(force=False))
        self.manage_section_timer(self.sent_orders_timer, 60000)
        
        return column_widget
    
    def create_unified_service_section(self, title, items):
        """Crea una sezione unificata per un servizio all'interno del pannello centrale"""
        section_frame = QFrame()
        section_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        section_layout = QVBoxLayout(section_frame)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)
        
        # Titolo sezione
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold;")
        section_layout.addWidget(title_label)
        
        # Items della sezione
        for label, value, color in items:
            item_layout = QHBoxLayout()
            
            item_label = QLabel(f"{label}: {value}")
            item_label.setStyleSheet(f"color: {color}; font-size: 11px;")
            item_layout.addWidget(item_label)
            item_layout.addStretch()
            
            section_layout.addLayout(item_layout)
        
        return section_frame
    
    def create_localhost_status_box(self):
        """Crea il box Localhost Status (stesso della sezione Quotations)"""
        return self.create_service_status_box(
            "Localhost Status",
            [
                ("Stato API locale", "Online", "#00FF00"),
                ("Latency", "5ms", "#AAAAAA"),
                ("Ultima ricezione POST", "Ora", "#AAAAAA"),
                ("Richieste totali", "0", "#AAAAAA")
            ],
            icon="🖥"
        )
    
    def create_service_status_box(self, title, items, icon=None):
        """Crea un box di stato per servizi (stesso della sezione Quotations)"""
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
        """Sezione Help — assistente per flusso ordini e conferme."""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(30, 30, 30, 30)
        section_layout.setSpacing(20)

        help_title = QLabel("Help")
        help_title.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        section_layout.addWidget(help_title)

        help_desc = QLabel(
            "Ask how to manage Gmail orders, sent confirmations, AI analysis, and the orders SQLite table."
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
        
        welcome_text = QLabel("NStone Neural Engine ready. Ask about orders or check order confirmation status.")
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
        self.ai_input.setPlaceholderText("Ask about Gmail orders, confirmations, or database…")
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
        """Footer operativo — strumenti ordini (allineato a Quotations Hub)."""
        footer_frame = QFrame()
        footer_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
        """)
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 15, 20, 15)
        footer_layout.setSpacing(15)

        title_label = QLabel("STRUMENTI ORDERS")
        title_label.setStyleSheet("color: #AAAAAA; font-size: 12px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(title_label)

        hint_label = QLabel(
            "Gmail IMAP → SQLite orders → analisi AI → conferme inviate · Verifica lo stack LOCALE"
        )
        hint_label.setStyleSheet("color: #666677; font-size: 11px;")
        hint_label.setWordWrap(True)
        hint_label.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(hint_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)
        buttons_layout.addStretch()

        force_sync_btn = QPushButton("🔄 Forza Sync")
        force_sync_btn.setToolTip(
            "Ricarica ordini da SQLite, conferme inviate e poll Gmail IMAP"
        )
        force_sync_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: bold;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        force_sync_btn.clicked.connect(self.sync_database)
        buttons_layout.addWidget(force_sync_btn)

        health_btn = QPushButton("Verifica pipeline")
        health_btn.setToolTip(
            "Check orders SQLite, FastAPI, neural engine, Gmail IMAP/SMTP"
        )
        health_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border: 1px solid #9B6CF6;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: bold;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #9B6CF6;
                border: 1px solid #AB7CF6;
            }
            QPushButton:pressed {
                background-color: #7B4CF6;
            }
        """)
        health_btn.clicked.connect(self.run_orders_health_check)
        buttons_layout.addWidget(health_btn)

        start_web_btn = QPushButton("▶ Avvia backend web")
        start_web_btn.setToolTip(
            "Esegue avvia_backend_web.bat: FastAPI, ngrok e aggiornamento URL form"
        )
        start_web_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a5a3a;
                color: #FFFFFF;
                border: 1px solid #2a6a4a;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: bold;
                min-width: 170px;
            }
            QPushButton:hover {
                background-color: #2a6a4a;
                border: 1px solid #3a7a5a;
            }
            QPushButton:pressed {
                background-color: #0a4a2a;
            }
        """)
        start_web_btn.clicked.connect(self.launch_backend_web_stack)
        buttons_layout.addWidget(start_web_btn)

        stop_web_btn = QPushButton("⏹ Spegni backend web")
        stop_web_btn.setToolTip("Termina FastAPI (:8000) e ngrok")
        stop_web_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a1a1a;
                color: #FFFFFF;
                border: 1px solid #6a2a2a;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: bold;
                min-width: 170px;
            }
            QPushButton:hover {
                background-color: #6a2a2a;
                border: 1px solid #7a3a3a;
            }
            QPushButton:pressed {
                background-color: #4a0a0a;
            }
        """)
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
        """Statistiche ordini da SQLite / meta in memoria."""
        meta = getattr(self, "_orders_meta", []) or []
        total = len(meta)
        new_count = sum(
            1
            for o in meta
            if str(o.get("status") or "NEW").strip().lower() in _PENDING_ORDER_STATUSES
            or str(o.get("status") or "").upper() == "NEW"
        )
        sent_count = 0
        if hasattr(self, "right_orders_model"):
            sent_count = self.right_orders_model.rowCount()

        stats_box = self.create_health_box(
            "ORDER STATISTICS",
            [
                (f"Total in DB: {total}", "", "#FFFFFF"),
                (f"Pending: {new_count}", "", "#FFD93D" if new_count > 0 else "#AAAAAA"),
                (f"Sent confirmations: {sent_count}", "", "#00FF00" if sent_count else "#AAAAAA"),
            ],
            icon="📊",
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
                    section_idx = self.section_index_map.get(name, idx)
                    break
        
        # Mostra la sezione se l'indice è valido
        if section_idx is not None and 0 <= section_idx < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(section_idx)
            if section_name == "Orders":
                self.load_orders_from_files()
        else:
            print(f"Warning: Sezione '{section_name}' non trovata (indice: {section_idx}, totale sezioni: {self.stacked_widget.count()})")
    
    def sync_database(self):
        """Ricarica ordini SQLite, conferme inviate e avvia poll Gmail."""
        self.load_orders_from_files()
        self.load_sent_orders_refresh(force=True)
        self._gmail_poll_manual = True
        self.check_new_gmail_orders_async()
        pending = self._order_pipeline_counts().get("new", 0)
        sent = self._order_pipeline_counts().get("done", 0)
        QMessageBox.information(
            self,
            "Sincronizzazione",
            f"Ordini aggiornati.\n\n"
            f"In coda: {pending}\n"
            f"Conferme inviate (tabella): {sent}\n"
            f"Poll Gmail avviato.",
        )

    def _order_pipeline_counts(self) -> dict:
        meta = getattr(self, "_orders_meta", []) or []
        new_count = sum(
            1
            for o in meta
            if str(o.get("status") or "NEW").strip().lower() in _PENDING_ORDER_STATUSES
            or str(o.get("status") or "").upper() == "NEW"
        )
        sent_count = 0
        if hasattr(self, "right_orders_model"):
            sent_count = self.right_orders_model.rowCount()
        return {"total": len(meta), "new": new_count, "done": sent_count}

    def update_neural_stats(self):
        if not is_ui_active(self):
            return
        worker = getattr(self, "_neural_stats_worker", None)
        if worker is not None and worker.isRunning():
            return
        worker = NeuralStatsPollWorker(self._order_pipeline_counts(), self)
        wire_worker(self, worker, self._apply_neural_stats, "_neural_stats_worker")

    def _apply_neural_stats(self, stats: dict):
        if not is_ui_active(self):
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
                pipeline_kind="orders",
            )
        except RuntimeError:
            pass

    def open_sql_database(self):
        if not HAS_DATABASE_WINDOW or DatabaseWindow is None:
            QMessageBox.warning(
                self,
                "Database",
                "SQL Databaser non disponibile in questa installazione.",
            )
            return
        dialog = DatabaseWindow(parent=self)
        dialog.destroyed.connect(
            lambda *_: (
                self.load_orders_from_files(),
                self.load_sent_orders_refresh(force=True),
            )
        )
        show_auxiliary_window(dialog)

    def launch_backend_web_stack(self):
        try:
            from modules.backend_web_stack import start_backend_web

            ok, message = start_backend_web(self.project_root)
        except Exception as exc:
            QMessageBox.critical(self, "Start Web Backend", f"Error:\n{exc}")
            return
        icon = QMessageBox.Information if ok else QMessageBox.Warning
        QMessageBox(icon, "Avvio backend web", message)

    def shutdown_backend_web_stack(self):
        reply = QMessageBox.question(
            self,
            "Spegni backend web",
            "Terminare FastAPI (porta 8000) e ngrok?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            from modules.backend_web_stack import stop_backend_web

            ok, message = stop_backend_web()
        except Exception as exc:
            QMessageBox.critical(self, "Stop Web Backend", f"Error:\n{exc}")
            return
        icon = QMessageBox.Information if ok else QMessageBox.Warning
        QMessageBox(icon, "Spegni backend web", message)

    def run_orders_health_check(self):
        """Verifica stack LOCALE per il flusso ordini."""
        lines: list[str] = []

        try:
            counts = self._order_pipeline_counts()
            lines.append(
                f"SQLite ordini: OK ({counts['total']} in DB, "
                f"{counts['new']} in coda, {counts['done']} conferme in tabella)"
            )
        except Exception as exc:
            lines.append(f"SQLite ordini: FAIL ({exc})")

        try:
            resp = requests.get("http://127.0.0.1:8000/health", timeout=_HTTP_QUICK)
            if resp.status_code == 200:
                lines.append("FastAPI :8000: ONLINE")
            else:
                lines.append(f"FastAPI :8000: risposta {resp.status_code}")
        except requests.RequestException:
            lines.append("FastAPI :8000: OFFLINE (opzionale per API ordini)")

        try:
            from llm.llm_service import get_llm_service, load_llm_config

            cfg = load_llm_config()
            provider = cfg.get("provider", "ollama")
            llm = get_llm_service()
            if llm.is_configured():
                lines.append(f"Motore neurale ({provider}): configurato")
            else:
                lines.append(f"Motore neurale ({provider}): non pronto — Settings")
        except Exception as exc:
            lines.append(f"Motore neurale: FAIL ({exc})")

        try:
            from core.machine_plc_config import load_config

            gmail = (load_config().get("gmail") or {})
            if (gmail.get("email") or "").strip() and (gmail.get("app_password") or "").strip():
                lines.append("Gmail (IMAP/SMTP): credenziali presenti in config")
            else:
                lines.append("Gmail: non configurato (Settings → casella ordini)")
        except Exception as exc:
            lines.append(f"Gmail: FAIL ({exc})")

        if self.gmail_orders_status_file.exists():
            try:
                with open(self.gmail_orders_status_file, encoding="utf-8") as f:
                    st = json.load(f)
                status = st.get("status", "—")
                lines.append(f"Ultimo poll Gmail ordini: {status}")
            except Exception:
                lines.append("Log poll Gmail: file presente ma illeggibile")
        else:
            lines.append("Poll Gmail ordini: nessun log ancora")

        report = "\n".join(f"• {line}" for line in lines)
        QMessageBox.information(
            self,
            "Verifica pipeline Orders",
            f"Stack LOCALE — gestione ordini\n\n{report}",
        )

    def send_ai_message(self):
        """Gestisce l'invio del messaggio alla sezione Help."""
        import traceback
        
        try:
            message = self.ai_input.text().strip()
            if not message:
                return
            
            print(f"\n[ORDERS WINDOW] Messaggio inviato: {message}")

            # Disabilita input durante la chiamata
            self.ai_input.setEnabled(False)
            self.start_ai_worker(message)

        except Exception as e:
            print("\n" + "="*80)
            print("ERRORE IN send_ai_message (ORDERS WINDOW):")
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
        if not is_ui_active(self):
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
            reply_label = QLabel(response if response else "Nessuna risposta ricevuta.")
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
    
    def update_footer_statistics(self):
        """Aggiorna le statistiche nel box Request Statistics"""
        try:
            # Trova il box Request Statistics e aggiornalo
            if hasattr(self, 'footer_boxes_widget'):
                boxes_layout = self.footer_boxes_widget.layout()
                if boxes_layout:
                    # Il box Request Statistics è l'ultimo prima dello stretch
                    widget_count = boxes_layout.count() - 1  # -1 per lo stretch
                    if widget_count >= 7:  # Request Statistics è il 7° box (indice 6)
                        request_stats_box = boxes_layout.itemAt(6).widget()
                        if request_stats_box:
                            # Ricrea il box con statistiche aggiornate
                            new_box = self.create_request_statistics_box()
                            new_box.setMinimumWidth(220)
                            
                            # Sostituisci il vecchio box
                            boxes_layout.removeWidget(request_stats_box)
                            request_stats_box.deleteLater()
                            boxes_layout.insertWidget(6, new_box)
        except Exception as e:
            # Ignora errori durante l'aggiornamento
            pass
    
    def go_back(self):
        """Porta il focus alla dashboard (sezione resta aperta o in icona)."""
        self.go_back_to_dashboard()
    
    def closeEvent(self, event):
        """Gestisce la chiusura della finestra in modo sicuro"""
        self._ui_active = False
        self.on_section_hidden()
        for timer_name in ("gmail_check_timer", "gmail_monitor_timer", "neural_stats_timer", "sent_orders_timer"):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        wait_workers(self, ORDERS_WORKER_ATTRS, timeout_ms=2000)
        super().closeEvent(event)
    
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

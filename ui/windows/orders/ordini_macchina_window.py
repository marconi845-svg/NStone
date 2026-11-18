"""
Nstone LLM - Finestra Ordini in Arrivo / Produzione
Visualizza gli ordini inviati a una specifica macchina
"""
import sys
from datetime import datetime
from pathlib import Path
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QMessageBox, QGroupBox, QScrollArea)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont

# Import enum MachineState per CNC
try:
    from machines.cnc_simulator import MachineState
    HAS_MACHINE_STATE = True
except ImportError:
    HAS_MACHINE_STATE = False
    MachineState = None


class OrdiniMacchinaRefreshWorker(QThread):
    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(list)

    def __init__(self, machine_name: str, parent=None):
        super().__init__(parent)
        self.machine_name = machine_name

    def run(self):
        try:
            from modules.orders_database import get_orders_for_machine

            self.result_ready.emit(get_orders_for_machine(self.machine_name))
        except Exception:
            self.result_ready.emit([])


class OrdiniMacchinaWindow(SectionMainWindow):
    """
    Finestra per visualizzare ordini inviati a una specifica macchina
    Mostra ordini dal Centro Ordini Produzione
    """
    
    def __init__(self, nome_macchina, parent=None):
        super().__init__(parent)
        self.nome_macchina = nome_macchina
        self.parent_window = parent
        self.ordini_ricevuti = []  # Lista ordini per questa macchina
        
        # Riferimento alla finestra Centro Ordini Produzione per ottenere ordini
        self.centro_ordini_window = None
        self.main_window = None
        self._find_centro_ordini_window()
        
        self.setWindowTitle(f"📋 Incoming / Production Orders — {nome_macchina}")
        self.setMinimumSize(900, 600)
        
        self.init_ui()
        self.apply_stylesheet()
        
        self._refresh_worker = None
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(lambda: self.aggiorna_ordini_async(force=False))
        self.manage_section_timer(self.update_timer, 2000)

    def on_section_shown(self) -> None:
        self.aggiorna_ordini_async(force=True)

    def on_section_hidden(self) -> None:
        worker = getattr(self, "_refresh_worker", None)
        if worker is not None and worker.isRunning():
            worker.wait(150)
        self._refresh_worker = None
    
    def aggiorna_ordini_async(self, force: bool = False):
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            return
        self._refresh_worker = OrdiniMacchinaRefreshWorker(self.nome_macchina, parent=self)
        self._refresh_worker.result_ready.connect(self._apply_ordini_refresh)
        self._refresh_worker.start()

    def _apply_ordini_refresh(self, ordini: list):
        self._refresh_worker = None
        self.ordini_ricevuti = ordini or []

        if not self.centro_ordini_window:
            self._find_centro_ordini_window()
        if self.centro_ordini_window:
            if self.nome_macchina == "CNC":
                self.centro_ordini_window.ordini_cnc = list(self.ordini_ricevuti)
            elif self.nome_macchina == "Lucidatrice":
                self.centro_ordini_window.ordini_lucidatrice = list(self.ordini_ricevuti)
            elif self.nome_macchina == "Multifilo":
                self.centro_ordini_window.ordini_multifilo = list(self.ordini_ricevuti)

        self._aggiorna_stati_ordini()
        self._popola_tabella()
        self.ordini_count_label.setText(f"Orders: {len(self.ordini_ricevuti)}")

    def aggiorna_ordini(self):
        """Compat: refresh sincrono (preferire aggiorna_ordini_async)."""
        self.aggiorna_ordini_async(force=True)

    def _find_centro_ordini_window(self):
        """Trova la finestra Centro Ordini Produzione per ottenere gli ordini"""
        # Metodo 1: Se parent è una finestra macchina, cerca nella main window
        if self.parent_window:
            # Se parent ha un attributo parent (finestra principale)
            if hasattr(self.parent_window, 'parent'):
                main_window = self.parent_window.parent()
                if main_window and hasattr(main_window, 'centro_ordini_produzione_window'):
                    self.centro_ordini_window = main_window.centro_ordini_produzione_window
                    self.main_window = main_window
                    return
            
            # Metodo 2: Cerca nella gerarchia delle finestre
            for widget in self.parent_window.findChildren(QWidget):
                if hasattr(widget, '__class__'):
                    class_name = widget.__class__.__name__
                    if 'CentroOrdiniProduzione' in class_name:
                        self.centro_ordini_window = widget
                        return
        
        # Metodo 3: Cerca tra tutte le finestre aperte dell'applicazione
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            for widget in app.allWidgets():
                if hasattr(widget, '__class__'):
                    class_name = widget.__class__.__name__
                    if 'CentroOrdiniProduzione' in class_name:
                        self.centro_ordini_window = widget
                        return
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Tabella ordini
        ordini_section = self.create_ordini_section()
        main_layout.addWidget(ordini_section, 1)
        
        # Status bar
        status_bar = self.create_status_bar()
        main_layout.addWidget(status_bar)
    
    def create_header(self):
        """Crea l'header della finestra"""
        header_widget = QWidget()
        header_widget.setFixedHeight(50)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(15)
        
        # Titolo
        titolo = QLabel(f"📋 Incoming / Production Orders — {self.nome_macchina}")
        titolo.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(titolo)
        
        header_layout.addStretch()
        
        # Pulsante Aggiorna
        self.aggiorna_btn = QPushButton("🔄 Aggiorna")
        self.aggiorna_btn.setFixedHeight(32)
        self.aggiorna_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a5a2a;
                border: 1px solid #3a6a3a;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 15px;
            }
            QPushButton:hover {
                background-color: #3a6a3a;
                border: 1px solid #4a7a4a;
            }
            QPushButton:pressed {
                background-color: #1a4a1a;
            }
        """)
        self.aggiorna_btn.clicked.connect(self.aggiorna_ordini)
        header_layout.addWidget(self.aggiorna_btn)
        
        return header_widget
    
    def create_ordini_section(self):
        """Crea la sezione con la tabella ordini"""
        section_box = QGroupBox(f"Orders received by {self.nome_macchina}")
        section_box.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #FFFFFF;
                border: 2px solid #4a4a5a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        section_layout = QVBoxLayout(section_box)
        section_layout.setContentsMargins(10, 10, 10, 10)
        
        # Tabella ordini
        self.ordini_table = QTableWidget()
        self.ordini_table.setColumnCount(6)
        self.ordini_table.setHorizontalHeaderLabels([
            "Codice Ordine",
            "Cliente",
            "Materiale",
            "Quantità",
            "Stato",
            "Timestamp Invio"
        ])
        
        # Configurazione tabella
        header = self.ordini_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        self.ordini_table.setAlternatingRowColors(True)
        self.ordini_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 5px;
                gridline-color: #2a2a3a;
                color: #CCCCCC;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:alternate {
                background-color: #0f0f1a;
            }
            QHeaderView::section {
                background-color: #1a1a2a;
                color: #FFFFFF;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #3a3a4a;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        
        section_layout.addWidget(self.ordini_table)
        
        return section_box
    
    def create_status_bar(self):
        """Crea la barra di stato"""
        status_bar = QWidget()
        status_bar.setFixedHeight(40)
        status_bar.setStyleSheet("""
            QWidget {
                background-color: #1a1a2a;
                border-top: 1px solid #3a3a4a;
            }
        """)
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(15, 5, 15, 5)
        
        self.status_label = QLabel("Pronto")
        self.status_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # Contatore ordini
        self.ordini_count_label = QLabel("Orders: 0")
        self.ordini_count_label.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        layout.addWidget(self.ordini_count_label)
        
        return status_bar
    
    def _is_machine_running(self) -> bool:
        """
        Determina se la macchina è in esecuzione (RUN)
        Usa confronto robusto con enum per CNC, numerico per Lucidatrice/Multifilo
        
        Returns:
            True se macchina è in RUN, False altrimenti
        """
        if not self.parent_window:
            return False
        
        if hasattr(self.parent_window, '_current_cnc_status'):
            # CNC - usa enum MachineState
            if self.parent_window._current_cnc_status:
                try:
                    machine_state = self.parent_window._current_cnc_status.machine_state
                    # Confronto diretto con enum (robusto)
                    if HAS_MACHINE_STATE and MachineState:
                        return machine_state == MachineState.RUN
                    else:
                        # Fallback: confronto con stringa
                        return str(machine_state) == 'MachineState.RUN' or str(machine_state) == 'RUN'
                except (AttributeError, TypeError):
                    return False
        elif hasattr(self.parent_window, '_current_lucidatrice_status'):
            # Lucidatrice - usa stato numerico (0=Idle, 1=Run, 2=Alarm, ecc.)
            stato = self.parent_window._current_lucidatrice_status
            if stato:
                try:
                    stato_num = stato.stato if hasattr(stato, 'stato') else 0
                    return stato_num == 1  # 1 = Run
                except (AttributeError, TypeError):
                    return False
        elif hasattr(self.parent_window, '_current_multifilo_status'):
            # Multifilo - usa stato numerico (0=Idle, 1=Run, 2=Alarm)
            stato = self.parent_window._current_multifilo_status
            if stato:
                try:
                    stato_num = stato.stato_macchina if hasattr(stato, 'stato_macchina') else (stato.stato if hasattr(stato, 'stato') else 0)
                    return stato_num == 1  # 1 = Run
                except (AttributeError, TypeError):
                    return False
        
        return False
    
    def _is_machine_stopped(self) -> bool:
        """
        Determina se la macchina è ferma (STOP/IDLE/READY)
        
        Returns:
            True se macchina è ferma, False altrimenti
        """
        if not self.parent_window:
            return True
        
        if hasattr(self.parent_window, '_current_cnc_status'):
            # CNC - usa enum MachineState
            if self.parent_window._current_cnc_status:
                try:
                    machine_state = self.parent_window._current_cnc_status.machine_state
                    # Confronto diretto con enum (robusto)
                    if HAS_MACHINE_STATE and MachineState:
                        return machine_state in [MachineState.STOP, MachineState.READY, MachineState.HOLD]
                    else:
                        # Fallback: confronto con stringhe
                        state_str = str(machine_state)
                        return 'STOP' in state_str or 'READY' in state_str or 'HOLD' in state_str
                except (AttributeError, TypeError):
                    return True
        elif hasattr(self.parent_window, '_current_lucidatrice_status'):
            # Lucidatrice - stato 0 = Idle
            stato = self.parent_window._current_lucidatrice_status
            if stato:
                try:
                    stato_num = stato.stato if hasattr(stato, 'stato') else 0
                    return stato_num == 0  # 0 = Idle
                except (AttributeError, TypeError):
                    return True
        elif hasattr(self.parent_window, '_current_multifilo_status'):
            # Multifilo - stato 0 = Idle
            stato = self.parent_window._current_multifilo_status
            if stato:
                try:
                    stato_num = stato.stato_macchina if hasattr(stato, 'stato_macchina') else (stato.stato if hasattr(stato, 'stato') else 0)
                    return stato_num == 0  # 0 = Idle
                except (AttributeError, TypeError):
                    return True
        
        return True
    
    def _aggiorna_stati_ordini(self):
        """Aggiorna gli stati degli ordini in base alla simulazione macchina"""
        if not self.parent_window:
            return
        
        # Usa funzioni helper per determinare stato macchina
        is_running = self._is_machine_running()
        is_stopped = self._is_machine_stopped()
        
        # Trova ordine attualmente in produzione (se esiste)
        ordine_in_produzione = None
        for ordine in self.ordini_ricevuti:
            if ordine.get('stato') == 'IN PRODUZIONE':
                ordine_in_produzione = ordine
                break
        
        # Aggiorna stati ordini
        for ordine in self.ordini_ricevuti:
            # Inizializza stato se mancante
            if 'stato' not in ordine:
                ordine['stato'] = 'IN ARRIVO'
            
            stato_corrente = ordine.get('stato', 'IN ARRIVO')
            
            # LOGICA: IN ARRIVO → IN PRODUZIONE
            if is_running and stato_corrente == 'IN ARRIVO':
                # Prendi il primo ordine in arrivo (non può esserci ordine in produzione)
                if ordine_in_produzione is None:
                    ordini_in_arrivo = [o for o in self.ordini_ricevuti if o.get('stato') == 'IN ARRIVO']
                    if ordini_in_arrivo and ordini_in_arrivo[0] == ordine:
                        ordine['stato'] = 'IN PRODUZIONE'
                        ordine['timestamp_inizio_produzione'] = datetime.now().isoformat()
                        ordine_in_produzione = ordine
                        self._persist_stato_ordine(ordine, 'IN PRODUZIONE')
            
            # LOGICA: IN PRODUZIONE → COMPLETATO
            elif is_stopped and stato_corrente == 'IN PRODUZIONE':
                # Se macchina si è fermata e ordine era in produzione, completalo
                if 'timestamp_inizio_produzione' in ordine:
                    # Calcola durata produzione
                    try:
                        timestamp_inizio = datetime.fromisoformat(ordine['timestamp_inizio_produzione'])
                        durata_secondi = (datetime.now() - timestamp_inizio).total_seconds()
                        
                        # Completa solo se durata > soglia minima (es. 5 secondi per evitare completamenti accidentali)
                        if durata_secondi >= 5.0:
                            ordine['stato'] = 'COMPLETATO'
                            ordine['timestamp_fine_produzione'] = datetime.now().isoformat()
                            ordine['durata_produzione_secondi'] = int(durata_secondi)
                            ordine_in_produzione = None
                            self._persist_stato_ordine(ordine, 'COMPLETATO')
                    except (ValueError, TypeError) as e:
                        ordine['stato'] = 'COMPLETATO'
                        ordine['timestamp_fine_produzione'] = datetime.now().isoformat()
                        ordine_in_produzione = None
                        self._persist_stato_ordine(ordine, 'COMPLETATO')
                else:
                    ordine['stato'] = 'COMPLETATO'
                    ordine['timestamp_fine_produzione'] = datetime.now().isoformat()
                    ordine_in_produzione = None
                    self._persist_stato_ordine(ordine, 'COMPLETATO')

    def _persist_stato_ordine(self, ordine: dict, status: str) -> None:
        codice = ordine.get('codice') or ordine.get('order_id')
        if not codice:
            return
        try:
            from modules.orders_database import update_order_production_status
            update_order_production_status(codice, status)
        except Exception:
            pass
    
    def _popola_tabella(self):
        """Popola la tabella con gli ordini"""
        self.ordini_table.setRowCount(len(self.ordini_ricevuti))
        
        if not self.ordini_ricevuti:
            # Mostra messaggio "Nessun ordine"
            self.ordini_table.setRowCount(1)
            empty_item = QTableWidgetItem("Nessun ordine in arrivo")
            empty_item.setTextAlignment(Qt.AlignCenter)
            empty_item.setForeground(QColor(128, 128, 128))
            self.ordini_table.setItem(0, 0, empty_item)
            self.ordini_table.setSpan(0, 0, 1, 6)
            return
        
        # Ordina per timestamp (più recente in alto)
        ordini_ordinati = sorted(self.ordini_ricevuti, 
                                 key=lambda x: x.get('timestamp', ''), 
                                 reverse=True)
        
        for row_idx, ordine in enumerate(ordini_ordinati):
            # Codice ordine
            codice_item = QTableWidgetItem(ordine.get('codice', 'N/A'))
            self.ordini_table.setItem(row_idx, 0, codice_item)
            
            # Cliente
            cliente_item = QTableWidgetItem(ordine.get('cliente', 'N/A'))
            self.ordini_table.setItem(row_idx, 1, cliente_item)
            
            # Materiale
            materiale_item = QTableWidgetItem(ordine.get('materiale', 'N/A'))
            self.ordini_table.setItem(row_idx, 2, materiale_item)
            
            # Quantità
            quantita_item = QTableWidgetItem(str(ordine.get('quantita', 'N/A')))
            self.ordini_table.setItem(row_idx, 3, quantita_item)
            
            # Stato (con colore e durata)
            stato = ordine.get('stato', 'IN ARRIVO')
            stato_text = stato
            
            # Aggiungi durata se disponibile
            if stato == 'IN PRODUZIONE' and 'timestamp_inizio_produzione' in ordine:
                try:
                    timestamp_inizio = datetime.fromisoformat(ordine['timestamp_inizio_produzione'])
                    durata_secondi = int((datetime.now() - timestamp_inizio).total_seconds())
                    durata_minuti = durata_secondi // 60
                    durata_sec = durata_secondi % 60
                    stato_text = f"{stato} ({durata_minuti}m {durata_sec}s)"
                except (ValueError, TypeError):
                    pass
            elif stato == 'COMPLETATO' and 'durata_produzione_secondi' in ordine:
                durata_sec = ordine['durata_produzione_secondi']
                durata_minuti = durata_sec // 60
                durata_sec_resto = durata_sec % 60
                stato_text = f"{stato} ({durata_minuti}m {durata_sec_resto}s)"
            
            stato_item = QTableWidgetItem(stato_text)
            if stato == 'IN ARRIVO':
                stato_item.setForeground(QColor(255, 255, 0))  # Giallo
            elif stato == 'IN PRODUZIONE':
                stato_item.setForeground(QColor(0, 255, 0))  # Verde
            elif stato == 'COMPLETATO':
                stato_item.setForeground(QColor(0, 170, 255))  # Blu
            self.ordini_table.setItem(row_idx, 4, stato_item)
            
            # Timestamp
            timestamp_item = QTableWidgetItem(ordine.get('timestamp', 'N/A'))
            self.ordini_table.setItem(row_idx, 5, timestamp_item)
    
    def apply_stylesheet(self):
        """Applica lo stylesheet alla finestra"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0a0a15;
            }
        """)
    
    def closeEvent(self, event):
        """Gestisce chiusura finestra"""
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        event.accept()


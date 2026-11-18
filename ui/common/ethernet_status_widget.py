"""
Widget comune per visualizzazione stato connessione Ethernet PLC
Riutilizzabile in tutte le finestre macchina
"""

from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class EthernetStatusWidget(QGroupBox):
    """Widget per visualizzare stato connessione PLC Ethernet"""
    
    def __init__(self, parent=None):
        super().__init__("Connessione PLC Ethernet", parent)
        self.init_ui()
    
    def init_ui(self):
        """Inizializza il widget"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # Stato connessione
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Stato: Non Connesso")
        self.status_label.setStyleSheet("color: #FF6B6B; font-size: 12px; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # IP e Porta
        self.ip_label = QLabel("IP: --")
        self.ip_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        layout.addWidget(self.ip_label)
        
        self.port_label = QLabel("Porta: --")
        self.port_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        layout.addWidget(self.port_label)
        
        # Latenza
        self.latency_label = QLabel("Latenza: -- ms")
        self.latency_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        layout.addWidget(self.latency_label)
        
        # Ultimo pacchetto
        self.last_packet_label = QLabel("Ultimo pacchetto: --")
        self.last_packet_label.setStyleSheet("color: #FFFFFF; font-size: 10px;")
        layout.addWidget(self.last_packet_label)
        
        # Separatore
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #3a3a4a;")
        layout.addWidget(separator)
        
        # Statistiche
        stats_label = QLabel("Statistiche:")
        stats_label.setStyleSheet("color: #FFFFFF; font-size: 10px; font-weight: bold;")
        layout.addWidget(stats_label)
        
        self.packets_label = QLabel("Pacchetti: 0")
        self.packets_label.setStyleSheet("color: #FFFFFF; font-size: 10px;")
        layout.addWidget(self.packets_label)
        
        self.errors_label = QLabel("Errori: 0")
        self.errors_label.setStyleSheet("color: #FFFFFF; font-size: 10px;")
        layout.addWidget(self.errors_label)
    
    def update_status(self, status_dict: dict):
        """
        Aggiorna il widget con lo stato della connessione
        
        Args:
            status_dict: Dizionario con stato (da PlcConnectionManager.get_status())
        """
        # Stato connessione
        connected = status_dict.get("connected", False)
        state = status_dict.get("state", "Disconnesso")
        
        if connected:
            self.status_label.setText(f"Stato: {state}")
            self.status_label.setStyleSheet("color: #51CF66; font-size: 12px; font-weight: bold;")
        elif state == "In Connessione" or state == "Riconnessione":
            self.status_label.setText(f"Stato: {state}")
            self.status_label.setStyleSheet("color: #FFD93D; font-size: 12px; font-weight: bold;")
        else:
            self.status_label.setText(f"Stato: {state}")
            self.status_label.setStyleSheet("color: #FF6B6B; font-size: 12px; font-weight: bold;")
        
        # IP e Porta
        ip = status_dict.get("ip", "--")
        port = status_dict.get("port", "--")
        self.ip_label.setText(f"IP: {ip}")
        self.port_label.setText(f"Porta: {port}")
        
        # Latenza
        latency = status_dict.get("latency_ms", 0)
        if latency > 200:
            color = "#FF6B6B"
        elif latency > 50:
            color = "#FFD93D"
        else:
            color = "#51CF66"
        self.latency_label.setText(f"Latenza: {latency} ms")
        self.latency_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        
        # Ultimo pacchetto
        last_packet = status_dict.get("last_packet_time")
        if last_packet:
            self.last_packet_label.setText(f"Ultimo pacchetto: {last_packet}")
        else:
            self.last_packet_label.setText("Ultimo pacchetto: --")
        
        # Statistiche
        total_packets = status_dict.get("total_packets", 0)
        failed_packets = status_dict.get("failed_packets", 0)
        self.packets_label.setText(f"Pacchetti: {total_packets}")
        self.errors_label.setText(f"Errori: {failed_packets}")
        
        # Tooltip diagnostico
        tooltip = f"""Stato: {state}
IP: {ip}
Porta: {port}
Latenza: {latency} ms
Pacchetti totali: {total_packets}
Pacchetti falliti: {failed_packets}
Errori: {status_dict.get('error_count', 0)}
Ultimo errore: {status_dict.get('last_error', 'Nessuno')}"""
        self.setToolTip(tooltip)





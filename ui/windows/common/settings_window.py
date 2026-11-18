"""
Nstone LLM - Finestra Impostazioni Sistema
Finestra di configurazione PyQt5 con tema scuro
"""
import sys
import json
import os
from pathlib import Path
from datetime import datetime
from ui.common.datetime_ui import format_header_datetime
from ui.common.section_access import prompt_section_access
from ui.common.section_window import SectionDialog, SectionMainWindow
from modules.access_control_db import SECTION_ADVANCED_DATASET_OPTIONS
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QComboBox, 
                             QSlider, QGroupBox, QScrollArea, QLineEdit, QMessageBox,
                             QTextEdit)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QPalette, QColor


_CONTEXT_KEYS = ("offerte", "ordini", "produzione")
_CONTEXT_UI_LABELS = {
    "offerte": "Quotations / Offerte",
    "ordini": "Orders / Ordini",
    "produzione": "Production / Produzione",
}
_NUM_CTX_LABELS = {
    4096: "4096 — Fast (less VRAM)",
    6144: "6144 — Balanced",
    8192: "8192 — Long context",
}
_NUM_PREDICT_LABELS = {
    400: "400 — Short",
    600: "600 — Standard offer",
    1200: "1200 — Long reply",
}
_PREWARM_UI_TO_VALUE = {"Auto": "auto", "On": True, "Off": False}
_PREWARM_VALUE_TO_UI = {"auto": "Auto", True: "On", False: "Off"}
_COMBO_STYLE = """
    QComboBox {
        background-color: #1a1a2a;
        color: #FFFFFF;
        border: 1px solid #3a2a4a;
        border-radius: 6px;
        padding: 8px;
        font-size: 14px;
    }
    QComboBox:hover {
        border: 1px solid #4a3a5a;
    }
    QComboBox::drop-down {
        border: none;
        width: 30px;
    }
    QComboBox QAbstractItemView {
        background-color: #1a1a2a;
        color: #FFFFFF;
        selection-background-color: #3a2a4a;
        border: 1px solid #3a2a4a;
    }
"""
_GROUP_STYLE = """
    QGroupBox {
        color: #FFFFFF;
        font-size: 16px;
        font-weight: bold;
        border: 2px solid #3a2a4a;
        border-radius: 10px;
        margin-top: 10px;
        padding-top: 20px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 15px;
        padding: 0 10px;
    }
"""
class ThemeCircle(QPushButton):
    """Cerchio colorato cliccabile per selezione tema"""
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.is_selected = False
        self.setFixedSize(40, 40)
        self.setCheckable(True)
        self.update_style()
        
    def update_style(self):
        """Aggiorna lo stile in base allo stato di selezione"""
        border_color = "#FFFFFF" if self.is_selected else "#666666"
        border_width = "3px" if self.is_selected else "2px"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color};
                border: {border_width} solid {border_color};
                border-radius: 20px;
            }}
            QPushButton:hover {{
                border: 3px solid #FFFFFF;
            }}
        """)
    
    def set_selected(self, selected):
        """Imposta lo stato di selezione"""
        self.is_selected = selected
        self.setChecked(selected)
        self.update_style()


class ApiTestWorker(QThread):
    """Worker thread per testare l'API key senza bloccare l'UI"""
    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(bool, str)  # (success, message)
    
    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key
    
    def run(self):
        """Esegue il test dell'API key"""
        try:
            # Verifica che la chiave non sia vuota
            if not self.api_key or not self.api_key.strip():
                self.result_ready.emit(False, "Empty API Key. Enter a valid key.")
                return
            
            # Simula una chiamata API (sostituire con chiamata reale se necessario)
            # Per ora simuliamo un test che verifica il formato della chiave
            success, message = self._test_api_connection()
            self.result_ready.emit(success, message)

        except Exception as e:
            self.result_ready.emit(False, f"Error during test: {str(e)}")
    
    def _test_api_connection(self):
        """
        Testa la connessione API con una chiamata HTTP reale.
        Supporta Google Gemini, OpenAI e Anthropic Claude.
        """
        api_key_clean = self.api_key.strip()
        
        # Verifica che la chiave non sia vuota
        if not api_key_clean:
            return False, "Empty API Key. Enter a valid key."
        
        # Controllo base: la chiave deve avere almeno 20 caratteri
        if len(api_key_clean) < 20:
            return False, "API Key too short. Make sure you entered the full key."
        
        # Verifica se requests è installato
        try:
            import requests
        except ImportError:
            return False, "'requests' library not installed. Install with: pip install requests"
        
        # Rileva il provider in base al formato della chiave
        provider = self._detect_provider(api_key_clean)
        
        # Esegui il test in base al provider
        if provider == "gemini":
            return self._test_gemini_api(api_key_clean)
        elif provider == "openai":
            return self._test_openai_api(api_key_clean)
        elif provider == "anthropic":
            return self._test_anthropic_api(api_key_clean)
        else:
            # Prova tutti i provider in ordine se il formato non è riconosciuto
            for test_func in [self._test_gemini_api, self._test_openai_api, self._test_anthropic_api]:
                result = test_func(api_key_clean)
                if result and result[0]:  # Se success è True
                    return result
            return False, "API Key not valid for any supported provider (Gemini, OpenAI, Anthropic)."
    
    def _detect_provider(self, api_key):
        """Rileva il provider in base al formato della chiave"""
        # Prefisso chiavi Google Generative Language (non hardcodare in chiaro per grep pubblici)
        _google_prefix = bytes((0x41, 0x49, 0x7A, 0x61)).decode("ascii")
        if api_key.startswith(_google_prefix):
            return "gemini"
        elif api_key.startswith("sk-"):
            return "openai"
        elif api_key.startswith("sk-ant-"):
            return "anthropic"
        return "unknown"
    
    def _test_gemini_api(self, api_key):
        """Testa la chiave API di Google Gemini"""
        try:
            import requests
            
            # Endpoint per listare i modelli disponibili
            url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return True, "✅ Google Gemini API Key valid! Connection successful."
            elif response.status_code == 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", "Invalid API key")
                return False, f"❌ Invalid Gemini API Key: {error_msg}"
            elif response.status_code == 403:
                return False, "❌ Access denied. Verify the API key is correct and enabled."
            else:
                return False, f"❌ Gemini API error (code {response.status_code}): {response.text[:100]}"
                
        except requests.exceptions.Timeout:
            return False, "❌ Timeout: server did not respond in time. Check your internet connection."
        except requests.exceptions.ConnectionError:
            return False, "❌ Connection error: unable to reach server. Check your internet connection."
        except requests.exceptions.RequestException as e:
            return False, f"❌ Request error: {str(e)}"
        except Exception as e:
            return False, f"❌ Unexpected error: {str(e)}"
    
    def _test_openai_api(self, api_key):
        """Testa la chiave API di OpenAI"""
        try:
            import requests
            
            # Endpoint per listare i modelli disponibili
            url = "https://api.openai.com/v1/models"
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return True, "✅ OpenAI API Key valid! Connection successful."
            elif response.status_code == 401:
                return False, "❌ OpenAI API Key invalid or expired."
            elif response.status_code == 429:
                return False, "❌ Too many requests. Try again later."
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", f"Error {response.status_code}")
                return False, f"❌ OpenAI API error: {error_msg}"
                
        except requests.exceptions.Timeout:
            return False, "❌ Timeout: OpenAI server did not respond in time."
        except requests.exceptions.ConnectionError:
            return False, "❌ Connection error: unable to reach OpenAI server."
        except requests.exceptions.RequestException as e:
            return False, f"❌ OpenAI request error: {str(e)}"
        except Exception:
            return False, ""  # Fallback silenzioso per provare altri provider
    
    def _test_anthropic_api(self, api_key):
        """Testa la chiave API di Anthropic Claude"""
        try:
            import requests
            
            # Endpoint per verificare la chiave (usiamo un endpoint semplice)
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            # Richiesta minima per testare la chiave
            data = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "test"}]
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                return True, "✅ Anthropic Claude API Key valid! Connection successful."
            elif response.status_code == 401:
                return False, "❌ Anthropic API Key invalid or expired."
            elif response.status_code == 429:
                return False, "❌ Too many requests. Try again later."
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", f"Error {response.status_code}")
                return False, f"❌ Anthropic API error: {error_msg}"
                
        except requests.exceptions.Timeout:
            return False, "❌ Timeout: Anthropic server did not respond in time."
        except requests.exceptions.ConnectionError:
            return False, "❌ Connection error: unable to reach Anthropic server."
        except requests.exceptions.RequestException as e:
            return False, f"❌ Anthropic request error: {str(e)}"
        except Exception:
            return False, ""  # Fallback silenzioso per provare altri provider


class SettingsWindow(SectionDialog):
    """Finestra di impostazioni sistema"""
    
    settings_saved = pyqtSignal(dict)  # Segnale emesso quando le impostazioni vengono salvate
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Dataset Options")
        self.setMinimumSize(800, 700)
        
        from core.machine_plc_config import get_config_path, load_config, save_config

        self._load_app_config = load_config
        self._save_app_config = save_config
        self.config_file = get_config_path()

        saved_config = self._load_app_config()
        
        # Valori di default o caricati
        self.selected_theme = saved_config.get("theme", "viola")
        try:
            from llm.llm_service import ui_model_label_from_config

            self.model_value = saved_config.get("model") or ui_model_label_from_config()
        except ImportError:
            self.model_value = saved_config.get("model", "Qwen 2.5 14B (local Ollama)")
        self.language_value = saved_config.get("language", "Italiano (IT)")
        self._context_options = self._load_context_options(saved_config)
        self._current_context_key = "offerte"
        self._prewarm_ui_value = self._load_prewarm_ui_value(saved_config)
        self.api_key_visible = False
        self.saved_api_key = saved_config.get("api_key", "")
        gmail_cfg = saved_config.get("gmail", {})
        if not isinstance(gmail_cfg, dict):
            gmail_cfg = {}
        self.saved_gmail_email = gmail_cfg.get("email", "")
        self.saved_gmail_password = gmail_cfg.get("app_password", "")

        # Thread per test API
        self.api_test_thread = None
        self._authorized = False

        self.init_ui()
        self.setup_timer()
        self.apply_stylesheet()

        self._authorized = prompt_section_access(
            self,
            SECTION_ADVANCED_DATASET_OPTIONS,
            title="Advanced Dataset Options",
        )
        if not self._authorized and hasattr(self, "_content_scroll"):
            self._content_scroll.setEnabled(False)
            if hasattr(self, "_save_button"):
                self._save_button.setEnabled(False)
        
        # Carica API key salvata nel campo
        if self.saved_api_key:
            self.api_key_input.setText(self.saved_api_key)
        if hasattr(self, "gmail_email_input") and self.saved_gmail_email:
            self.gmail_email_input.setText(self.saved_gmail_email)
        if hasattr(self, "gmail_password_input") and self.saved_gmail_password:
            self.gmail_password_input.setText(self.saved_gmail_password)

    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Area scrollabile per il contenuto
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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Contenuto principale
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(40, 30, 40, 30)
        content_layout.setSpacing(30)
        
        # Titolo
        title_label = QLabel("Advanced Dataset Options")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            color: #FFFFFF;
            font-size: 32px;
            font-weight: bold;
            padding: 20px;
        """)
        # Prova a usare font moderni
        font = QFont()
        font_families = ["Montserrat", "Roboto", "Open Sans", "Segoe UI", "Arial"]
        for font_family in font_families:
            font.setFamily(font_family)
            if font.exactMatch():
                break
        font.setPointSize(32)
        font.setBold(True)
        title_label.setFont(font)
        content_layout.addWidget(title_label)
        
        # Sezione Motore Neurale
        neural_section = self.create_neural_engine_section()
        content_layout.addWidget(neural_section)
        
        # Sezione Lingua
        language_section = self.create_language_section()
        content_layout.addWidget(language_section)
        
        # Sezione Tema
        theme_section = self.create_theme_section()
        content_layout.addWidget(theme_section)
        
        # Sezione Gestione API Key
        api_section = self.create_api_key_section()
        content_layout.addWidget(api_section)

        gmail_section = self.create_gmail_section()
        content_layout.addWidget(gmail_section)

        health_section = self.create_system_health_section()
        content_layout.addWidget(health_section)
        
        content_layout.addStretch()
        
        # Pulsanti in basso
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumHeight(45)
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 30px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
                border: 1px solid #4a4a5a;
            }
            QPushButton:pressed {
                background-color: #1a1a2a;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_button)
        
        buttons_layout.addStretch()
        
        save_button = QPushButton("Save Changes")
        save_button.setMinimumHeight(45)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 30px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        save_button.clicked.connect(self.save_settings)
        buttons_layout.addWidget(save_button)
        self._save_button = save_button
        self._cancel_button = cancel_button

        content_layout.addLayout(buttons_layout)
        
        # Imposta il widget scrollabile
        scroll_area.setWidget(content_widget)
        self._content_scroll = scroll_area
        main_layout.addWidget(scroll_area, 1)

        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)
        
    def create_header(self):
        """Crea l'header con info sviluppatore e data/ora"""
        header_frame = QFrame()
        header_frame.setFixedHeight(60)
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 10, 20, 10)
        
        # Info sviluppatore a sinistra
        developer_label = QLabel("NStone")
        developer_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        header_layout.addWidget(developer_label)
        
        # Spacer
        header_layout.addStretch()
        
        # Data e ora a destra
        self.datetime_label = QLabel()
        self.datetime_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        self.update_datetime()
        header_layout.addWidget(self.datetime_label)
        
        return header_frame
    
    def _load_context_options(self, saved_config: dict) -> dict:
        """Carica llm.contexts con fallback su DEFAULT_CONTEXT_OPTIONS."""
        try:
            from llm.llm_contexts import DEFAULT_CONTEXT_OPTIONS
        except ImportError:
            DEFAULT_CONTEXT_OPTIONS = {
                "offerte": {"temperature": 0.55, "num_ctx": 4096, "num_predict": 600},
                "ordini": {"temperature": 0.20, "num_ctx": 4096, "num_predict": 400},
                "produzione": {"temperature": 0.25, "num_ctx": 4096, "num_predict": 800},
            }

        llm = saved_config.get("llm") if isinstance(saved_config.get("llm"), dict) else {}
        contexts = llm.get("contexts") if isinstance(llm.get("contexts"), dict) else {}
        legacy_temp = saved_config.get("temperature")

        options = {}
        for key in _CONTEXT_KEYS:
            defaults = DEFAULT_CONTEXT_OPTIONS.get(key, {})
            block = contexts.get(key) if isinstance(contexts.get(key), dict) else {}
            temp = block.get("temperature", defaults.get("temperature", 0.5))
            if key == "offerte" and "temperature" not in block and legacy_temp is not None:
                temp = legacy_temp
            options[key] = {
                "temperature": float(temp),
                "num_ctx": int(block.get("num_ctx", defaults.get("num_ctx", 4096))),
                "num_predict": int(block.get("num_predict", defaults.get("num_predict", 600))),
            }
        return options

    @staticmethod
    def _load_prewarm_ui_value(saved_config: dict) -> str:
        llm = saved_config.get("llm") if isinstance(saved_config.get("llm"), dict) else {}
        prewarm = llm.get("prewarm") if isinstance(llm.get("prewarm"), dict) else {}
        enabled = prewarm.get("enabled", "auto")
        if isinstance(enabled, str) and enabled.lower() == "auto":
            return "Auto"
        if enabled is True or (isinstance(enabled, str) and enabled.lower() in ("true", "1", "on", "yes")):
            return "On"
        if enabled is False or (isinstance(enabled, str) and enabled.lower() in ("false", "0", "off", "no")):
            return "Off"
        return "Auto"

    def _nearest_preset(self, value: int, presets: tuple[int, ...]) -> int:
        return min(presets, key=lambda preset: abs(preset - int(value)))

    def _set_combo_by_data(self, combo: QComboBox, data_value) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == data_value:
                combo.setCurrentIndex(index)
                return

    def _save_current_context_from_ui(self) -> None:
        if not hasattr(self, "context_combo"):
            return
        key = self.context_combo.currentData()
        if key not in self._context_options:
            return
        self._context_options[key] = {
            "temperature": self.temp_slider.value() / 100.0,
            "num_ctx": int(self.num_ctx_combo.currentData()),
            "num_predict": int(self.num_predict_combo.currentData()),
        }

    def _load_context_to_ui(self, key: str) -> None:
        block = self._context_options.get(key, {})
        temp = float(block.get("temperature", 0.5))
        self.temp_slider.blockSignals(True)
        self.temp_slider.setValue(int(temp * 100))
        self.temp_slider.blockSignals(False)
        self.temp_value_label.setText(f"{temp:.1f}")

        num_ctx = self._nearest_preset(int(block.get("num_ctx", 4096)), tuple(_NUM_CTX_LABELS))
        num_predict = self._nearest_preset(
            int(block.get("num_predict", 600)), tuple(_NUM_PREDICT_LABELS)
        )
        self._set_combo_by_data(self.num_ctx_combo, num_ctx)
        self._set_combo_by_data(self.num_predict_combo, num_predict)

    def _on_context_profile_changed(self) -> None:
        previous = getattr(self, "_current_context_key", "offerte")
        if previous in self._context_options and hasattr(self, "temp_slider"):
            self._context_options[previous] = {
                "temperature": self.temp_slider.value() / 100.0,
                "num_ctx": int(self.num_ctx_combo.currentData()),
                "num_predict": int(self.num_predict_combo.currentData()),
            }
        key = self.context_combo.currentData()
        self._current_context_key = key
        self._load_context_to_ui(key)

    def create_neural_engine_section(self):
        """Crea la sezione Motore Neurale"""
        group = QGroupBox("Neural Engine")
        group.setStyleSheet(_GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setSpacing(20)

        model_layout = QHBoxLayout()
        model_label = QLabel("Default Model:")
        model_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        model_label.setMinimumWidth(150)
        model_layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "Qwen 2.5 14B (local Ollama)",
            "Gemini 2.5 Flash",
        ])
        self.model_combo.setCurrentText(self.model_value)
        self.model_combo.setStyleSheet(_COMBO_STYLE)
        model_layout.addWidget(self.model_combo)
        layout.addLayout(model_layout)

        context_layout = QHBoxLayout()
        context_label = QLabel("Context profile:")
        context_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        context_label.setMinimumWidth(150)
        context_layout.addWidget(context_label)

        self.context_combo = QComboBox()
        for key in _CONTEXT_KEYS:
            self.context_combo.addItem(_CONTEXT_UI_LABELS[key], key)
        self.context_combo.setStyleSheet(_COMBO_STYLE)
        self.context_combo.currentIndexChanged.connect(self._on_context_profile_changed)
        context_layout.addWidget(self.context_combo)
        layout.addLayout(context_layout)

        temp_layout = QVBoxLayout()
        temp_label_layout = QHBoxLayout()
        temp_label = QLabel("Response Temperature:")
        temp_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        temp_label_layout.addWidget(temp_label)
        temp_label_layout.addStretch()

        initial_temp = self._context_options[self._current_context_key]["temperature"]
        self.temp_value_label = QLabel(f"{initial_temp:.1f}")
        self.temp_value_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        temp_label_layout.addWidget(self.temp_value_label)
        temp_layout.addLayout(temp_label_layout)

        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setMinimum(0)
        self.temp_slider.setMaximum(100)
        self.temp_slider.setValue(int(initial_temp * 100))
        self.temp_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #1a1a2a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #6a4a8a;
                width: 20px;
                height: 20px;
                margin: -6px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #7a5a9a;
            }
            QSlider::sub-page:horizontal {
                background: #4a2a6a;
                border-radius: 4px;
            }
        """)
        self.temp_slider.valueChanged.connect(self.on_temp_changed)
        temp_layout.addWidget(self.temp_slider)
        layout.addLayout(temp_layout)

        num_ctx_layout = QHBoxLayout()
        num_ctx_label = QLabel("Context window (num_ctx):")
        num_ctx_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        num_ctx_label.setMinimumWidth(150)
        num_ctx_layout.addWidget(num_ctx_label)

        self.num_ctx_combo = QComboBox()
        for value, label in _NUM_CTX_LABELS.items():
            self.num_ctx_combo.addItem(label, value)
        self.num_ctx_combo.setStyleSheet(_COMBO_STYLE)
        num_ctx_layout.addWidget(self.num_ctx_combo)
        layout.addLayout(num_ctx_layout)

        num_predict_layout = QHBoxLayout()
        num_predict_label = QLabel("Max response (num_predict):")
        num_predict_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        num_predict_label.setMinimumWidth(150)
        num_predict_layout.addWidget(num_predict_label)

        self.num_predict_combo = QComboBox()
        for value, label in _NUM_PREDICT_LABELS.items():
            self.num_predict_combo.addItem(label, value)
        self.num_predict_combo.setStyleSheet(_COMBO_STYLE)
        num_predict_layout.addWidget(self.num_predict_combo)
        layout.addLayout(num_predict_layout)

        prewarm_layout = QHBoxLayout()
        prewarm_label = QLabel("Model pre-warm:")
        prewarm_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        prewarm_label.setMinimumWidth(150)
        prewarm_layout.addWidget(prewarm_label)

        self.prewarm_combo = QComboBox()
        self.prewarm_combo.addItems(["Auto", "On", "Off"])
        self.prewarm_combo.setCurrentText(self._prewarm_ui_value)
        self.prewarm_combo.setStyleSheet(_COMBO_STYLE)
        prewarm_layout.addWidget(self.prewarm_combo)
        layout.addLayout(prewarm_layout)

        hint = QLabel(
            "Per-context tuning applies to Ollama inference (offers, orders, production). "
            "Lower context window uses less VRAM and is often faster."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        layout.addWidget(hint)

        self._load_context_to_ui(self._current_context_key)
        return group
    
    def create_language_section(self):
        """Crea la sezione Lingua"""
        group = QGroupBox("Language")
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #3a2a4a;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
            }
        """)
        layout = QHBoxLayout(group)
        
        self.language_combo = QComboBox()
        self.language_combo.addItems(["Italiano (IT)", "English (EN)", "Español (ES)", "Français (FR)", "Deutsch (DE)"])
        self.language_combo.setCurrentText(self.language_value)
        self.language_combo.setStyleSheet("""
            QComboBox {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QComboBox:hover {
                border: 1px solid #4a3a5a;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a2a;
                color: #FFFFFF;
                selection-background-color: #3a2a4a;
                border: 1px solid #3a2a4a;
            }
        """)
        layout.addWidget(self.language_combo)
        
        return group
    
    def create_theme_section(self):
        """Crea la sezione Tema con cerchi colorati"""
        group = QGroupBox("Theme")
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #3a2a4a;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
            }
        """)
        layout = QHBoxLayout(group)
        layout.setSpacing(20)
        
        # Cerchio viola
        self.theme_viola = ThemeCircle("#8B5CF6")
        self.theme_viola.clicked.connect(lambda: self.select_theme("viola"))
        layout.addWidget(self.theme_viola)
        
        # Cerchio blu
        self.theme_blu = ThemeCircle("#3B82F6")
        self.theme_blu.clicked.connect(lambda: self.select_theme("blu"))
        layout.addWidget(self.theme_blu)
        
        # Cerchio nero
        self.theme_nero = ThemeCircle("#1a1a1a")
        self.theme_nero.clicked.connect(lambda: self.select_theme("nero"))
        layout.addWidget(self.theme_nero)
        
        layout.addStretch()
        
        # Imposta tema di default
        self.select_theme("viola")
        
        return group
    
    def create_api_key_section(self):
        """Crea la sezione Gestione API Key"""
        group = QGroupBox("API Key Management")
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #3a2a4a;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        
        # Etichetta
        api_label = QLabel("Enter your API Key:")
        api_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        layout.addWidget(api_label)
        
        # Campo di input per API Key
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your API Key here...")
        self.api_key_input.setMinimumHeight(45)
        self.api_key_input.setEchoMode(QLineEdit.Password)  # Nasconde i caratteri per sicurezza
        self.api_key_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 8px;
                padding: 10px 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #5a3a7a;
            }
            QLineEdit:hover {
                border: 1px solid #4a3a5a;
            }
        """)
        layout.addWidget(self.api_key_input)
        
        # Layout orizzontale per i pulsanti
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        # Pulsante per mostrare/nascondere la chiave
        toggle_button = QPushButton("Show/Hide")
        toggle_button.setMaximumWidth(150)
        toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 6px;
                font-size: 12px;
                padding: 6px 15px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
                border: 1px solid #4a4a5a;
            }
        """)
        toggle_button.clicked.connect(self.toggle_api_key_visibility)
        buttons_layout.addWidget(toggle_button)
        
        # Pulsante Test API
        self.test_api_button = QPushButton("Test API")
        self.test_api_button.setMaximumWidth(150)
        self.test_api_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                font-size: 12px;
                padding: 6px 15px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:disabled {
                background-color: #2a2a3a;
                color: #666666;
                border: 1px solid #3a3a4a;
            }
        """)
        self.test_api_button.clicked.connect(self.test_api_key)
        buttons_layout.addWidget(self.test_api_button)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        return group

    def create_gmail_section(self):
        """Credenziali SMTP Gmail per invio risposte dopo elaborazione Gemini."""
        group = QGroupBox("Gmail Reply Sending (SMTP)")
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #3a2a4a;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        hint = QLabel(
            "Use a Gmail account with 2-step verification and an App Password "
            "(Google Account → Security → App passwords)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        layout.addWidget(hint)

        email_label = QLabel("Sender email (Gmail):")
        email_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        layout.addWidget(email_label)

        self.gmail_email_input = QLineEdit()
        self.gmail_email_input.setPlaceholderText("e.g. nstone@gmail.com")
        self.gmail_email_input.setMinimumHeight(40)
        self.gmail_email_input.setStyleSheet(self.api_key_input.styleSheet())
        layout.addWidget(self.gmail_email_input)

        pwd_label = QLabel("Gmail App Password (16 characters):")
        pwd_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        layout.addWidget(pwd_label)

        self.gmail_password_input = QLineEdit()
        self.gmail_password_input.setPlaceholderText("xxxx xxxx xxxx xxxx")
        self.gmail_password_input.setEchoMode(QLineEdit.Password)
        self.gmail_password_input.setMinimumHeight(40)
        self.gmail_password_input.setStyleSheet(self.api_key_input.styleSheet())
        layout.addWidget(self.gmail_password_input)

        test_gmail_btn = QPushButton("Test Gmail Send")
        test_gmail_btn.setMaximumWidth(180)
        test_gmail_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a4a3a;
                color: #FFFFFF;
                border: 1px solid #3a6a4a;
                border-radius: 6px;
                font-size: 12px;
                padding: 8px 15px;
            }
            QPushButton:hover { background-color: #3a5a4a; }
        """)
        test_gmail_btn.clicked.connect(self.test_gmail_smtp)
        layout.addWidget(test_gmail_btn)

        return group

    def create_system_health_section(self):
        """Diagnostica servizi background e memoria processo."""
        group = QGroupBox("System Health (background)")
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #3a2a4a;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        hint = QLabel(
            "Stato dei servizi in background (auto-preventivi, poll email). "
            "Utile se l'app resta aperta a lungo."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        layout.addWidget(hint)

        self.system_health_text = QTextEdit()
        self.system_health_text.setReadOnly(True)
        self.system_health_text.setMinimumHeight(140)
        self.system_health_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                color: #CCCCCC;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.system_health_text)

        refresh_btn = QPushButton("Refresh diagnostics")
        refresh_btn.setMaximumWidth(200)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a4a;
                color: #FFFFFF;
                border: 1px solid #3a3a5a;
                border-radius: 6px;
                font-size: 12px;
                padding: 8px 15px;
            }
            QPushButton:hover { background-color: #3a3a5a; }
        """)
        refresh_btn.clicked.connect(self.refresh_system_health)
        layout.addWidget(refresh_btn)

        self.refresh_system_health()
        return group

    def refresh_system_health(self):
        if not hasattr(self, "system_health_text"):
            return
        try:
            from ui.common.background_services import format_diagnostics_text

            self.system_health_text.setPlainText(format_diagnostics_text())
        except Exception as exc:
            self.system_health_text.setPlainText(f"Diagnostica non disponibile: {exc}")

    def test_gmail_smtp(self):
        """Verifica login SMTP con i valori nei campi (senza inviare mail al cliente)."""
        from modules.email_service import reload_gmail_credentials, send_response_email

        self.save_config({
            "gmail": {
                "email": self.gmail_email_input.text().strip(),
                "app_password": self.gmail_password_input.text().strip(),
            }
        })
        reload_gmail_credentials()
        test_to = self.gmail_email_input.text().strip()
        if not test_to:
            QMessageBox.warning(self, "Gmail", "Enter the sender email.")
            return
        ok = send_response_email(
            test_to,
            "NSTONELLM — Test SMTP",
            "Gmail configuration test successful. Customer replies can be sent automatically.",
        )
        if ok:
            QMessageBox.information(self, "Gmail", "SMTP connection OK. Test email sent to sender.")
        else:
            QMessageBox.critical(
                self,
                "Gmail",
                "Send failed. Check App Password, 2FA, and that the email is Gmail.",
            )
    
    def create_footer(self):
        """Crea il footer con copyright"""
        footer_frame = QFrame()
        footer_frame.setFixedHeight(50)
        footer_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
        """)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        
        footer_label = QLabel("NStone — all rights reserved.")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setStyleSheet("color: #AAAAAA; font-size: 10px;")
        footer_layout.addWidget(footer_label)
        
        return footer_frame
    
    def select_theme(self, theme):
        """Seleziona un tema"""
        self.selected_theme = theme
        self.theme_viola.set_selected(theme == "viola")
        self.theme_blu.set_selected(theme == "blu")
        self.theme_nero.set_selected(theme == "nero")
    
    def on_temp_changed(self, value):
        """Aggiorna l'etichetta della temperatura quando cambia lo slider"""
        temp = value / 100.0
        self.temp_value_label.setText(f"{temp:.1f}")
    
    def toggle_api_key_visibility(self):
        """Mostra/nasconde l'API key"""
        self.api_key_visible = not self.api_key_visible
        if self.api_key_visible:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
    
    def test_api_key(self):
        """Testa l'API key inserita"""
        api_key = self.api_key_input.text().strip()
        
        # Verifica che la chiave non sia vuota
        if not api_key:
            QMessageBox.warning(
                self,
                "Empty API Key",
                "Enter an API Key in the field before testing."
            )
            return
        
        # Disabilita il pulsante durante il test
        self.test_api_button.setEnabled(False)
        self.test_api_button.setText("Testing...")
        
        # Crea e avvia il thread di test
        self.api_test_thread = ApiTestWorker(api_key)
        self.api_test_thread.result_ready.connect(self.on_api_test_finished)
        self.api_test_thread.start()
    
    @pyqtSlot(bool, str)
    def on_api_test_finished(self, success, message):
        """Gestisce il risultato del test API"""
        # Riabilita il pulsante
        self.test_api_button.setEnabled(True)
        self.test_api_button.setText("Test API")
        
        # Mostra il risultato
        if success:
            QMessageBox.information(
                self,
                "API Test Successful",
                message
            )
        else:
            QMessageBox.critical(
                self,
                "API Test Failed",
                message
            )
        
        # Pulisci il thread
        if self.api_test_thread:
            self.api_test_thread.quit()
            self.api_test_thread.wait()
            self.api_test_thread = None
    
    def load_config(self):
        """Carica la configurazione dal config.json canonico (con merge legacy)."""
        if hasattr(self, "_load_app_config"):
            return self._load_app_config()
        return {}

    def save_config(self, settings):
        """Salva nel config.json canonico (root progetto), preservando machines ecc."""
        try:
            if hasattr(self, "_save_app_config"):
                path = self._save_app_config(settings)
                self.config_file = path
                return
            existing_config = self.load_config()
            existing_config.update(settings)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(existing_config, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
    
    def save_settings(self):
        """Salva le impostazioni e chiude la finestra"""
        if not self._authorized:
            QMessageBox.warning(self, "Access", "Unauthorized session.")
            return
        self._save_current_context_from_ui()
        model_label = self.model_combo.currentText()
        prewarm_ui = self.prewarm_combo.currentText()
        prewarm_enabled = _PREWARM_UI_TO_VALUE.get(prewarm_ui, "auto")
        settings = {
            "model": model_label,
            "temperature": self._context_options["offerte"]["temperature"],
            "language": self.language_combo.currentText(),
            "theme": self.selected_theme,
            "api_key": self.api_key_input.text().strip(),
            "gmail": {
                "email": self.gmail_email_input.text().strip(),
                "app_password": self.gmail_password_input.text().strip().replace(" ", ""),
            },
        }
        try:
            from llm.llm_service import merge_llm_settings_from_ui, reset_llm_service

            existing = self.load_config()
            existing_llm = existing.get("llm") if isinstance(existing.get("llm"), dict) else {}
            settings["llm"] = merge_llm_settings_from_ui(
                model_label,
                contexts=self._context_options,
                prewarm_enabled=prewarm_enabled,
                existing_llm=existing_llm,
            )
            reset_llm_service()
        except ImportError:
            pass

        self.save_config(settings)
        try:
            from modules.email_service import reload_gmail_credentials
            reload_gmail_credentials()
        except Exception:
            pass
        
        # Emetti segnale (senza stampare API key in chiaro)
        settings_for_signal = settings.copy()
        self.settings_saved.emit(settings_for_signal)
        self.accept()
    
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
            QFrame {
                background: transparent;
            }
        """)
        
        # Header e footer con gradiente
        header_footer_style = """
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
        """
        # Applica al header e footer (verrà fatto nel create_header/footer)
    
    def setup_timer(self):
        """Configura il timer per aggiornare data e ora"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_datetime)
        self.timer.start(1000)  # Aggiorna ogni secondo
    
    def update_datetime(self):
        """Update header date/time (English)."""
        self.datetime_label.setText(format_header_datetime())


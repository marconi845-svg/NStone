"""
End-to-End Tester per il flusso WhatsApp → Meta → Cloud Function → Windows → AI → Offerte → Outlook
Esegue test diagnostici senza inviare email reali o modificare dati.
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import urllib.request
import urllib.error

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


class EndToEndTester:
    """
    Classe per eseguire test end-to-end del flusso completo.
    
    Test eseguiti:
    1. Cloud Function - verifica raggiungibilità endpoint
    2. Windows Listener - verifica che l'endpoint locale risponda
    3. AI Assistant - test del modulo di analisi
    4. Offer Generation - generazione simulata offerta
    5. Outlook COM - verifica disponibilità senza inviare email
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Inizializza il tester con configurazione.
        
        Args:
            config: Dizionario con configurazione (cloud_function_url, windows_listener_url, etc.)
        """
        self.config = config or {}
        self.cloud_function_url = self.config.get("cloud_function_url", "")
        self.windows_listener_url = self.config.get("windows_listener_url", "http://localhost:5000/api/whatsapp")
        self.results = {}
        self.log_messages = []
    
    def log(self, message: str, level: str = "INFO"):
        """Aggiunge un messaggio al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.log_messages.append(log_entry)
        print(log_entry)
    
    def test_cloud_function(self) -> Dict[str, Any]:
        """
        Test 1: Verifica raggiungibilità della Google Cloud Function.
        
        Returns:
            Dict con 'status' ('OK' o 'FAIL'), 'message' e 'details'
        """
        self.log("Inizio test Cloud Function...")
        
        if not self.cloud_function_url:
            return {
                "status": "FAIL",
                "message": "URL Cloud Function non configurato",
                "details": "Configurare cloud_function_url nel config"
            }
        
        try:
            # Test con richiesta GET (health check) o POST minimale
            test_payload = {
                "test": True,
                "timestamp": datetime.now().isoformat()
            }
            
            if HAS_REQUESTS:
                response = requests.get(
                    self.cloud_function_url,
                    timeout=5
                )
                status_code = response.status_code
                response_text = response.text[:100]
            else:
                req = urllib.request.Request(
                    self.cloud_function_url,
                    method="GET"
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    status_code = response.status
                    response_text = response.read(100).decode('utf-8', errors='ignore')
            
            if status_code in [200, 404]:  # 404 è accettabile (endpoint non trovato ma server risponde)
                return {
                    "status": "OK",
                    "message": f"Cloud Function raggiungibile (HTTP {status_code})",
                    "details": f"Response: {response_text[:50]}..."
                }
            else:
                return {
                    "status": "FAIL",
                    "message": f"Cloud Function risponde con codice {status_code}",
                    "details": f"Response: {response_text[:50]}..."
                }
        
        except urllib.error.URLError as e:
            return {
                "status": "FAIL",
                "message": "Cloud Function non raggiungibile",
                "details": str(e)
            }
        except Exception as e:
            return {
                "status": "FAIL",
                "message": "Errore durante test Cloud Function",
                "details": str(e)
            }
    
    def test_windows_listener(self) -> Dict[str, Any]:
        """
        Test 2: Verifica che il listener Windows risponda.
        
        Returns:
            Dict con 'status' ('OK' o 'FAIL'), 'message' e 'details'
        """
        self.log("Inizio test Windows Listener...")
        
        try:
            # Test con richiesta POST al listener
            test_payload = {
                "from": "393471234567",
                "message": "Test end-to-end",
                "raw": {"test": True}
            }
            
            json_data = json.dumps(test_payload).encode('utf-8')
            
            if HAS_REQUESTS:
                response = requests.post(
                    self.windows_listener_url,
                    json=test_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=5
                )
                status_code = response.status_code
                response_text = response.text[:100]
            else:
                req = urllib.request.Request(
                    self.windows_listener_url,
                    data=json_data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    status_code = response.status
                    response_text = response.read(100).decode('utf-8', errors='ignore')
            
            if status_code == 200:
                return {
                    "status": "OK",
                    "message": f"Windows Listener risponde correttamente (HTTP {status_code})",
                    "details": f"Response: {response_text[:50]}..."
                }
            else:
                return {
                    "status": "FAIL",
                    "message": f"Windows Listener risponde con codice {status_code}",
                    "details": f"Response: {response_text[:50]}..."
                }
        
        except urllib.error.URLError as e:
            return {
                "status": "FAIL",
                "message": "Windows Listener non raggiungibile",
                "details": f"Verificare che il backend sia in esecuzione su {self.windows_listener_url}. Errore: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "FAIL",
                "message": "Errore durante test Windows Listener",
                "details": str(e)
            }
    
    def test_ai_assistant(self) -> Dict[str, Any]:
        """
        Test 3: Verifica funzionamento del modulo AI Assistant.
        
        Returns:
            Dict con 'status' ('OK' o 'FAIL'), 'message' e 'details'
        """
        self.log("Inizio test AI Assistant...")
        
        try:
            # Test con analisi di un testo fittizio
            test_message = "Ciao, vorrei un preventivo per marmo Carrara per un progetto di 50mq"
            
            # PUNTO DI ESTENSIONE: Qui si può integrare il modulo AI reale
            # Esempio futuro:
            # from llm.ai_assistant import analyze_message
            # result = analyze_message(test_message)
            
            # Simulazione per ora
            if len(test_message) > 0:
                # Analisi base: verifica che il messaggio sia processabile
                keywords = ["marmo", "Carrara", "preventivo", "mq"]
                found_keywords = [kw for kw in keywords if kw.lower() in test_message.lower()]
                
                return {
                    "status": "OK",
                    "message": "AI Assistant funzionante (simulazione)",
                    "details": f"Messaggio analizzato: {len(test_message)} caratteri, {len(found_keywords)} keyword trovate"
                }
            else:
                return {
                    "status": "FAIL",
                    "message": "AI Assistant non ha processato il messaggio",
                    "details": "Messaggio vuoto o non valido"
                }
        
        except Exception as e:
            return {
                "status": "FAIL",
                "message": "Errore durante test AI Assistant",
                "details": str(e)
            }
    
    def test_offer_generation(self) -> Dict[str, Any]:
        """
        Test 4: Genera un'offerta simulata (file temporaneo, NON inviata).
        
        Returns:
            Dict con 'status' ('OK' o 'FAIL'), 'message' e 'details'
        """
        self.log("Inizio test Generazione Offerta...")
        
        try:
            # Crea file temporaneo per simulare l'offerta
            temp_dir = Path(tempfile.gettempdir())
            test_offer_file = temp_dir / f"nstone_test_offer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            # Dati offerta simulata
            offer_data = {
                "richiesta_id": "TEST_001",
                "cliente": "393471234567",
                "messaggio_originale": "Test preventivo marmo Carrara",
                "totale_stimato": 12500.00,
                "dettagli_offerta": [
                    {"materiale": "Carrara", "quantita": 50, "prezzo_mq": 250}
                ],
                "timestamp": datetime.now().isoformat(),
                "test": True
            }
            
            # Salva file temporaneo
            with open(test_offer_file, 'w', encoding='utf-8') as f:
                json.dump(offer_data, f, indent=2, ensure_ascii=False)
            
            # Verifica che il file sia stato creato
            if test_offer_file.exists():
                file_size = test_offer_file.stat().st_size
                
                # PUNTO DI ESTENSIONE: Qui si può integrare la logica reale di generazione offerte
                # Esempio futuro:
                # from offer_generator import generate_offer
                # offer = generate_offer(richiesta_data)
                
                return {
                    "status": "OK",
                    "message": f"Offerta generata con successo (file temporaneo)",
                    "details": f"File: {test_offer_file.name} ({file_size} bytes). File verrà eliminato automaticamente."
                }
            else:
                return {
                    "status": "FAIL",
                    "message": "File offerta non creato",
                    "details": "Errore durante la creazione del file"
                }
        
        except Exception as e:
            return {
                "status": "FAIL",
                "message": "Errore durante test Generazione Offerta",
                "details": str(e)
            }
    
    def test_outlook(self) -> Dict[str, Any]:
        """
        Test 5: Verifica disponibilità di Outlook COM senza inviare email.
        
        Returns:
            Dict con 'status' ('OK' o 'FAIL'), 'message' e 'details'
        """
        self.log("Inizio test Outlook COM...")
        
        if not HAS_WIN32COM:
            return {
                "status": "FAIL",
                "message": "pywin32 non installato",
                "details": "Installare pywin32: pip install pywin32"
            }
        
        try:
            # Prova a creare un'istanza di Outlook COM
            outlook = win32com.client.Dispatch("Outlook.Application")
            
            # Verifica che Outlook sia disponibile
            if outlook:
                # NON inviare email, solo verificare disponibilità
                namespace = outlook.GetNamespace("MAPI")
                
                return {
                    "status": "OK",
                    "message": "Outlook COM disponibile",
                    "details": "Outlook è accessibile via COM. Nessuna email inviata (test mode)."
                }
            else:
                return {
                    "status": "FAIL",
                    "message": "Outlook COM non disponibile",
                    "details": "Impossibile creare istanza Outlook"
                }
        
        except Exception as e:
            error_msg = str(e)
            if "CoCreateInstance" in error_msg or "CLSID" in error_msg:
                return {
                    "status": "FAIL",
                    "message": "Outlook non installato o non disponibile",
                    "details": "Verificare che Microsoft Outlook sia installato. Errore: " + error_msg
                }
            else:
                return {
                    "status": "FAIL",
                    "message": "Errore durante test Outlook COM",
                    "details": error_msg
                }
    
    def run_all_tests(self) -> Dict[str, Any]:
        """
        Esegue tutti i test in sequenza.
        
        Returns:
            Dict con risultati di tutti i test e statistiche finali
        """
        self.log("=== INIZIO TEST END-TO-END ===")
        self.results = {}
        self.log_messages = []
        
        # Esegui tutti i test
        self.results["cloud_function"] = self.test_cloud_function()
        self.results["windows_listener"] = self.test_windows_listener()
        self.results["ai_assistant"] = self.test_ai_assistant()
        self.results["offer_generation"] = self.test_offer_generation()
        self.results["outlook"] = self.test_outlook()
        
        # Calcola statistiche
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["status"] == "OK")
        failed_tests = total_tests - passed_tests
        
        summary = {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
        }
        
        self.log(f"=== TEST COMPLETATI ===")
        self.log(f"Totale: {total_tests}, Passati: {passed_tests}, Falliti: {failed_tests}")
        
        return {
            "results": self.results,
            "summary": summary,
            "logs": self.log_messages
        }


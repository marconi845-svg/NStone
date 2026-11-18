"""
Configurazione PLC - Parametri di connessione Ethernet per PLC Siemens S7-1200/S7-1500
Centralizzato e facilmente modificabile
"""

# Configurazione PLC principale
PLC_IP = "192.168.0.10"
PLC_PORT = 102  # Porta standard S7

# Data Block numbers
PLC_DB_LUCIDATRICE = 100
PLC_DB_MULTIFILO = 200

# Timeout (secondi)
PLC_CONNECTION_TIMEOUT = 5.0
PLC_READ_TIMEOUT = 2.0
PLC_RECONNECT_DELAY = 1.0  # Secondi tra tentativi di riconnessione

# Retry settings
PLC_MAX_RETRIES = 3
PLC_RETRY_DELAY = 0.5  # Secondi tra retry

# Monitor settings
PLC_MONITOR_INTERVAL_MS = 100  # Intervallo aggiornamento UI (ms)

# Status thresholds
PLC_LATENCY_WARNING_MS = 50  # Latenza > 50ms = warning
PLC_LATENCY_ERROR_MS = 200  # Latenza > 200ms = errore
PLC_PACKET_TIMEOUT_MS = 5000  # Nessun pacchetto per 5s = timeout

# Fallback settings
PLC_FALLBACK_OFFLINE = True  # Fallback automatico a modalità offline se connessione fallisce
PLC_SHOW_OFFLINE_DATA = True  # Mostra dati offline (ultimi valori) quando disconnesso





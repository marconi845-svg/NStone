@echo off
REM ============================================================
REM Script per avviare il PLC Virtuale Snap7 Lucidatrice/Calibratrice
REM ============================================================
title PLC Virtuale Snap7 - Lucidatrice/Calibratrice

echo.
echo ============================================================
echo   PLC Virtuale Snap7 - Simulazione Lucidatrice/Calibratrice
echo ============================================================
echo.
echo Questo script avvia il server Snap7 che simula un PLC
echo Siemens S7-1200/S7-1500 per testare il Motore Neurale.
echo.
echo Configurazione:
echo   - IP: 127.0.0.1
echo   - Porta: 102
echo   - Rack: 0, Slot: 1
echo.
echo Data Block simulati:
echo   - DB1: Stato macchina (7 byte)
echo   - DB2: Parametri macchina (28 byte = 7 Real)
echo   - DB3: Comandi macchina (3 byte)
echo.
echo ============================================================
echo.

REM Verifica che Python sia disponibile
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Python non trovato!
    echo.
    echo Installa Python 3.8 o superiore e riprova.
    echo.
    pause
    exit /b 1
)

REM Verifica che snap7 sia installato
echo Verifica dipendenze...
python -c "import snap7" >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] python-snap7 non installato!
    echo.
    echo Installa con il comando:
    echo   pip install python-snap7
    echo.
    echo Oppure:
    echo   python -m pip install python-snap7
    echo.
    pause
    exit /b 1
)

REM Verifica che il file server esista
if not exist "snap7_lucidatrice_server.py" (
    echo [ERRORE] File snap7_lucidatrice_server.py non trovato!
    echo.
    echo Assicurati di eseguire lo script dalla root del progetto.
    echo.
    pause
    exit /b 1
)

echo [OK] Dipendenze verificate
echo.
echo ============================================================
echo   Avvio PLC Virtuale Lucidatrice/Calibratrice...
echo ============================================================
echo.
echo Il server Snap7 verra' avviato e rimarra' in esecuzione.
echo.
echo Per fermare il server, premi Ctrl+C in questa finestra.
echo.
echo ============================================================
echo.

REM Avvia il server
python snap7_lucidatrice_server.py

REM Se il server si chiude, mostra messaggio
if errorlevel 1 (
    echo.
    echo ============================================================
    echo   [ERRORE] Il server Snap7 si e' chiuso con un errore
    echo ============================================================
    echo.
    echo Codice di uscita: %errorlevel%
    echo.
    echo Verifica:
    echo   1. Che la porta 102 non sia gia' in uso
    echo   2. Che non ci siano altri server Snap7 in esecuzione
    echo   3. I log sopra per dettagli sull'errore
    echo.
) else (
    echo.
    echo ============================================================
    echo   Server Snap7 chiuso correttamente
    echo ============================================================
    echo.
)

echo.
pause


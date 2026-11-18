@echo off
REM ============================================================
REM Script per avviare il Simulatore CNC Universale
REM ============================================================
title Simulatore CNC Universale

echo.
echo ============================================================
echo   Simulatore CNC Universale
echo ============================================================
echo.
echo Questo script avvia il simulatore CNC che simula una
echo macchina CNC universale per testare il Motore Neurale.
echo.
echo Il simulatore include:
echo   - Stati macchina (READY, RUN, HOLD, ERROR, STOP)
echo   - Posizioni assi (X, Y, Z)
echo   - Spindle (RPM, carico, temperatura)
echo   - Feed (velocità, override)
echo   - Tool (numero, carico)
echo   - G-code simulato
echo   - Allarmi dinamici
echo   - Analisi fanghi e depurazione
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

REM Verifica che il file simulatore esista
if not exist "cnc_simulator.py" (
    echo [ERRORE] File cnc_simulator.py non trovato!
    echo.
    echo Assicurati di eseguire lo script dalla root del progetto.
    echo.
    pause
    exit /b 1
)

echo [OK] Dipendenze verificate
echo.
echo ============================================================
echo   Avvio Simulatore CNC...
echo ============================================================
echo.
echo Il simulatore CNC verra' avviato e rimarra' in esecuzione.
echo Per fermare il simulatore, premi Ctrl+C in questa finestra.
echo.
echo ============================================================
echo.

REM Esegui il simulatore
python cnc_simulator.py

if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERRORE durante l'esecuzione!
    echo ============================================================
    echo.
    echo Verifica che tutte le dipendenze siano installate:
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Simulatore CNC chiuso correttamente
echo ============================================================
pause


@echo off
setlocal

REM ============================================================
REM Script portabile per avviare il PLC Virtuale Snap7 Multifilo
REM Funziona nella cartella della build NSTONELLM_App
REM ============================================================
title PLC Virtuale Snap7 - Multifilo

REM Ottieni il percorso della directory dove si trova questo script
set "SCRIPT_DIR=%~dp0"
REM Rimuovi il trailing backslash se presente
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"
set "SCRIPT_DIR=%CD%"

REM Se siamo in _internal, torna alla directory padre
echo %SCRIPT_DIR% | findstr /C:"\_internal" >nul
if not errorlevel 1 (
    cd /d "%SCRIPT_DIR%\.."
    set "SCRIPT_DIR=%CD%"
)

echo.
echo ============================================================
echo   PLC Virtuale Snap7 - Simulazione Multifilo
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
echo   - DB1: Stato macchina (4 byte)
echo   - DB2: Parametri macchina (16 byte)
echo   - DB3: Comandi macchina (3 byte)
echo.
echo ============================================================
echo.

REM Cerca l'eseguibile Snap7 server nella build (standalone, senza Python necessario)
set "SERVER_EXE="

REM Prima cerca nella directory corrente
if exist "%SCRIPT_DIR%\snap7_multifilo_server.exe" (
    set "SERVER_EXE=%SCRIPT_DIR%\snap7_multifilo_server.exe"
) else (
    REM Se non trovato, cerca nella directory padre (root di NSTONELLM_App)
    set "PARENT_DIR=%SCRIPT_DIR%\.."
    cd /d "%PARENT_DIR%"
    set "PARENT_DIR=%CD%"
    if exist "%PARENT_DIR%\snap7_multifilo_server.exe" (
        set "SERVER_EXE=%PARENT_DIR%\snap7_multifilo_server.exe"
        set "SCRIPT_DIR=%PARENT_DIR%"
    ) else (
        echo [ERRORE] Eseguibile snap7_multifilo_server.exe non trovato!
        echo.
        echo Cercato in:
        echo   - %SCRIPT_DIR%\snap7_multifilo_server.exe
        echo   - %PARENT_DIR%\snap7_multifilo_server.exe
        echo.
        echo Assicurati che la build sia completa e contenga snap7_multifilo_server.exe
        echo.
        pause
        exit /b 1
    )
)

echo Directory script: %SCRIPT_DIR%
echo Eseguibile server: %SERVER_EXE%
echo.
echo NOTA: Questo eseguibile e' standalone e non richiede Python installato!
echo.

echo ============================================================
echo   Avvio PLC Virtuale...
echo ============================================================
echo.
echo Il server Snap7 verra' avviato e rimarra' in esecuzione.
echo.
echo Per fermare il server, premi Ctrl+C in questa finestra.
echo.
echo ============================================================
echo.

REM Avvia il server in una finestra che rimane aperta
echo.
echo ============================================================
echo   Avvio Server Snap7...
echo ============================================================
echo.
start "Snap7 Multifilo Server" cmd /k "cd /d "%SCRIPT_DIR%" && echo ======================================== && echo AVVIO SERVER SNAP7 MULTIFILO && echo ======================================== && echo. && "%SERVER_EXE%" 2>&1 && echo. && echo ======================================== && echo SERVER FERMATO && echo ======================================== && pause"
echo Server avviato in nuova finestra.
echo NOTA: Se il server si chiude immediatamente, controlla la finestra per vedere l'errore.
echo.
echo Premi un tasto per chiudere questa finestra...
pause >nul
exit /b 0

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


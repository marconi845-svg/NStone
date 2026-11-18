@echo off

title NSTONELLM v.0.0.12

color 0A



set "BAT_DIR=%~dp0"

set "BAT_DIR=%BAT_DIR:~0,-1%"

cd /d "%BAT_DIR%"

set PYTHONPATH=%BAT_DIR%



REM Poll Gmail automatico ON (L2). Debug senza IMAP: set NSTONELLM_SKIP_IMAP=1 o legacy\DEBUG_SENZA_IMAP.bat



echo ========================================

echo   NSTONELLM v.0.0.12

echo   Agentic OS for natural stone

echo ========================================

echo.

echo Directory: %CD%

echo.



if not exist "run.py" (

    echo ERRORE: run.py non trovato in questa cartella!

    pause

    exit /b 1

)



python --version >nul 2>&1

if errorlevel 1 (

    echo ERRORE: Python non trovato. Installa Python 3.10+ da python.org

    pause

    exit /b 1

)



echo Python:

python --version

echo.



echo Pulizia processi zombie da sessioni precedenti...

python tools\kill_stale_nstone.py

echo.



echo Verifica dipendenze desktop...

python tools\verify_desktop_deps.py

if errorlevel 1 (

    echo.

    echo Installazione automatica da requirements.txt ...

    python -m pip install --upgrade pip

    python -m pip install -r requirements.txt

    if errorlevel 1 (

        echo ERRORE pip install. Prova manualmente:

        echo   pip install -r requirements.txt

        pause

        exit /b 1

    )

    echo.

    python tools\verify_desktop_deps.py

    if errorlevel 1 (

        echo ERRORE: dipendenze ancora mancanti dopo install.

        pause

        exit /b 1

    )

)



echo.

if "%NSTONELLM_SKIP_IMAP%"=="1" (

    echo Avvio GUI ^(IMAP disabilitato via NSTONELLM_SKIP_IMAP^)...

) else (

    echo Avvio GUI con poll Gmail automatico ^(dopo stabilizzazione GUI^)...

)

echo.

python "%BAT_DIR%\run.py"

set EXIT_CODE=%ERRORLEVEL%



if not "%EXIT_CODE%"=="0" (

    echo.

    echo ERRORE avvio! Codice: %EXIT_CODE%

    echo Vedi logs\nstonellm_crash.log

    pause

    exit /b %EXIT_CODE%

)



echo.

echo Applicazione chiusa.

pause



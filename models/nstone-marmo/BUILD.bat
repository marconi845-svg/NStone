@echo off
setlocal
title NStone Marmo — build modello Ollama
cd /d "%~dp0"

echo ============================================================
echo   NStone Marmo — creazione modello Ollama (fase 0)
echo   Richiede: ollama in PATH + base qwen2.5:14b-instruct-q4_0
echo ============================================================
echo.

where ollama >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] ollama non trovato. Avvia Ollama o aggiungilo al PATH.
    exit /b 1
)

echo [..] Verifica base model...
ollama show qwen2.5:14b-instruct-q4_0 >nul 2>&1
if errorlevel 1 (
    echo [..] Download base Qwen 14B ^(puo' richiedere diversi minuti^)...
    ollama pull qwen2.5:14b-instruct-q4_0
    if errorlevel 1 exit /b 1
)

echo [..] Creazione nstone-marmo:latest ...
ollama create nstone-marmo -f Modelfile
if errorlevel 1 (
    echo [ERRORE] ollama create fallito.
    exit /b 1
)

echo.
echo [OK] Modello pronto: nstone-marmo:latest
echo      In config.json imposta:
echo        "llm": { "ollama": { "model": "nstone-marmo:latest" } }
echo      oppure in Impostazioni seleziona il modello se configurato.
echo.
ollama show nstone-marmo
endlocal
exit /b 0

# Script PowerShell per verificare la portabilità dei file batch
# Esegui questo script nella cartella NSTONELLM_App

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VERIFICA PORTABILITA FILE BATCH" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$errors = 0
$warnings = 0

# Verifica struttura file
Write-Host "1. Verifica struttura file..." -ForegroundColor Yellow
Write-Host ""

$requiredFiles = @(
    @{Path="AVVIA_BACKEND.bat"; Description="File batch backend"},
    @{Path="AVVIA_SIMULAZIONE_MULTIFILO.bat"; Description="File batch simulazione"},
    @{Path="fastapi_backend\main.py"; Description="File main.py backend"},
    @{Path="snap7_multifilo_server.py"; Description="File server Snap7"}
)

foreach ($item in $requiredFiles) {
    if (Test-Path $item.Path) {
        Write-Host "  [OK] $($item.Description): $($item.Path)" -ForegroundColor Green
    } else {
        Write-Host "  [ERRORE] $($item.Description): $($item.Path) NON TROVATO!" -ForegroundColor Red
        $errors++
    }
}

# Verifica che i file batch NON siano in _internal
Write-Host ""
Write-Host "2. Verifica posizione file batch..." -ForegroundColor Yellow
Write-Host ""

if (Test-Path "_internal\AVVIA_BACKEND.bat") {
    Write-Host "  [ATTENZIONE] AVVIA_BACKEND.bat trovato anche in _internal!" -ForegroundColor Yellow
    Write-Host "    I file batch devono essere nella ROOT, non in _internal" -ForegroundColor Yellow
    $warnings++
}

if (Test-Path "_internal\AVVIA_SIMULAZIONE_MULTIFILO.bat") {
    Write-Host "  [ATTENZIONE] AVVIA_SIMULAZIONE_MULTIFILO.bat trovato anche in _internal!" -ForegroundColor Yellow
    Write-Host "    I file batch devono essere nella ROOT, non in _internal" -ForegroundColor Yellow
    $warnings++
}

# Verifica Python
Write-Host ""
Write-Host "3. Verifica Python..." -ForegroundColor Yellow
Write-Host ""

try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Python trovato: $pythonVersion" -ForegroundColor Green
        
        # Verifica versione Python
        $versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
        if ($versionMatch) {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
                Write-Host "  [ATTENZIONE] Versione Python troppo vecchia (richiesto 3.8+)" -ForegroundColor Yellow
                $warnings++
            }
        }
    } else {
        Write-Host "  [ERRORE] Python non trovato nel PATH!" -ForegroundColor Red
        Write-Host "    Installa Python da python.org e aggiungilo al PATH" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host "  [ERRORE] Python non trovato!" -ForegroundColor Red
    Write-Host "    Installa Python da python.org e aggiungilo al PATH" -ForegroundColor Red
    $errors++
}

# Verifica dipendenze Python
Write-Host ""
Write-Host "4. Verifica dipendenze Python..." -ForegroundColor Yellow
Write-Host ""

$modules = @(
    @{Name="uvicorn"; Required="AVVIA_BACKEND.bat"},
    @{Name="fastapi"; Required="AVVIA_BACKEND.bat"},
    @{Name="snap7"; Required="AVVIA_SIMULAZIONE_MULTIFILO.bat"}
)

foreach ($module in $modules) {
    python -c "import $($module.Name)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] $($module.Name) installato (richiesto da $($module.Required))" -ForegroundColor Green
    } else {
        Write-Host "  [MANCANTE] $($module.Name) - installa con: pip install $($module.Name)" -ForegroundColor Yellow
        Write-Host "    Richiesto da: $($module.Required)" -ForegroundColor Yellow
        $warnings++
    }
}

# Verifica ngrok (opzionale)
Write-Host ""
Write-Host "5. Verifica ngrok (opzionale)..." -ForegroundColor Yellow
Write-Host ""

try {
    $ngrokVersion = ngrok version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] ngrok trovato" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] ngrok non trovato (opzionale per AVVIA_BACKEND.bat)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [INFO] ngrok non trovato (opzionale per AVVIA_BACKEND.bat)" -ForegroundColor Gray
}

# Verifica porte disponibili
Write-Host ""
Write-Host "6. Verifica porte disponibili..." -ForegroundColor Yellow
Write-Host ""

# Porta 8000 (FastAPI)
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($port8000) {
    Write-Host "  [ATTENZIONE] Porta 8000 già in uso (FastAPI)" -ForegroundColor Yellow
    $warnings++
} else {
    Write-Host "  [OK] Porta 8000 disponibile (FastAPI)" -ForegroundColor Green
}

# Porta 102 (Snap7)
$port102 = Get-NetTCPConnection -LocalPort 102 -ErrorAction SilentlyContinue
if ($port102) {
    Write-Host "  [ATTENZIONE] Porta 102 già in uso (Snap7)" -ForegroundColor Yellow
    $warnings++
} else {
    Write-Host "  [OK] Porta 102 disponibile (Snap7)" -ForegroundColor Green
}

# Riepilogo
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "RIEPILOGO" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($errors -eq 0 -and $warnings -eq 0) {
    Write-Host "  [SUCCESSO] Tutti i controlli superati!" -ForegroundColor Green
    Write-Host "  I file batch dovrebbero funzionare correttamente su questa macchina." -ForegroundColor Green
    exit 0
} elseif ($errors -eq 0) {
    Write-Host "  [ATTENZIONE] $warnings avviso/i trovati" -ForegroundColor Yellow
    Write-Host "  I file batch potrebbero funzionare, ma verifica gli avvisi sopra." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "  [ERRORE] $errors errore/i trovati" -ForegroundColor Red
    Write-Host "  Risolvi gli errori prima di distribuire la build." -ForegroundColor Red
    exit 1
}






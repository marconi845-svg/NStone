# NStone — FreeSWITCH Windows installer + Agentic Calling config deploy
# Run as Administrator:  powershell -ExecutionPolicy Bypass -File tools\install_freeswitch_windows.ps1

param(
    [string]$InstallDir = "C:\Program Files\FreeSWITCH",
    [string]$MsiUrl = "https://files.freeswitch.org/windows/installer/x64/FreeSWITCH-1.10.12-Release-x64.msi",
    [switch]$SkipMsi,
    [switch]$SkipSounds
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$CacheDir = Join-Path $ProjectRoot "tools\cache"
$MsiPath = Join-Path $CacheDir "FreeSWITCH-1.10.12-Release-x64.msi"
$IntegrationRoot = Join-Path $ProjectRoot "integrations\freeswitch"
$RecordingsDir = "C:\freeswitch\recordings\agentic"

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-FreeSwitchRoot {
    $candidates = @(
        $InstallDir,
        "C:\Program Files\FreeSWITCH",
        "C:\Program Files (x86)\FreeSWITCH"
    )
    foreach ($c in $candidates) {
        $fsCli = Join-Path $c "fs_cli.exe"
        $fsExe = Join-Path $c "FreeSwitchConsole.exe"
        if (Test-Path $fsCli) { return $c }
        if (Test-Path $fsExe) { return $c }
    }
    return $null
}

function Update-NStoneConfig {
    param([string]$FsRoot)
    $configPath = Join-Path $ProjectRoot "config.json"
    $fsCli = Join-Path $FsRoot "fs_cli.exe"
    $sipHost = "127.0.0.1"
    try {
        $sipHost = (Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
            Select-Object -First 1).IPAddress
    } catch { }

    $agentic = @{
        enabled = $true
        mode = "lan"
        sip_server = $sipHost
        sip_port = 5060
        freeswitch_path = $fsCli
        voice_bridge_host = "127.0.0.1"
        voice_bridge_port = 8765
        voice_bridge_auto_start = $true
        recordings_dir = $RecordingsDir
    }

    if (Test-Path $configPath) {
        $raw = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -eq $raw.agentic_calling) {
            $raw | Add-Member -NotePropertyName agentic_calling -NotePropertyValue ([pscustomobject]@{})
        }
        foreach ($key in $agentic.Keys) {
            $raw.agentic_calling.$key = $agentic[$key]
        }
        $raw | ConvertTo-Json -Depth 20 | Set-Content $configPath -Encoding UTF8
        Write-Host "Updated config.json (agentic_calling.sip_server = $sipHost)"
    } else {
        Write-Host "config.json not found - copy config.json.example and re-run deploy section"
    }
}

function Deploy-NStoneFreeSwitchConfig {
    param([string]$FsRoot)
    $conf = Join-Path $FsRoot "conf"
    if (-not (Test-Path $conf)) {
        throw "FreeSWITCH conf not found under $FsRoot"
    }

    New-Item -ItemType Directory -Force -Path $RecordingsDir | Out-Null

    Copy-Item (Join-Path $IntegrationRoot "dialplan\01_agentic.xml") `
        (Join-Path $conf "dialplan\default\01_agentic.xml") -Force

    $scriptsDir = Join-Path $conf "scripts"
    New-Item -ItemType Directory -Force -Path $scriptsDir | Out-Null
    Copy-Item (Join-Path $IntegrationRoot "scripts\agentic_call.lua") `
        (Join-Path $scriptsDir "agentic_call.lua") -Force

    Copy-Item (Join-Path $IntegrationRoot "directory\2001.xml") `
        (Join-Path $conf "directory\default\2001.xml") -Force

    Write-Host "Deployed dialplan, Lua script, SIP user 2001"
}

if (-not $SkipMsi) {
    if (-not (Test-Admin)) {
        Write-Host "ERROR: Run PowerShell as Administrator for MSI install."
        Write-Host "  Right-click -> Install FreeSWITCH (see legacy\INSTALLA_FREESWITCH.bat)"
        exit 1
    }

    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    if (-not (Test-Path $MsiPath)) {
        Write-Host "Downloading FreeSWITCH 1.10.12 MSI (~126 MB)..."
        Invoke-WebRequest -Uri $MsiUrl -OutFile $MsiPath -UseBasicParsing
    }

    $existing = Find-FreeSwitchRoot
    if (-not $existing) {
        Write-Host "Installing FreeSWITCH MSI (silent)..."
        $proc = Start-Process msiexec.exe -ArgumentList "/i `"$MsiPath`" /quiet /norestart" -Wait -PassThru
        if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) {
            Write-Host "msiexec exit code: $($proc.ExitCode) - try manual install: $MsiPath"
        }
        Start-Sleep -Seconds 3
    } else {
        Write-Host "FreeSWITCH already present at $existing"
    }
}

$FsRoot = Find-FreeSwitchRoot
if (-not $FsRoot) {
    Write-Host "FreeSWITCH not found after install. Install manually then run:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File tools\install_freeswitch_windows.ps1 -SkipMsi"
    exit 1
}

Write-Host "FreeSWITCH root: $FsRoot"
Deploy-NStoneFreeSwitchConfig -FsRoot $FsRoot
Update-NStoneConfig -FsRoot $FsRoot

Write-Host ""
Write-Host "=== Done ==="
Write-Host "1. Start service:  net start FreeSWITCH (or Services.msc -> FreeSWITCH)"
Write-Host "2. Open NStone -> Agentic Calling (Voice Bridge)"
Write-Host "3. Zoiper: user 2001 / password CHANGE_ME_SIP_PASSWORD / server = LAN IP / port 5060"
Write-Host "4. Dial 2000 (Commercial), 1000 (Management), 3000 (Production)"
Write-Host "5. Reload dialplan if FS was already running: fs_cli -x reloadxml"

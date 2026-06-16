# ============================================================================
# Launch.ps1 -- oneDiversified World Cup Colour sACN
#
# Single launcher that:
#   1. Self-elevates to Administrator (needed for firewall rules)
#   2. Ensures firewall rules are in place (idempotent)
#   3. Launches main.py in a watchdog loop that always relaunches (show mode);
#      stop it with Ctrl+C in the watchdog window
#
# Double-click Launch.bat to run, or right-click this file > Run with PowerShell.
# ============================================================================

# ── Self-elevate if not running as Administrator ─────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    $scriptPath = $MyInvocation.MyCommand.Definition
    Start-Process powershell.exe -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    exit
}

# ── Resolve paths ────────────────────────────────────────────────────────────
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $AppDir
$ConfigPath = Join-Path $AppDir "config.ini"

# ── Configuration ────────────────────────────────────────────────────────────
$RulePrefix       = "WorldCupColour"
$SacnPort         = 5568
$WebPort          = 8080
$HttpsPort        = 443
$RestartDelaySec  = 2        # seconds to wait before restarting after a crash
$MouseWiggleSec   = 60       # wiggle mouse every N seconds to prevent screen lock

# ── Resolve Python interpreter ─────────────────────────────────────────────────
# Prefer the full path recorded in config.ini [dependencies] python_path. Falling
# back to bare "python" is risky on Windows: it often resolves to the Microsoft
# Store stub, which exits 0 immediately and makes the watchdog think the app
# closed cleanly (so it never relaunches).
function Get-PythonExe {
    if (Test-Path $ConfigPath) {
        $content = Get-Content $ConfigPath -Raw
        if ($content -match '(?m)^\s*python_path\s*=\s*(.+?)\s*$') {
            $p = $matches[1].Trim()
            if ($p -and (Test-Path $p)) {
                return $p
            }
        }
    }
    return "python"
}

$PythonExe = Get-PythonExe

# ── Firewall Rules ───────────────────────────────────────────────────────────
$Rules = @(
    @{
        Name      = "$RulePrefix - sACN E1.31 (UDP $SacnPort Out)"
        Direction = "Outbound"; Protocol = "UDP"; Port = $SacnPort
        Description = "Outbound sACN/E1.31 multicast + unicast DMX"
    },
    @{
        Name      = "$RulePrefix - sACN E1.31 (UDP $SacnPort In)"
        Direction = "Inbound"; Protocol = "UDP"; Port = $SacnPort
        Description = "Inbound sACN/E1.31 responses"
    },
    @{
        Name      = "$RulePrefix - Web Server (TCP $WebPort In)"
        Direction = "Inbound"; Protocol = "TCP"; Port = $WebPort
        Description = "Inbound HTTP for live status web server"
    },
    @{
        Name      = "$RulePrefix - SportMonks API (TCP $HttpsPort Out)"
        Direction = "Outbound"; Protocol = "TCP"; Port = $HttpsPort
        Description = "Outbound HTTPS for SportMonks livescore API"
    }
)

# ICMPv4 rule name (separate from port-based rules)
$IcmpRuleName = "$RulePrefix - Allow Ping (ICMPv4-In)"

function Ensure-NetworkPrivate {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " Network Profile" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # Find all connected Wi-Fi adapters (and Ethernet as fallback)
    $profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue
    if (-not $profiles) {
        Write-Host "  No active network connections found." -ForegroundColor Yellow
        return
    }

    foreach ($p in $profiles) {
        $alias    = $p.InterfaceAlias
        $category = $p.NetworkCategory
        $name     = $p.Name

        if ($category -eq "Private") {
            Write-Host "  OK (Private): $alias  [$name]" -ForegroundColor DarkGray
        } else {
            Write-Host "  Switching to Private: $alias  [$name]  (was $category)" -ForegroundColor Yellow
            Set-NetConnectionProfile -InterfaceIndex $p.InterfaceIndex -NetworkCategory Private
            Write-Host "    Done." -ForegroundColor Green
        }
    }
    Write-Host ""
}

function Ensure-FirewallRules {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " Firewall Rules" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # ── Port-based rules ─────────────────────────────────────────────────
    foreach ($r in $Rules) {
        $existing = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "  OK (exists): $($r.Name)" -ForegroundColor DarkGray
            continue
        }

        $params = @{
            DisplayName = $r.Name
            Direction   = $r.Direction
            Protocol    = $r.Protocol
            Action      = "Allow"
            Enabled     = "True"
            Profile     = "Any"
            Description = $r.Description
        }
        if ($r.Direction -eq "Inbound") {
            $params["LocalPort"]  = [string]$r.Port
        } else {
            $params["RemotePort"] = [string]$r.Port
        }

        New-NetFirewallRule @params | Out-Null
        Write-Host "  CREATED: $($r.Name)" -ForegroundColor Green
    }

    # ── ICMPv4 ping rule ─────────────────────────────────────────────────
    $icmpExists = Get-NetFirewallRule -DisplayName $IcmpRuleName -ErrorAction SilentlyContinue
    if ($icmpExists) {
        Write-Host "  OK (exists): $IcmpRuleName" -ForegroundColor DarkGray
    } else {
        New-NetFirewallRule `
            -DisplayName $IcmpRuleName `
            -Direction   Inbound `
            -Protocol    ICMPv4 `
            -IcmpType    8 `
            -Action      Allow `
            -Enabled     True `
            -Profile     Any `
            -Description "Allow inbound ping (echo request) from other machines on the network" `
            | Out-Null
        Write-Host "  CREATED: $IcmpRuleName" -ForegroundColor Green
    }

    # ── Enable built-in Network Discovery rules (file sharing, mDNS, etc.) ──
    Write-Host ""
    Write-Host "  Enabling Network Discovery ..." -ForegroundColor Cyan
    Get-NetFirewallRule -DisplayGroup "Network Discovery" -ErrorAction SilentlyContinue |
        Where-Object { $_.Enabled -eq "False" } |
        ForEach-Object {
            Enable-NetFirewallRule -Name $_.Name
            Write-Host "    Enabled: $($_.DisplayName)" -ForegroundColor Green
        }

    Write-Host ""
}

# ── Mouse Wiggle (keep-alive) ──────────────────────────────────────────────
$WiggleJob = $null

function Start-MouseWiggle {
    $script:WiggleJob = Start-Job -ArgumentList $MouseWiggleSec -ScriptBlock {
        param($intervalSec)
        Add-Type -AssemblyName System.Windows.Forms
        while ($true) {
            Start-Sleep -Seconds $intervalSec
            $pos = [System.Windows.Forms.Cursor]::Position
            [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(($pos.X + 1), $pos.Y)
            Start-Sleep -Milliseconds 50
            [System.Windows.Forms.Cursor]::Position = $pos
        }
    }
    Write-Host "  Mouse wiggle: every ${MouseWiggleSec}s (screen-lock prevention)" -ForegroundColor White
}

function Stop-MouseWiggle {
    if ($script:WiggleJob) {
        Stop-Job   $script:WiggleJob -ErrorAction SilentlyContinue
        Remove-Job $script:WiggleJob -ErrorAction SilentlyContinue
        $script:WiggleJob = $null
    }
}

# ── Watchdog Loop ────────────────────────────────────────────────────────────
function Start-Watchdog {
    $crashCount = 0

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " World Cup Colour - Watchdog" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  App dir : $AppDir" -ForegroundColor White
    Write-Host "  Python  : $PythonExe" -ForegroundColor White
    Write-Host "  Restart : always (show mode) -- ${RestartDelaySec}s after exit" -ForegroundColor White
    Write-Host ""
    Write-Host "  Press Ctrl+C in this window to stop the watchdog." -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "[$timestamp] Starting main.py ..." -ForegroundColor Green

        # Call the interpreter directly and block until it exits. This is more
        # reliable than Start-Process -PassThru, whose .ExitCode is frequently
        # unpopulated; $LASTEXITCODE always reflects the real process exit code.
        & $PythonExe "main.py"
        $exitCode = $LASTEXITCODE
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        # Show mode: always relaunch, whether the app closed cleanly or crashed.
        # To stop the app for good, press Ctrl+C in this window.
        if ($exitCode -eq 0) {
            Write-Host "[$timestamp] Application exited (code 0)." -ForegroundColor Cyan
        } else {
            $crashCount++
            Write-Host ""
            Write-Host "[$timestamp] CRASH #$crashCount  (exit code $exitCode)" -ForegroundColor Red
        }
        Write-Host "  Relaunching in $RestartDelaySec seconds ... (Ctrl+C to stop)" -ForegroundColor Yellow
        Start-Sleep -Seconds $RestartDelaySec
    }
}

# ── Dependency Check ──────────────────────────────────────────────────────────
function Ensure-Dependencies {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " Dependency Check" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    $configPath = Join-Path $AppDir "config.ini"
    $needsInstall = $true

    if (Test-Path $configPath) {
        $content = Get-Content $configPath -Raw
        if ($content -match '(?m)^\[dependencies\]') {
            if ($content -match '(?m)^status\s*=\s*installed') {
                Write-Host "  Dependencies: OK (already installed)" -ForegroundColor DarkGray
                $needsInstall = $false
            } else {
                Write-Host "  Dependencies: previous install incomplete or failed" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  Dependencies: not yet installed" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Dependencies: config.ini not found, running installer" -ForegroundColor Yellow
    }

    if ($needsInstall) {
        $installScript = Join-Path $AppDir "Install.ps1"
        if (Test-Path $installScript) {
            Write-Host "  Running Install.ps1 ..." -ForegroundColor Cyan
            & $installScript
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  Install.ps1 failed. Cannot continue." -ForegroundColor Red
                return $false
            }
        } else {
            Write-Host "  ERROR: Install.ps1 not found at $installScript" -ForegroundColor Red
            return $false
        }
    }

    return $true
}

# ── Network Setup Flag (config.ini [network]) ──────────────────────────────────
# Mirrors the [dependencies] flag: once the network profile, firewall rules, and
# Network Discovery are configured, record it in config.ini so subsequent launches
# skip the (admin-only, slow) setup. Delete the [network] section to force a re-run.
function Test-NetworkConfigured {
    if (-not (Test-Path $ConfigPath)) { return $false }
    $content = Get-Content $ConfigPath -Raw
    if ($content -match '(?m)^\[network\]' -and $content -match '(?m)^status\s*=\s*configured') {
        return $true
    }
    return $false
}

function Set-NetworkConfigured {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    $lines = @()
    if (Test-Path $ConfigPath) {
        $lines = Get-Content $ConfigPath
    }

    # Remove any existing [network] section (idempotent rewrite)
    $newLines = @()
    $inSection = $false
    foreach ($line in $lines) {
        if ($line -match '^\[network\]') {
            $inSection = $true
            continue
        }
        if ($inSection -and $line -match '^\[') {
            $inSection = $false
        }
        if (-not $inSection) {
            $newLines += $line
        }
    }

    # Strip trailing blank lines
    while ($newLines.Count -gt 0 -and $newLines[-1].Trim() -eq "") {
        $newLines = $newLines[0..($newLines.Count - 2)]
    }

    # Append [network] section
    $newLines += ""
    $newLines += "[network]"
    $newLines += "status = configured"
    $newLines += "profile = Private"
    $newLines += "firewall_rules = installed"
    $newLines += "network_discovery = enabled"
    $newLines += "configured_on = $timestamp"
    $newLines += ""

    $newLines | Set-Content $ConfigPath -Encoding UTF8
}

# ── Main ─────────────────────────────────────────────────────────────────────
try {
    if (Test-NetworkConfigured) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host " Network Setup" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  OK (already configured) -- skipping profile/firewall/discovery setup" -ForegroundColor DarkGray
        Write-Host "  (delete the [network] section in config.ini to force a re-run)" -ForegroundColor DarkGray
        Write-Host ""
    } else {
        Ensure-NetworkPrivate
        Ensure-FirewallRules
        Set-NetworkConfigured
        Write-Host "  config.ini updated: [network] status = configured" -ForegroundColor Green
        Write-Host ""
    }

    $depsOk = Ensure-Dependencies
    if (-not $depsOk) {
        Write-Host ""
        Write-Host "Cannot start -- dependencies not satisfied." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }

    Start-MouseWiggle
    Start-Watchdog
} catch {
    Write-Host ""
    Write-Host "FATAL: $_" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
} finally {
    Stop-MouseWiggle
}

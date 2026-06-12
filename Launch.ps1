# ============================================================================
# Launch.ps1 -- oneDiversified World Cup Colour sACN
#
# Single launcher that:
#   1. Self-elevates to Administrator (needed for firewall rules)
#   2. Ensures firewall rules are in place (idempotent)
#   3. Launches main.py in a watchdog loop that auto-restarts on crash
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

# ── Configuration ────────────────────────────────────────────────────────────
$RulePrefix       = "WorldCupColour"
$SacnPort         = 5568
$WebPort          = 8080
$HttpsPort        = 443
$RestartDelaySec  = 5        # seconds to wait before restarting after a crash
$PythonExe        = "python" # change to full path if needed, e.g. "C:\Python312\python.exe"
$MouseWiggleSec   = 60       # wiggle mouse every N seconds to prevent screen lock

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
    Write-Host "  Restart : ${RestartDelaySec}s after crash" -ForegroundColor White
    Write-Host ""
    Write-Host "  Press Ctrl+C in this window to stop." -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "[$timestamp] Starting main.py ..." -ForegroundColor Green

        $proc = Start-Process -FilePath $PythonExe -ArgumentList "main.py" `
            -WorkingDirectory $AppDir -PassThru -NoNewWindow

        $proc.WaitForExit()
        $exitCode = $proc.ExitCode
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        if ($exitCode -eq 0) {
            Write-Host "[$timestamp] Application exited cleanly (code 0)." -ForegroundColor Cyan
            Write-Host "  Clean exit -- not restarting." -ForegroundColor Cyan
            break
        }

        $crashCount++
        Write-Host ""
        Write-Host "[$timestamp] CRASH #$crashCount  (exit code $exitCode)" -ForegroundColor Red
        Write-Host "  Restarting in $RestartDelaySec seconds ..." -ForegroundColor Yellow
        Start-Sleep -Seconds $RestartDelaySec
    }
}

# ── Main ─────────────────────────────────────────────────────────────────────
try {
    Ensure-NetworkPrivate
    Ensure-FirewallRules
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

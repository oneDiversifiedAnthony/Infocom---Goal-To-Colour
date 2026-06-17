# ============================================================================
# Setup-Firewall.ps1 -- oneDiversified World Cup Colour sACN
#
# Standalone firewall setup. Same rules as Launch.ps1 but without the watchdog.
# Run once with elevated privileges, or just use Launch.bat which does both.
# ============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

$RulePrefix = "WorldCupColour"
$SacnPort   = 5568
$WebPort    = 8080
$HttpsPort  = 443

$Rules = @(
    @{ Name = "$RulePrefix - sACN E1.31 (UDP $SacnPort Out)";       Direction = "Outbound"; Protocol = "UDP"; Port = $SacnPort;  Description = "Outbound sACN/E1.31 multicast + unicast DMX" },
    @{ Name = "$RulePrefix - sACN E1.31 (UDP $SacnPort In)";        Direction = "Inbound";  Protocol = "UDP"; Port = $SacnPort;  Description = "Inbound sACN/E1.31 responses" },
    @{ Name = "$RulePrefix - Web Server (TCP $WebPort In)";          Direction = "Inbound";  Protocol = "TCP"; Port = $WebPort;   Description = "Inbound HTTP for live status web server" },
    @{ Name = "$RulePrefix - SportMonks API (TCP $HttpsPort Out)";   Direction = "Outbound"; Protocol = "TCP"; Port = $HttpsPort; Description = "Outbound HTTPS for SportMonks livescore API" }
)

$IcmpRuleName = "$RulePrefix - Allow Ping (ICMPv4-In)"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " World Cup Colour - Firewall Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Port-based rules
foreach ($r in $Rules) {
    $existing = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Remove-NetFirewallRule -DisplayName $r.Name
        Write-Host "  Removed old rule: $($r.Name)" -ForegroundColor Yellow
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
    Write-Host "  Created rule: $($r.Name)" -ForegroundColor Green
}

# ICMPv4 ping
$icmpExists = Get-NetFirewallRule -DisplayName $IcmpRuleName -ErrorAction SilentlyContinue
if ($icmpExists) { Remove-NetFirewallRule -DisplayName $IcmpRuleName }
New-NetFirewallRule `
    -DisplayName $IcmpRuleName `
    -Direction   Inbound `
    -Protocol    ICMPv4 `
    -IcmpType    8 `
    -Action      Allow `
    -Enabled     True `
    -Profile     Any `
    -Description "Allow inbound ping (echo request) from the network" `
    | Out-Null
Write-Host "  Created rule: $IcmpRuleName" -ForegroundColor Green

# Network Discovery
Write-Host ""
Write-Host "  Enabling Network Discovery ..." -ForegroundColor Cyan
Get-NetFirewallRule -DisplayGroup "Network Discovery" -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq "False" } |
    ForEach-Object {
        Enable-NetFirewallRule -Name $_.Name
        Write-Host "    Enabled: $($_.DisplayName)" -ForegroundColor Green
    }

Write-Host ""
Write-Host "All firewall rules applied." -ForegroundColor Green
Write-Host ""
Write-Host "  Ping (ICMP)   :  ICMPv4 echo (in)" -ForegroundColor White
Write-Host "  sACN / E1.31  :  UDP $SacnPort  (in + out)" -ForegroundColor White
Write-Host "  Web Server    :  TCP $WebPort  (in)" -ForegroundColor White
Write-Host "  SportMonks    :  TCP $HttpsPort  (out)" -ForegroundColor White
Write-Host "  Network Discovery: enabled" -ForegroundColor White
Write-Host ""

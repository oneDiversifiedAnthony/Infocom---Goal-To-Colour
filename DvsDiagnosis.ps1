$ErrorActionPreference = 'SilentlyContinue'

# Restart Bonjour and give it time to re-register
Write-Host "Restarting Bonjour Service..."
Restart-Service "Bonjour Service" -Force
Write-Host "Clearing DNS client cache..."
Clear-DnsClientCache
Write-Host "Waiting 10 seconds for Bonjour to re-register..."
Start-Sleep -Seconds 10
Write-Host "Done waiting. Running diagnostics..."

Get-NetAdapter | Sort-Object ifIndex | ForEach-Object {
    $ip = Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
    $gw = (Get-NetIPConfiguration -InterfaceIndex $_.ifIndex 2>$null).IPv4DefaultGateway.NextHop
    [PSCustomObject]@{
        Name      = $_.Name
        ifIndex   = $_.ifIndex
        Status    = $_.Status
        Speed     = $_.LinkSpeed
        IP        = ($ip.IPAddress -join ', ')
        Prefix    = ($ip.PrefixLength -join ', ')
        Metric    = (Get-NetIPInterface -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).InterfaceMetric -join ', '
        Gateway   = $gw
    }
} | Format-Table -AutoSize

Get-NetIPInterface -AddressFamily IPv4 | Sort-Object InterfaceMetric | Format-Table ifIndex, InterfaceAlias, InterfaceMetric, Dhcp, ConnectionState -AutoSize

# Route lookup for each IPv4 address found on this machine
$foundIPs = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -ExpandProperty IPAddress -Unique

foreach ($addr in $foundIPs) {
    Write-Host "Route to $addr"
    Find-NetRoute -RemoteIPAddress $addr |
        Select-Object IPAddress, InterfaceAlias, NextHop |
        Format-Table -AutoSize
}

# DNS resolution for this machine's .local name
$hostName = $env:COMPUTERNAME
Write-Host "Resolving $hostName.local"
Resolve-DnsName -Name "$hostName.local" -Type A -ErrorAction SilentlyContinue

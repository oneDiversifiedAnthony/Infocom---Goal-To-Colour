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

# Ping sweep of each connected subnet
$sweepIPs = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' -and $_.PrefixLength -ge 16 }

foreach ($iface in $sweepIPs) {
    $ip = [System.Net.IPAddress]::Parse($iface.IPAddress)
    $prefix = $iface.PrefixLength
    $ipBytes = $ip.GetAddressBytes()
    [Array]::Reverse($ipBytes)
    $ipInt = [BitConverter]::ToUInt32($ipBytes, 0)
    $maskInt = [uint32](([math]::Pow(2, $prefix) - 1) * [math]::Pow(2, 32 - $prefix))
    $networkInt = $ipInt -band $maskInt
    $broadcastInt = $networkInt -bor (-bnot $maskInt -band 0xFFFFFFFF)
    $hostCount = $broadcastInt - $networkInt - 1

    if ($hostCount -lt 1 -or $hostCount -gt 1024) {
        Write-Host ("`nSkipping " + $iface.IPAddress + "/$prefix - $hostCount hosts (too large or empty)") -ForegroundColor DarkGray
        continue
    }

    Write-Host ("`n--- Ping sweep: " + $iface.IPAddress + "/$prefix - $hostCount hosts ---") -ForegroundColor Cyan

    $pool = [RunspaceFactory]::CreateRunspacePool(1, 64)
    $pool.Open()
    $runners = @()

    for ($i = 1; $i -le $hostCount; $i++) {
        $targetInt = $networkInt + $i
        $tBytes = [BitConverter]::GetBytes([uint32]$targetInt)
        [Array]::Reverse($tBytes)
        $targetIP = ([System.Net.IPAddress]::new($tBytes)).ToString()

        $ps = [PowerShell]::Create().AddScript({
            param($tip)
            $ping = New-Object System.Net.NetworkInformation.Ping
            try {
                $reply = $ping.Send($tip, 1000)
                if ($reply.Status -eq 'Success') {
                    [PSCustomObject]@{ IP = $tip; RTT = $reply.RoundtripTime }
                }
            } catch {}
            finally { $ping.Dispose() }
        }).AddArgument($targetIP)
        $ps.RunspacePool = $pool
        $runners += [PSCustomObject]@{ Pipe = $ps; Handle = $ps.BeginInvoke() }
    }

    $results = @()
    foreach ($r in $runners) {
        $out = $r.Pipe.EndInvoke($r.Handle)
        if ($out) { $results += $out }
        $r.Pipe.Dispose()
    }
    $pool.Close()
    $pool.Dispose()

    if ($results.Count -gt 0) {
        # Parallel DNS reverse lookups
        $dnsPool = [RunspaceFactory]::CreateRunspacePool(1, 32)
        $dnsPool.Open()
        $dnsRunners = @()
        foreach ($res in $results) {
            $ps = [PowerShell]::Create().AddScript({
                param($tip, $rtt)
                $dns = try { [System.Net.Dns]::GetHostEntry($tip).HostName } catch { '-' }
                [PSCustomObject]@{ IP = $tip; Hostname = $dns; RTT_ms = $rtt }
            }).AddArgument($res.IP).AddArgument($res.RTT)
            $ps.RunspacePool = $dnsPool
            $dnsRunners += [PSCustomObject]@{ Pipe = $ps; Handle = $ps.BeginInvoke() }
        }
        $resolved = @()
        foreach ($dr in $dnsRunners) {
            $out = $dr.Pipe.EndInvoke($dr.Handle)
            if ($out) { $resolved += $out }
            $dr.Pipe.Dispose()
        }
        $dnsPool.Close()
        $dnsPool.Dispose()

        $resolved | Sort-Object { ($_.IP -split '\.') | ForEach-Object { [int]$_ } } | Format-Table -AutoSize
    } else {
        Write-Host "No hosts responded." -ForegroundColor Yellow
    }
}

# ARP table (populated by ping sweep above)
Write-Host "`n--- ARP Table (devices seen on local network) ---" -ForegroundColor Cyan
Get-NetNeighbor -AddressFamily IPv4 |
    Where-Object { $_.State -ne 'Unreachable' -and $_.IPAddress -notlike '224.*' -and $_.IPAddress -notlike '255.*' -and $_.IPAddress -notlike '239.*' } |
    Select-Object IPAddress, LinkLayerAddress, State, @{N='Interface';E={(Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue).Name}} |
    Sort-Object { ($_.IPAddress -split '\.') | ForEach-Object { [int]$_ } } |
    Format-Table -AutoSize

# Bonjour / mDNS service discovery via multicast DNS queries
$bonjourServices = @(
    '_http._tcp.local'
    '_https._tcp.local'
    '_ssh._tcp.local'
    '_smb._tcp.local'
    '_printer._tcp.local'
    '_ipp._tcp.local'
    '_airplay._tcp.local'
    '_raop._tcp.local'
    '_googlecast._tcp.local'
    '_companion-link._tcp.local'
    '_workstation._tcp.local'
    '_rfb._tcp.local'
    '_sacn._udp.local'
    '_artnet._udp.local'
)

Write-Host "`n--- Bonjour / mDNS Service Discovery ---" -ForegroundColor Cyan

# Use raw mDNS multicast query via UDP
$mdnsResults = @()
$mdnsEndpoint = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Parse('224.0.0.251'), 5353)

foreach ($svc in $bonjourServices) {
    try {
        # Build mDNS PTR query packet
        $labels = $svc -split '\.'
        $queryBytes = [System.Collections.Generic.List[byte]]::new()
        # Transaction ID
        $queryBytes.AddRange([byte[]](0x00, 0x00))
        # Flags (standard query)
        $queryBytes.AddRange([byte[]](0x00, 0x00))
        # Questions: 1
        $queryBytes.AddRange([byte[]](0x00, 0x01))
        # Answer/Authority/Additional: 0
        $queryBytes.AddRange([byte[]](0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        # QNAME
        foreach ($label in $labels) {
            $queryBytes.Add([byte]$label.Length)
            $queryBytes.AddRange([System.Text.Encoding]::ASCII.GetBytes($label))
        }
        $queryBytes.Add(0x00)
        # QTYPE PTR (12) and QCLASS IN (1)
        $queryBytes.AddRange([byte[]](0x00, 0x0C, 0x00, 0x01))

        $udp = [System.Net.Sockets.UdpClient]::new()
        $udp.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::Socket,
            [System.Net.Sockets.SocketOptionName]::ReuseAddress, $true)
        $udp.Client.Bind([System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0))
        $udp.JoinMulticastGroup([System.Net.IPAddress]::Parse('224.0.0.251'))
        $udp.Client.ReceiveTimeout = 2000
        $udp.Send($queryBytes.ToArray(), $queryBytes.Count, $mdnsEndpoint) | Out-Null

        # Collect responses for 2 seconds
        $deadline = [DateTime]::Now.AddSeconds(2)
        while ([DateTime]::Now -lt $deadline) {
            try {
                $remoteEP = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
                $response = $udp.Receive([ref]$remoteEP)
                if ($response.Length -gt 12) {
                    # Parse answer names from the response
                    $answerCount = ([int]$response[6] -shl 8) + [int]$response[7]
                    if ($answerCount -gt 0) {
                        # Extract readable strings from the packet
                        $text = [System.Text.Encoding]::ASCII.GetString($response)
                        # Find instance names by looking for printable runs
                        $names = @()
                        $pos = 12
                        while ($pos -lt $response.Length - 2) {
                            $len = [int]$response[$pos]
                            if ($len -gt 1 -and $len -lt 64 -and ($pos + $len) -lt $response.Length) {
                                $segment = [System.Text.Encoding]::UTF8.GetString($response, $pos + 1, $len)
                                if ($segment -match '^[a-zA-Z0-9 _\-\.]+$' -and $segment.Length -gt 2) {
                                    $names += $segment
                                }
                            }
                            $pos++
                        }
                        if ($names.Count -gt 0) {
                            $instanceName = ($names | Where-Object { $_ -notmatch '^_' -and $_ -ne 'local' -and $_ -ne 'tcp' -and $_ -ne 'udp' } | Select-Object -First 1)
                            if ($instanceName) {
                                $mdnsResults += [PSCustomObject]@{
                                    Service  = $svc -replace '\.local$',''
                                    Instance = $instanceName
                                    From     = $remoteEP.Address.ToString()
                                }
                            }
                        }
                    }
                }
            } catch [System.Net.Sockets.SocketException] { break }
        }
        $udp.Close()
    } catch {}
}

if ($mdnsResults.Count -gt 0) {
    $mdnsResults | Sort-Object Service, Instance -Unique | Format-Table -AutoSize
} else {
    Write-Host "No Bonjour services discovered." -ForegroundColor Yellow
}

# DNS resolution for this machine's .local name
$hostName = $env:COMPUTERNAME
Write-Host "Resolving $hostName.local"
Resolve-DnsName -Name "$hostName.local" -Type A -ErrorAction SilentlyContinue

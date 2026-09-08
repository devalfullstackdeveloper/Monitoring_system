$ErrorActionPreference = "SilentlyContinue"

$root = (Resolve-Path $PSScriptRoot).Path.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)

function Read-Url($url) {
    try {
        return (Invoke-WebRequest -Uri $url -TimeoutSec 2 -ErrorAction Stop).Content
    } catch {
        return ""
    }
}

function Get-ListenerPidsForPort($port) {
    $found = @()

    if ($IsWindows) {
        try {
            $results = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop
            foreach ($item in $results) {
                if ($null -ne $item.OwningProcess -and $item.OwningProcess -gt 0) {
                    $found += [int]$item.OwningProcess
                }
            }
            return @($found | Sort-Object -Unique)
        } catch {
            return @()
        }
    }

    $lsof = Get-Command lsof -ErrorAction SilentlyContinue
    if ($lsof) {
        $lsofOutput = & $lsof.Path -nP -iTCP:$port -sTCP:LISTEN -t 2>$null
        foreach ($pidText in $lsofOutput) {
            if ($pidText -match '^\d+$') {
                $found += [int]$pidText
            }
        }
    }

    if (-not $found) {
        $ss = Get-Command ss -ErrorAction SilentlyContinue
        if ($ss) {
            $ssOutput = & $ss.Path -lntp "sport = :$port" 2>$null
            foreach ($line in $ssOutput) {
                if ($line -match 'pid=(\d+)') {
                    $found += [int]$Matches[1]
                }
            }
        }
    }

    return @($found | Sort-Object -Unique)
}

function Stop-PortIfTracker($port, $url, $contentPattern) {
    $content = Read-Url $url
    if ($content -notlike $contentPattern) {
        return
    }

    foreach ($pid in Get-ListenerPidsForPort $port) {
        if ($pid -gt 0) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and
    $_.Path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -and
    $_.ProcessName -match '^python'
} | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

Stop-PortIfTracker 8000 "http://127.0.0.1:8000/health" '*"status":"ok"*'
Stop-PortIfTracker 5173 "http://127.0.0.1:5173/" "*<title>Org Tracker</title>*"

$ErrorActionPreference = "SilentlyContinue"

$root = (Resolve-Path $PSScriptRoot).Path.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)

Write-Host "Stopping Org Tracker (backend, frontend, desktop agent)..."
Write-Host "Project root: $root"
Write-Host ""

function Get-TrackerProcessIds {
    $found = New-Object System.Collections.Generic.List[int]
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    foreach ($p in $all) {
        $cmd = $p.CommandLine
        if (-not $cmd) { continue }
        $isFrontend = ($cmd -like "*$root\frontend*") -and (($cmd -like "*run dev*") -or ($cmd -like "*vite*") -or ($cmd -like "*npm*"))
        $isAgent    = ($cmd -like "*$root\desktop-agent*") -and ($cmd -like "*agent.py*")
        if ($isFrontend -or $isAgent) {
            $found.Add([int]$p.ProcessId)
        }
    }
    return @($found | Sort-Object -Unique)
}

function Get-AncestorChain([int]$procId) {
    $chain = New-Object System.Collections.Generic.List[int]
    $current = $procId
    $depth = 0
    while ($current -and $current -gt 4 -and $depth -lt 10) {
        $chain.Add($current)
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $current" -ErrorAction SilentlyContinue
        if (-not $proc) { break }
        $current = $proc.ParentProcessId
        $depth++
    }
    return @($chain)
}

function Stop-Pid([int]$procId) {
    $result = & taskkill.exe /F /T /PID $procId 2>&1
    Write-Host "taskkill PID $procId : $result"
}

function Get-ListenerPidsForPort([int]$port) {
    $found = New-Object System.Collections.Generic.List[int]
    $lines = & netstat.exe -ano | Select-String ":$port\s"
    foreach ($line in $lines) {
        if ($line.ToString() -match "LISTENING\s+(\d+)\s*$") {
            $found.Add([int]$Matches[1])
        }
    }
    return @($found | Sort-Object -Unique)
}

function Stop-PortCompletely([int]$port) {
    $pids = Get-ListenerPidsForPort $port
    if ($pids.Count -eq 0) {
        Write-Host "Port $port : nothing listening."
        return
    }
    foreach ($procId in $pids) {
        $chain = Get-AncestorChain $procId
        Write-Host "Port $port owned by PID $procId, ancestor chain: $($chain -join ' -> ')"
        foreach ($ancestorId in $chain) {
            Stop-Pid $ancestorId
        }
    }
}

$targets = Get-TrackerProcessIds
if ($targets.Count -eq 0) {
    Write-Host "No matching frontend/agent processes found by command line."
} else {
    Write-Host "Found $($targets.Count) matching process(es): $($targets -join ', ')"
    foreach ($procId in $targets) {
        Stop-Pid $procId
    }
}

Start-Sleep -Milliseconds 800

for ($attempt = 1; $attempt -le 3; $attempt++) {
    Stop-PortCompletely 8000
    Stop-PortCompletely 5173
    Start-Sleep -Milliseconds 700
}

Write-Host ""
Write-Host "Final check:"
foreach ($port in 8000, 5173) {
    $pids = Get-ListenerPidsForPort $port
    if ($pids.Count -gt 0) {
        Write-Host "  Port $port : STILL LISTENING (PID $($pids -join ', '))"
    } else {
        Write-Host "  Port $port : clear."
    }
}

Write-Host ""
Write-Host "Done."
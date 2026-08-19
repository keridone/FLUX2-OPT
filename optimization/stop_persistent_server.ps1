param(
    [string]$ExpectedPath = "E:\flux\sdcpp\experiments\persistent-server-v1\sd-server.exe",
    [int]$ListenPort = 12345
)

$ErrorActionPreference = "Stop"
$Processes = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "sd-server.exe" -and
    $_.ExecutablePath -eq $ExpectedPath -and
    $_.CommandLine -match "--listen-port\s+$ListenPort(?:\s|$)"
}

if (-not $Processes) {
    Write-Output "SERVER_STOPPED=true"
    Write-Output "DETAIL=not_running"
    exit 0
}
if (@($Processes).Count -ne 1) {
    throw "Expected exactly one matching server, found $(@($Processes).Count)"
}

$ProcessId = [int]$Processes.ProcessId
Stop-Process -Id $ProcessId -ErrorAction Stop
Start-Sleep -Seconds 1
if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
    throw "Server process $ProcessId did not stop"
}
Write-Output "SERVER_STOPPED=true"
Write-Output "PID=$ProcessId"

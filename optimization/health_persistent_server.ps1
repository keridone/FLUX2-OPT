param(
    [string]$BaseUrl = "http://127.0.0.1:12345",
    [int]$TimeoutSeconds = 5
)

$ErrorActionPreference = "Stop"
$Started = Get-Date
try {
    $Response = Invoke-RestMethod -Uri "$BaseUrl/sdcpp/v1/capabilities" `
        -Method Get -TimeoutSec $TimeoutSeconds
    $Elapsed = ((Get-Date) - $Started).TotalMilliseconds
    if ($Response.current_mode -ne "img_gen") {
        throw "Unexpected current_mode: $($Response.current_mode)"
    }
    Write-Output "HEALTHY=true"
    Write-Output "MODE=$($Response.current_mode)"
    Write-Output "LATENCY_MS=$([math]::Round($Elapsed, 2))"
} catch {
    Write-Output "HEALTHY=false"
    Write-Output "ERROR=$($_.Exception.Message)"
    exit 1
}

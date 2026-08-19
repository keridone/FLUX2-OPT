param(
    [string]$Root = "E:\flux",
    [string]$ListenIp = "127.0.0.1",
    [int]$ListenPort = 12345,
    [string]$Variant = "persistent-server-v1"
)

$ErrorActionPreference = "Stop"
$Server = Join-Path $Root "sdcpp\experiments\$Variant\sd-server.exe"
$Log = Join-Path $Root "optimization\runs\$Variant.log"
$PidFile = Join-Path $Root "optimization\runs\$Variant.pid"
$CudaRuntime = Join-Path $Root ".venv\Lib\site-packages\nvidia\cuda_runtime\bin"
$Cublas = Join-Path $Root ".venv\Lib\site-packages\nvidia\cublas\bin"
$env:PATH = "$CudaRuntime;$Cublas;$env:PATH"

if (-not (Test-Path -LiteralPath $Server -PathType Leaf)) {
    throw "Server binary not found: $Server"
}
$Existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "sd-server.exe" -and $_.ExecutablePath -eq $Server -and
    $_.CommandLine -match "--listen-port\s+$ListenPort(?:\s|$)"
}
if ($Existing) {
    throw "Persistent server already running on port $ListenPort (PID $($Existing.ProcessId))"
}

$Arguments = @(
    "--diffusion-model", (Join-Path $Root "sdcpp\models\flux-2-klein-4b-Q8_0.gguf"),
    "--vae", (Join-Path $Root "sdcpp\models\split_files\vae\flux2-vae.safetensors"),
    "--llm", (Join-Path $Root "sdcpp\models\Qwen3-4B-Q4_K_M.gguf"),
    "--diffusion-fa", "--cfg-scale", "1.0",
    "--listen-ip", $ListenIp, "--listen-port", "$ListenPort"
)

$Process = Start-Process -FilePath $Server -ArgumentList $Arguments -RedirectStandardOutput $Log `
    -RedirectStandardError "$Log.err" -PassThru
$Process.Id | Set-Content -Encoding ASCII $PidFile

$Healthy = $false
for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
    if ($Process.HasExited) {
        throw "Server exited during startup with code $($Process.ExitCode)"
    }
    try {
        $Response = Invoke-RestMethod -Uri "http://${ListenIp}:$ListenPort/sdcpp/v1/capabilities" `
            -Method Get -TimeoutSec 2
        if ($Response.current_mode -eq "img_gen") {
            $Healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $Healthy) {
    Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue
    throw "Server failed its startup health check"
}
Write-Output "PID=$($Process.Id)"
Write-Output "URL=http://${ListenIp}:$ListenPort"
Write-Output "HEALTHY=true"

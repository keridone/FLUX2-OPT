param(
    [string]$Root = "E:\flux",
    [string]$ListenIp = "127.0.0.1",
    [int]$ListenPort = 12345
)

$ErrorActionPreference = "Stop"
$Server = Join-Path $Root "sdcpp\experiments\persistent-server-v1\sd-server.exe"
$Log = Join-Path $Root "optimization\runs\persistent-server-v1.log"
$CudaRuntime = Join-Path $Root ".venv\Lib\site-packages\nvidia\cuda_runtime\bin"
$Cublas = Join-Path $Root ".venv\Lib\site-packages\nvidia\cublas\bin"
$env:PATH = "$CudaRuntime;$Cublas;$env:PATH"

$Arguments = @(
    "--diffusion-model", (Join-Path $Root "sdcpp\models\flux-2-klein-4b-Q8_0.gguf"),
    "--vae", (Join-Path $Root "sdcpp\models\split_files\vae\flux2-vae.safetensors"),
    "--llm", (Join-Path $Root "sdcpp\models\Qwen3-4B-Q4_K_M.gguf"),
    "--diffusion-fa", "--cfg-scale", "1.0",
    "--listen-ip", $ListenIp, "--listen-port", "$ListenPort"
)

$Process = Start-Process -FilePath $Server -ArgumentList $Arguments -RedirectStandardOutput $Log `
    -RedirectStandardError "$Log.err" -PassThru
Write-Output "PID=$($Process.Id)"
Write-Output "URL=http://${ListenIp}:$ListenPort"

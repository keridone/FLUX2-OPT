param(
    [string]$RunId = "nsys-season-001-v1",
    [string]$InputImage = "E:\flux\benchmark\datasets\season-weather-edit-v1\inputs\season_001_winter_city.png",
    [string]$Prompt = "Change the scene to deep winter with fresh snow and frost. Preserve the street layout, buildings, people, camera viewpoint, and object positions.",
    [int]$Seed = 12001
)

$ErrorActionPreference = "Stop"
$Root = "E:\flux"
$NsightRoot = "C:\Program Files\NVIDIA Corporation\Nsight Systems 2025.3.2"
$Nsys = Join-Path $NsightRoot "target-windows-x64\nsys.exe"
$SdCli = Join-Path $Root "sdcpp\runtime\sd-cli.exe"
$Model = Join-Path $Root "sdcpp\models\flux-2-klein-4b-Q8_0.gguf"
$Llm = Join-Path $Root "sdcpp\models\Qwen3-4B-Q4_K_M.gguf"
$Vae = Join-Path $Root "sdcpp\models\split_files\vae\flux2-vae.safetensors"
$RunRoot = Join-Path $Root "profiling\runs\$RunId"
$TraceBase = Join-Path $RunRoot "trace"
$OutputImage = Join-Path $RunRoot "output.png"

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
$env:PATH = "E:\flux\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;E:\flux\.venv\Lib\site-packages\nvidia\cublas\bin;$env:PATH"

$Missing = @($Nsys, $SdCli, $Model, $Llm, $Vae, $InputImage) | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($Missing.Count -gt 0) {
    throw "Missing required paths: $($Missing -join ', ')"
}

$Metadata = [ordered]@{
    run_id = $RunId
    captured_at = (Get-Date).ToString("o")
    profiler = (& $Nsys --version 2>&1 | Out-String).Trim()
    gpu = (nvidia-smi --query-gpu=name,driver_version,memory.total,power.limit --format=csv,noheader | Out-String).Trim()
    command = [ordered]@{
        input_image = $InputImage
        prompt = $Prompt
        seed = $Seed
        width = 512
        height = 512
        steps = 4
        sampler = "euler"
        cfg_scale = 1.0
        diffusion_flash_attention = $true
        cpu_offload = $true
    }
}
$Metadata | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $RunRoot "metadata.json")

$SdArgs = @(
    "--diffusion-model", $Model,
    "--vae", $Vae,
    "--llm", $Llm,
    "--prompt", $Prompt,
    "--output", $OutputImage,
    "--width", "512",
    "--height", "512",
    "--steps", "4",
    "--cfg-scale", "1.0",
    "--sampling-method", "euler",
    "--diffusion-fa",
    "--offload-to-cpu",
    "--seed", "$Seed",
    "-r", $InputImage,
    "--verbose"
)

& $Nsys profile `
    --trace=cuda,nvtx `
    --sample=none `
    --cpuctxsw=none `
    --cuda-memory-usage=true `
    --gpu-metrics-device=all `
    --gpu-metrics-frequency=10000 `
    --force-overwrite=true `
    --output=$TraceBase `
    $SdCli @SdArgs 2>&1 | Tee-Object -FilePath (Join-Path $RunRoot "sd-cli-profile.log")
if ($LASTEXITCODE -ne 0) {
    throw "nsys profile failed with exit code $LASTEXITCODE"
}

$Reports = @(
    "cuda_gpu_kern_sum",
    "cuda_gpu_kern_gb_sum",
    "cuda_gpu_mem_time_sum",
    "cuda_gpu_mem_size_sum",
    "cuda_api_sum",
    "cuda_kern_exec_sum",
    "cuda_gpu_trace",
    "cuda_api_trace"
)
foreach ($Report in $Reports) {
    $ReportPath = Join-Path $RunRoot "$Report.csv"
    & $Nsys stats --report $Report --format csv "$TraceBase.nsys-rep" 2>&1 |
        Set-Content -Encoding UTF8 $ReportPath
}

Write-Output "NSYS_RUN_ROOT=$RunRoot"

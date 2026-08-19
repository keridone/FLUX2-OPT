param(
    [string]$RunId = "q8-control-deep-v1",
    [string]$SdCli = "E:\flux\sdcpp\experiments\q8-control\sd-cli.exe",
    [int]$LaunchSkip = 50
)

$ErrorActionPreference = "Continue"
$Root = "E:\flux"
$Ncu = "C:\Program Files\NVIDIA Corporation\Nsight Compute 2025.3.1\target\windows-desktop-win7-x64\ncu.exe"
$RunRoot = Join-Path $Root "profiling\runs\$RunId"
New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
$env:PATH = "E:\flux\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;E:\flux\.venv\Lib\site-packages\nvidia\cublas\bin;$env:PATH"

$Args = @(
    "--diffusion-model", "E:\flux\sdcpp\models\flux-2-klein-4b-Q8_0.gguf",
    "--vae", "E:\flux\sdcpp\models\split_files\vae\flux2-vae.safetensors",
    "--llm", "E:\flux\sdcpp\models\Qwen3-4B-Q4_K_M.gguf",
    "--prompt", "Replace the current season with deep winter. Add natural snow cover and bare trees while preserving the exact buildings, people, street layout, camera angle, and composition.",
    "--output", (Join-Path $RunRoot "output.png"),
    "--width", "512", "--height", "512", "--steps", "4",
    "--cfg-scale", "1.0", "--sampling-method", "euler",
    "--diffusion-fa", "--seed", "101",
    "-r", "E:\flux\benchmark\datasets\season-weather-edit-v1\inputs\season_001_winter_city.png"
)

$Sections = @(
    "LaunchStats", "Occupancy", "SpeedOfLight", "ComputeWorkloadAnalysis",
    "MemoryWorkloadAnalysis", "SchedulerStats", "WarpStateStats",
    "InstructionStats", "SourceCounters"
)
$NcuArgs = @(
    "--target-processes", "all",
    "--kernel-name-base", "demangled",
    "--kernel-name", "regex:.*mul_mat_q<\(ggml_type\)8,.*",
    "--launch-skip", "$LaunchSkip", "--launch-count", "1",
    "--replay-mode", "kernel", "--cache-control", "all",
    "--force-overwrite", "--export", (Join-Path $RunRoot "q8-control-deep")
)
foreach ($Section in $Sections) {
    $NcuArgs += @("--section", $Section)
}

$Metadata = [ordered]@{
    run_id = $RunId
    captured_at = (Get-Date).ToString("o")
    runtime = $SdCli
    runtime_sha256 = (Get-FileHash $SdCli -Algorithm SHA256).Hash
    profiler = (& $Ncu --version 2>&1 | Out-String).Trim()
    kernel_regex = ".*mul_mat_q<(ggml_type)8,.*"
    launch_skip = $LaunchSkip
    sections = $Sections
    cpu_offload = $false
}
$Metadata | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $RunRoot "metadata.json")

& $Ncu @NcuArgs $SdCli @Args 2>&1 | Tee-Object -FilePath (Join-Path $RunRoot "profile.log")
if ($LASTEXITCODE -ne 0) {
    throw "Nsight Compute failed with exit code $LASTEXITCODE"
}
& $Ncu --import (Join-Path $RunRoot "q8-control-deep.ncu-rep") --page raw --csv 2>&1 |
    Set-Content -Encoding UTF8 (Join-Path $RunRoot "q8-control-deep.csv")
Write-Output "NCU_RUN_ROOT=$RunRoot"

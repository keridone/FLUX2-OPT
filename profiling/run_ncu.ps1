param(
    [string]$RunId = "ncu-hotspots-v1",
    [string]$OnlyLabel = "",
    [string]$InputImage = "E:\flux\benchmark\datasets\season-weather-edit-v1\inputs\season_001_winter_city.png",
    [string]$Prompt = "Change the scene to deep winter with fresh snow and frost. Preserve the street layout, buildings, people, camera viewpoint, and object positions.",
    [int]$Seed = 12001
)

$ErrorActionPreference = "Continue"
$Root = "E:\flux"
$Ncu = "C:\Program Files\NVIDIA Corporation\Nsight Compute 2025.3.1\target\windows-desktop-win7-x64\ncu.exe"
$SdCli = Join-Path $Root "sdcpp\runtime\sd-cli.exe"
$RunRoot = Join-Path $Root "profiling\runs\$RunId"
New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
$env:PATH = "E:\flux\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;E:\flux\.venv\Lib\site-packages\nvidia\cublas\bin;$env:PATH"

$SdArgs = @(
    "--diffusion-model", "E:\flux\sdcpp\models\flux-2-klein-4b-Q8_0.gguf",
    "--vae", "E:\flux\sdcpp\models\split_files\vae\flux2-vae.safetensors",
    "--llm", "E:\flux\sdcpp\models\Qwen3-4B-Q4_K_M.gguf",
    "--prompt", $Prompt,
    "--output", (Join-Path $RunRoot "output.png"),
    "--width", "512", "--height", "512", "--steps", "4",
    "--cfg-scale", "1.0", "--sampling-method", "euler",
    "--diffusion-fa", "--offload-to-cpu", "--seed", "$Seed",
    "-r", $InputImage
)

$Profiles = @(
    [ordered]@{ label = "mul_mat_q_type8"; regex = ".*mul_mat_q<\(ggml_type\)8,.*"; skip = 50 },
    [ordered]@{ label = "mul_mat_q_type12"; regex = ".*mul_mat_q<\(ggml_type\)12,.*"; skip = 20 },
    [ordered]@{ label = "flash_attention"; regex = ".*flash_attn_ext_f16.*"; skip = 20 },
    [ordered]@{ label = "im2col"; regex = ".*im2col_kernel.*"; skip = 10 },
    [ordered]@{ label = "copy_scalar"; regex = ".*cpy_scalar.*"; skip = 100 },
    [ordered]@{ label = "binary_broadcast"; regex = ".*k_bin_bcast.*"; skip = 100 }
)
if ($OnlyLabel) {
    $Profiles = @($Profiles | Where-Object { $_.label -eq $OnlyLabel })
    if ($Profiles.Count -ne 1) {
        throw "Unknown profile label: $OnlyLabel"
    }
}

$Metadata = [ordered]@{
    run_id = $RunId
    captured_at = (Get-Date).ToString("o")
    profiler = (& $Ncu --version 2>&1 | Out-String).Trim()
    set = "basic"
    launch_count = 1
    profiles = $Profiles
}
$Metadata | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $RunRoot "metadata.json")

foreach ($Profile in $Profiles) {
    $Report = Join-Path $RunRoot $Profile.label
    $Log = Join-Path $RunRoot "$($Profile.label).log"
    Write-Output "NCU_PROFILE=$($Profile.label)"
    & $Ncu `
        --set basic `
        --target-processes all `
        --kernel-name-base demangled `
        --kernel-name "regex:$($Profile.regex)" `
        --launch-skip $Profile.skip `
        --launch-count 1 `
        --force-overwrite `
        --export $Report `
        $SdCli @SdArgs 2>&1 | Tee-Object -FilePath $Log
    if ($LASTEXITCODE -ne 0) {
        throw "NCU profile $($Profile.label) failed with exit code $LASTEXITCODE"
    }
    & $Ncu --import "$Report.ncu-rep" --page raw --csv 2>&1 |
        Set-Content -Encoding UTF8 (Join-Path $RunRoot "$($Profile.label).csv")
}

Write-Output "NCU_RUN_ROOT=$RunRoot"

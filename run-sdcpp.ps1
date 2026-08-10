param(
    [Parameter(Position = 0)]
    [string]$Prompt = "A cinematic futuristic Shanghai street at night, neon reflections on wet pavement, photorealistic",
    [string]$Output = "E:\flux\outputs\sdcpp-output.png",
    [int]$Width = 1024,
    [int]$Height = 1024,
    [int]$Seed = 42
)

$ErrorActionPreference = "Stop"
$Root = "E:\flux\sdcpp"
$CudaRuntime = "E:\flux\.venv\Lib\site-packages\nvidia\cuda_runtime\bin"
$CuBlas = "E:\flux\.venv\Lib\site-packages\nvidia\cublas\bin"
$env:PATH = "$CudaRuntime;$CuBlas;$env:PATH"

& "$Root\runtime\sd-cli.exe" `
    --diffusion-model "$Root\models\flux-2-klein-4b-Q8_0.gguf" `
    --vae "$Root\models\split_files\vae\flux2-vae.safetensors" `
    --llm "$Root\models\Qwen3-4B-Q4_K_M.gguf" `
    --prompt $Prompt `
    --output $Output `
    --width $Width `
    --height $Height `
    --steps 4 `
    --cfg-scale 1.0 `
    --sampling-method euler `
    --diffusion-fa `
    --offload-to-cpu `
    --seed $Seed

if ($LASTEXITCODE -ne 0) {
    throw "stable-diffusion.cpp inference failed with exit code $LASTEXITCODE"
}

# FLUX2-OPT

FLUX.2 Klein 4B inference deployment and performance optimization for
`stable-diffusion.cpp` on Windows with NVIDIA CUDA.

## Current baseline

- GPU: NVIDIA GeForce RTX 5060 Ti 16 GB
- Runtime: `stable-diffusion.cpp` commit `bfbef5b`
- Diffusion model: FLUX.2 Klein 4B Q8_0 GGUF
- Text encoder: Qwen3-4B Q4_K_M GGUF
- VAE: FLUX.2 VAE
- Inference: Euler, 4 steps, CFG 1.0, diffusion Flash Attention
- 512 x 512 baseline: about 5.2 seconds end to end

Model weights and generated images are intentionally excluded from Git.

## Remote layout

```text
E:\flux\
  run-sdcpp.ps1
  sdcpp\
    runtime\sd-cli.exe
    models\
      flux-2-klein-4b-Q8_0.gguf
      Qwen3-4B-Q4_K_M.gguf
      split_files\vae\flux2-vae.safetensors
```

## Download model files

Run on the Windows inference host:

```powershell
E:\flux\.venv\Scripts\python.exe E:\flux\sdcpp\download_sdcpp_models.py
```

The downloader retries interrupted Hugging Face transfers automatically.

## Run inference

```powershell
powershell -ExecutionPolicy Bypass -File E:\flux\run-sdcpp.ps1 `
  -Prompt "A cinematic futuristic Shanghai street at night" `
  -Output E:\flux\outputs\result.png `
  -Width 1024 `
  -Height 1024 `
  -Seed 42
```

The launcher adds the CUDA 12 runtime and cuBLAS DLL directories installed in
the project virtual environment to `PATH` before invoking `sd-cli.exe`.

## Optimization workflow

Future changes should be benchmarked against fixed prompts, seeds, dimensions,
and sampling settings. Record at least total latency, sampling latency, peak
VRAM, peak RAM, and output-quality observations.

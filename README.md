# FLUX2-OPT

FLUX.2 Klein 4B inference deployment and performance optimization for
`stable-diffusion.cpp` on Windows with NVIDIA CUDA.

## Performance dashboard

The continuously updated optimization history is published at
[keridone.github.io/FLUX2-OPT](https://keridone.github.io/FLUX2-OPT/). To add a
new chart node and detail card, append one entry to
[`docs/data/optimization-history.json`](docs/data/optimization-history.json).

## Current baseline

- GPU: NVIDIA GeForce RTX 5060 Ti 16 GB
- Runtime: `stable-diffusion.cpp` commit `bfbef5b`
- Diffusion model: FLUX.2 Klein 4B Q8_0 GGUF
- Text encoder: Qwen3-4B Q4_K_M GGUF
- VAE: FLUX.2 VAE
- Inference: Euler, 4 steps, CFG 1.0, diffusion Flash Attention
- 512 x 512 text-to-image reference: about 5.2 seconds end to end
- 512 x 512 image-edit baseline with CPU offload: 7.0354 seconds median
- 512 x 512 image-edit baseline without CPU offload: 5.8415 seconds median

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
Model weights are GPU-resident by default. On lower-memory devices, use
module-level placement such as `--backend te=cpu` before falling back to the
more expensive `--offload-to-cpu` mode.

## Optimization workflow

Phase 1 uses a fixed 20-task season/weather replacement set. See
[`benchmark/PROTOCOL.md`](benchmark/PROTOCOL.md) for the locked protocol and
[`benchmark/results/baseline-bfbef5b-q8-v1`](benchmark/results/baseline-bfbef5b-q8-v1)
for the first performance and quality baseline.

Run the benchmark on the Windows inference host:

```powershell
E:\flux\.venv\Scripts\python.exe E:\flux\benchmark\code\run_baseline.py `
  --manifest E:\flux\benchmark\code\tasks.json `
  --mode all `
  --run-id baseline-bfbef5b-q8-v1
```

Future changes must use a new run ID and be compared against the fixed inputs,
seeds, dimensions, sampling settings, and quality gate.

The first CUDA profiling dataset and bottleneck analysis are under
[`profiling/`](profiling/). It includes raw Nsight Systems/Compute reports,
normalized CSV/JSON data for visualization, reproducible collection scripts,
and the current compute/bandwidth/VRAM bottleneck classification.

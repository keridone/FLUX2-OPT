# Phase 1 Benchmark Protocol

## Scope

This phase evaluates only instruction-based season and weather replacement.
It does not cover object insertion/removal, color replacement, text editing, or
style transfer.

## Locked environment

- Model: FLUX.2 Klein 4B Q8_0 GGUF
- Text encoder: Qwen3-4B Q4_K_M GGUF
- VAE: FLUX.2 VAE
- Runtime: stable-diffusion.cpp commit `bfbef5b`
- Backend: CUDA on NVIDIA GeForce RTX 5060 Ti 16 GB
- Resolution: 512 x 512
- Sampler: Euler
- Steps: 4
- CFG scale: 1.0
- Diffusion Flash Attention: enabled
- CPU offload: enabled
- RNG: CUDA

The benchmark script records runtime and model file hashes with every run. A
change to any locked item creates a new benchmark configuration rather than
overwriting the baseline.

## Dataset

The first regression set contains 20 synthetic editing tasks:

- 10 season replacements
- 10 weather replacements

Input images are generated once from fixed prompts and seeds. They are then
treated as immutable benchmark inputs. Each instruction requests one primary
change and explicitly requires preservation of scene layout, objects, camera,
lighting geometry, and identity.

## Measurement procedure

1. Generate missing source images once.
2. Run one unmeasured warm-up edit.
3. Run every edit three times in task order.
4. Save every output and the raw runtime log.
5. Poll GPU memory/utilization and process RSS during inference.
6. Parse text encoding, reference encoding, sampling, VAE decoding, and total
   generation timings from stable-diffusion.cpp logs.
7. Report median and P95 end-to-end latency, plus peak VRAM and RAM.

## Quality review

The first output for each task is reviewed using four binary criteria:

- `instruction_success`: requested season/weather is clearly present.
- `content_preservation`: scene geometry and important objects are preserved.
- `local_consistency`: shadows, reflections, precipitation, vegetation, and
  surfaces are consistent with the requested condition.
- `artifact_free`: no major deformation, duplication, or broken structure.

An optimization is not accepted solely because it is faster. It must meet the
quality gate defined after the baseline review.

## Reproducibility

- Do not edit generated source images in place.
- Do not replace an existing baseline result directory.
- Record hashes for inputs, models, runtime, manifest, and scripts.
- Run benchmarks while unrelated GPU workloads are stopped.
- Record driver version, GPU name, Windows version, and free disk space.

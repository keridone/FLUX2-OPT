# stable-diffusion.cpp build and runtime audit

## Evidence-backed status

| Item | Status | Evidence |
| --- | --- | --- |
| Runtime revision | Confirmed | `sd-cli --version` captured `commit bfbef5b`; executable SHA-256 is stored in the no-offload environment record. |
| CUDA backend | Confirmed | RTX 5060 Ti execution and CUDA kernels are present in the saved Nsight reports. |
| CPU offload | Disabled | The deployed command omits `--offload-to-cpu`; the no-offload baseline peaked at 10,735 MiB of 16,311 MiB. |
| Diffusion Flash Attention requested | Confirmed | The deployed command contains `--diffusion-fa`. |
| Diffusion Flash Attention executed | Confirmed | Nsight captured 100 launches of `flash_attn_ext_f16<128,128,64,...>`, accounting for 13.8% of kernel time. |
| CUDA Graph | Not detected | The deployed command has no graph option and the saved profile contains normal per-op launches. Remote CLI/source inspection is still required to distinguish unsupported from supported-but-disabled. |
| Q8 GEMM implementation | Confirmed | Nsight captured `mul_mat_q<8,128,0>`: 36.0% of kernel time, 255 registers/thread, 58.88 KiB shared memory, and 16.7% active warps. |

## Remote checks still required

The host `100.68.188.85` was unreachable on 2026-08-19: SSH port 22 timed
out before authentication and ICMP received no reply. When it is reachable,
capture all of the following before rebuilding:

1. Full `sd-cli.exe --version` and `--help` output.
2. Runtime DLL list and SHA-256 hashes.
3. Source commit/submodule revisions and dirty status.
4. `CMakeCache.txt` entries matching CUDA, architecture, build type, cuBLAS,
   Flash Attention, and graph settings.
5. A verbose control log containing the Flash Attention selection message.
6. An Nsight Systems control trace and CUDA API summary; search for
   `cudaGraphInstantiate`, `cudaGraphLaunch`, and related graph APIs.

Do not claim CUDA Graph is disabled solely because there is no CLI flag: a
backend may capture internally. The CUDA API trace is the decisive runtime
check.

## Parameter screen

The executable experiment specification is
[`parameter-matrix.json`](parameter-matrix.json). Run one warmup and five timed
runs per cell on `season_001_winter_city`. Preserve stdout, output image hashes,
stage timings, wall time, peak GPU utilization, peak VRAM, and process RSS.

The control must run first and again last. If the two controls differ by more
than 3% in median latency, discard the screen as thermally or operationally
unstable. Randomize the middle cells to reduce ordering bias.

## Q8 GEMM work package

Parameter screening must not be mixed with kernel changes. Create a pinned
source build at `bfbef5b`, reproduce the deployed executable hash or explain
the difference, then make one kernel change per build.

The first Q8 experiments are:

1. Establish compiler and architecture controls: Release build, exact CUDA
   toolkit, explicit RTX 5060 Ti architecture, and unchanged model files.
2. Record compiler resource usage for `mul_mat_q<8,128,0>` and verify the
   255-register result independently of Nsight replay.
3. Sweep block/tile specializations that lower registers and/or shared memory;
   reject variants that reduce occupancy without reducing kernel duration.
4. Inspect whether the Q8 path uses Tensor Cores effectively. Compare a fused
   dequantize-plus-GEMM path only after the tile sweep provides a stable
   control.
5. Profile the same representative launch with Nsight Compute and run the full
   five-repeat edit screen. Kernel-only improvement is insufficient if launch,
   synchronization, or conversion overhead cancels it end-to-end.

Every candidate must retain the baseline output hash where deterministic. If a
compiler change prevents byte equality, run the complete quality review before
acceptance.

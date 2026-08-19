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

### Parameter screen result (v2)

The second screen passed the stability check: the final control median differed
from the initial control by only +0.173%.

| Cell | Median wall time | Change vs control | Decision |
| --- | ---: | ---: | --- |
| Flash Attention, automatic threads | 5.7941 s | control | Keep |
| Flash Attention, 16 threads | 5.8028 s | +0.15% | Reject: no improvement |
| Flash Attention, 8 threads | 5.8192 s | +0.43% | Reject: no improvement |
| No Flash Attention | 6.7366 s | +16.27% | Reject |
| Flash Attention + direct VAE convolution | 15.1887 s | +162.16% | Reject |

The fixed-thread cells are byte-identical to the control. Disabling Flash
Attention and enabling direct VAE convolution produce different output hashes,
in addition to being slower. Raw records and the machine-readable summary are
stored in `optimization/results/parameter-screen-v2`.

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

### Deep Q8 bottleneck classification

Nsight Compute captured a representative `mul_mat_q<8,128,0>` launch at
6.9495 ms. It uses 255 registers/thread and 58.88 KiB shared memory/block,
with no local-memory spills. Active warps are 16.67%, SM throughput is 54.30%,
Tensor/IMMA activity is 37.37%, and DRAM throughput is only 13.46%. The Q8
kernel is therefore occupancy/compute-latency constrained, not DRAM-bandwidth
or spill constrained. Machine-readable metrics and the full report are in
`optimization/results/q8-control-deep-v1`.

### Q8 experiment 2: reduce `mmq_y` to 64

The candidate retained `mmq_x=128` and attempted to halve `mmq_y`, which would
reduce dynamic shared memory from 58.88 KiB to approximately 38.88 KiB. The
corrected source was rejected at compile time by the MMA invariant
`nwarps*tile_C::I == mmq_y`. The current implementation couples eight warps to
the 128-row accumulator tile, so changing Y alone is not a valid specialization.
No timed A/B runs were accepted and the deployed runtime was not changed. The
failure logs and decision record are stored in
`optimization/results/q8-mmq-y64-v1`.

### Q8 experiment 1: cap `mmq_x` at 64

The first candidate limited `GGML_TYPE_Q8_0` to `mmq_x <= 64`, instead of the
selected `mmq_x=128`, to test the low-occupancy hypothesis. The candidate was
compiled for CUDA architecture 120a and compared with an otherwise identical
source-built control in alternating order.

| Variant | Median wall time | Median sampling | Peak VRAM |
| --- | ---: | ---: | ---: |
| Control, `mmq_x=128` | 5.7585 s | 3.13 s | 10,754 MiB |
| Candidate, `mmq_x<=64` | 5.9808 s | 3.35 s | 10,748 MiB |

The candidate regressed end-to-end latency by 3.86%, saved only 6 MiB of peak
VRAM, and changed the output hash. It is rejected. The result shows that simply
reducing the tile width loses more work efficiency than it gains from lower
resource pressure. The next Q8 experiment should preserve `mmq_x=128` and
target register lifetime/instruction scheduling inside the Q8 specialization,
or compare the current implementation with a fused Tensor Core path.

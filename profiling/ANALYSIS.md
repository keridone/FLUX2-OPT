# FLUX.2 image-edit profiling analysis

## Scope and interpretation

The profile uses task `season_001_winter_city` with the phase-1 baseline model,
prompt, seed, 512 x 512 resolution, Euler sampler, four steps, Flash Attention,
and CPU offload. Uninstrumented baseline timings remain the latency reference;
Nsight Systems and Nsight Compute measurements are used for attribution because
profilers add replay and tracing overhead.

## Stage-level baseline

| Stage | Median | Share of internal generation | Share of wall time |
| --- | ---: | ---: | ---: |
| Reference image encode | 0.54 s | 8.6% | 7.7% |
| Text conditioning | 1.42 s | 22.5% | 20.2% |
| Sampling | 3.80 s | 60.3% | 54.0% |
| VAE decode | 0.54 s | 8.6% | 7.7% |
| Internal generation total | 6.30 s | 100% | 89.5% |
| End-to-end wall time | 7.0354 s | - | 100% |

Sampling is the largest stage. Text conditioning is the second-largest stage,
so an optimization that affects only diffusion sampling has a measured upper
bound of roughly 54% end-to-end reduction before quality and new overheads.

## Nsight Systems attribution

- 6,215 kernel launches across 54 unique kernels were recorded.
- Summed kernel execution was 2,501.37 ms in a 6,170.11 ms GPU-active window.
- CUDA memory operations added 608.35 ms; kernels plus memory operations occupy
  about 50.4% of that window. The remaining 3,060.40 ms contains CPU work,
  launch gaps, synchronization, model/weight staging, and profiler overhead.
- The top ten kernel families account for 88.3% of kernel time.

| Kernel family | GPU kernel time | Calls | Share |
| --- | ---: | ---: | ---: |
| `mul_mat_q<type 8>` | 899.44 ms | 320 | 36.0% |
| `flash_attn_ext_f16` | 344.50 ms | 100 | 13.8% |
| `im2col_kernel<half>` | 213.34 ms | 64 | 8.5% |
| `cpy_scalar<float,float>` | 199.17 ms | 946 | 8.0% |
| elementwise multiply broadcast | 157.55 ms | 923 | 6.3% |
| elementwise add broadcast | 154.82 ms | 919 | 6.2% |
| RMS normalization | 67.84 ms | 294 | 2.7% |
| SiLU | 62.01 ms | 217 | 2.5% |

CUDA API data also shows 2,932.42 ms accumulated in 752
`cudaStreamSynchronize` calls. Four `cudaMallocHost` calls accumulated 923.50 ms
and four `cudaFreeHost` calls accumulated 328.28 ms. These API durations are not
blindly added to wall time, but they confirm substantial synchronization and
host-staging costs.

CPU offload caused 7,722.64 MB of cumulative host-to-device traffic across 734
copies, taking 589.57 ms of GPU copy-engine time. Device-to-device traffic was
3,600.60 MB. This is a meaningful transfer cost even though it is not the main
kernel bottleneck.

## Hardware-counter classification

Each row below is one representative launch selected from a Systems hotspot.

| Operator | DRAM throughput | SM throughput | Active warps | Registers/thread | Shared memory | Classification |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Q8 matrix multiply (`type 8`) | 13.9% | 51.7% | 16.7% | 255 | 58.88 KiB | Occupancy/compute-latency limited |
| Flash Attention | 17.4% | 23.0% | 15.3% | 254 | 27.65 KiB | Occupancy/latency limited |
| im2col | 19.0% | 77.9% | 72.9% | 44 | 1.02 KiB | Compute-throughput limited |
| scalar copy/convert | 49.8% | 73.9% | 90.2% | 34 | 1.02 KiB | Mixed compute/memory |
| elementwise broadcast | 90.1% | 33.0% | 89.4% | 20 | 1.02 KiB | DRAM-bandwidth limited |

The dominant Q8 matrix-multiply kernel is not DRAM-bandwidth limited. Its 255
registers per thread and 58.88 KiB shared-memory allocation coincide with only
16.7% active warps. Flash Attention shows the same low-occupancy pattern. Kernel
specialization, register pressure, tile shape, and launch configuration are
therefore higher-value targets than generic memory-bandwidth tuning for these
two operators.

Elementwise broadcast kernels are individually bandwidth-bound and collectively
consume 12.5% of kernel time for add and multiply alone. Fusion that removes
intermediate tensors and kernel launches is preferable to optimizing their
arithmetic.

## Global bottleneck verdict

This workload is **not constrained by VRAM capacity**: phase-1 peak allocation
was about 6,756 MiB out of 16,311 MiB (41.4%). It is also **not globally limited
by DRAM bandwidth**: during the kernel window, sampled DRAM read/write means were
11.2% and 8.8%, with P95 values of 50% and 41%.

The primary bottleneck is a combination of:

1. low occupancy and execution latency in Q8 matrix multiply and Flash Attention;
2. many launches and synchronization gaps;
3. CPU-offload weight staging and host-to-device transfers;
4. bandwidth-bound unfused elementwise work;
5. compute-bound im2col work.

## Optimization order suggested by the evidence

1. Test reduced/disabled CPU offload because more than 9 GiB of VRAM headroom is
   available; measure whether it removes H2D transfers and synchronization.
2. Investigate the `mul_mat_q<type 8>` implementation for Blackwell/SM 12.0,
   especially register pressure, shared-memory tile shape, and Tensor Core use.
3. Test Flash Attention variants or tile settings that reduce registers and
   increase active warps.
4. Fuse add/multiply/normalization/copy chains to reduce bandwidth traffic and
   the very high launch count.
5. Only then optimize im2col or consider sampler/step-level algorithmic changes.

## Saved data

- `profiling/results/nsys-season-001-v1/trace.nsys-rep`: forward-compatible raw
  Nsight Systems report.
- `profiling/results/nsys-season-001-v1/*.csv`: CUDA API, kernel, memory, launch,
  and full GPU trace exports.
- `profiling/results/nsys-season-001-v1/metrics`: sampled GPU counters and a
  downsampled time series suitable for plotting.
- `profiling/results/ncu-hotspots-v1/*.ncu-rep`: raw per-kernel Nsight Compute
  reports.
- `profiling/results/ncu-hotspots-v1/hotspot_summary.csv`: normalized operator
  counter table for visualization.
- The full 114.8 MB Systems SQLite export remains on the host at
  `E:\flux\profiling\runs\nsys-season-001-v1\trace.sqlite`.

Nsight Systems documents the GPU-metric SQLite tables and percentage values in
its official user guide:
https://docs.nvidia.com/nsight-systems/UserGuide/index.html#gpu-metrics

# FLUX.2 profiling

Profiling uses the same fixed model, image, prompt, seed, resolution, sampler,
step count, Flash Attention, and CPU-offload settings as the phase-1 baseline.

The collection has three levels:

1. stable-diffusion.cpp phase timings from its verbose log;
2. Nsight Systems CUDA API, kernel, memory-operation, launch-gap, and GPU-metric
   timelines;
3. Nsight Compute hardware counters for kernels selected from the Nsight Systems
   hotspots.

Run Nsight Systems on the Windows inference host:

```powershell
powershell -ExecutionPolicy Bypass -File E:\flux\profiling\code\run_nsys.ps1
```

Profiler overhead is expected. Nsight timing is used to find bottlenecks and
attribute GPU time, while the uninstrumented benchmark remains the source of
truth for end-to-end latency.

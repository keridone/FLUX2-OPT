# No-CPU-offload baseline v1

This run removes `--offload-to-cpu` while keeping every other phase-1 setting
fixed. It contains 20 season/weather editing tasks with three repetitions each.

## Result

| Metric | CPU offload | No CPU offload | Change |
| --- | ---: | ---: | ---: |
| End-to-end median | 7.0354 s | 5.8415 s | -16.97% |
| End-to-end P95 | 7.0760 s | 5.8740 s | -16.99% |
| Internal generation median | 6.30 s | 5.36 s | -14.92% |
| Reference encode median | 0.54 s | 0.52 s | -3.70% |
| Text conditioning median | 1.42 s | 1.16 s | -18.31% |
| Sampling median | 3.80 s | 3.17 s | -16.58% |
| VAE decode median | 0.54 s | 0.51 s | -5.56% |
| Peak VRAM median | 6,748 MiB | 10,725 MiB | +58.94% |
| Peak process RSS median | 8,125 MiB | 2,455 MiB | -69.78% |

Maximum observed VRAM was 10,735 MiB out of 16,311 MiB, leaving about 5.45 GiB
of capacity headroom. Full GPU residency is therefore safe for this fixed 512 x
512 workload.

The deployment launcher's default 1024 x 1024 text-to-image configuration was
also smoke-tested successfully without CPU offload. Its internal generation time
was 8.75 seconds, and all 7,821.21 MB of model parameters were GPU-resident.

## Quality gate

All 20 first-repetition output SHA-256 hashes are byte-for-byte identical to the
CPU-offload baseline. The existing quality scores therefore carry over exactly:

- instruction success: 17/20
- content preservation: 20/20
- local consistency: 17/20
- artifact-free: 20/20
- all criteria passed: 17/20

## Deployment decision

The default launcher no longer passes `--offload-to-cpu`. If a larger resolution
or a different model exceeds available VRAM, first try module-level placement,
for example `--backend te=cpu`, before restoring full dynamic CPU offload.

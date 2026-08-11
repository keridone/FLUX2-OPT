# Baseline bfbef5b Q8 v1

This baseline contains 20 season/weather replacement tasks, each measured three
times after one warm-up run. The first output of each task was visually reviewed.

## Performance

- End-to-end latency: 7.0354 s median, 7.0760 s P95
- Internal generation: 6.3000 s median
- Sampling: 3.8000 s median
- Text conditioning: 1.4200 s median
- Reference image encoding: 0.5400 s median
- VAE decoding: 0.5400 s median
- Peak GPU memory: 6748 MiB median, 6756.05 MiB P95
- Peak process RSS: 8125.13 MiB median

## Quality

- Instruction success: 17/20 (85%)
- Content preservation: 20/20 (100%)
- Local consistency: 17/20 (85%)
- Artifact-free: 20/20 (100%)
- All four criteria passed: 17/20 (85%)

The three failed instructions were residual snow in the spring-village edit,
strong direct sunlight in the overcast-park edit, and absent visible rainfall in
the rain-temple edit. These failures are part of the baseline and must not be
silently removed when evaluating acceleration methods.

Raw generated images and logs remain on the benchmark host under
`E:\flux\benchmark`. They are intentionally excluded from Git.

# Flux.2 timestep micro-batch 实验

## 目标

验证两个 512×512、Euler 四步任务能否在 batch 轴拼接 latent、noise、文本条件和
参考图 latent，使每个 timestep 只执行一次 batched diffusion forward。当前双缓存
持久服务的热点两任务 control 为 4.9427 秒、0.4046 task/s。

## 源码审计

现有 `batch_count` 在 `generate_image` 中逐张调用完整 `sample()`，并非 GPU batch。
Euler 采样器也是完整的内部循环，server worker 则在 `generate_image` 外持有唯一
`sd_ctx_mutex`。因此异构任务合批需要先将采样过程拆为可暂停状态，再在相同
shape、sigma、采样器和 guidance 的任务之间合并 diffusion compute。

## batch=2 原型

第一版原型为同一请求构造两组独立 seed，把以下 tensor 沿 batch 轴拼接：

- 初始 latent 与 noise；
- positive、unconditional 和 image-unconditional condition；
- `c_concat`、参考图 latent 与 denoise mask。

输出计划沿 batch 轴拆成两个独立 latent，再分别 VAE decode。

### 结果一：框架主动拒绝

编译成功，但第一次 diffusion graph 构建触发：

```text
flux.hpp:1525: GGML_ASSERT(x->ne[3] == 1) failed
```

这证明当前 Flux runner 明确限定 batch size 为 1。

### 结果二：解除断言后无进展

仅将保护条件改为允许 batch 后重新编译。服务成功加载模型并进入 micro-batch
sampling，但超过 90 秒没有完成第一个 timestep：

| 指标 | 观测值 |
| --- | ---: |
| GPU 利用率 | 1% |
| GPU 显存 | 4,595 MiB |
| 进程累计 CPU | 4.703125 s，后续不再增长 |
| control 两任务耗时 | 4.9427 s |

该表现不是显存不足，而是 batch graph 进入不兼容的后端等待路径。实验进程已
安全停止，GPU 显存恢复，原始 assert 和双缓存源码均已恢复并重新编译通过。

## 结论

直接沿 latent batch 轴合并不能纳入系统。当前 Flux 图不是“解除一个断言即可批处理”，
还需要逐层改造 patch embedding、RoPE、reference token 组织、attention batch 语义、
后端 buffer binding 和输出拆分。以当前四步、4B 模型和单卡规模计算，工程风险高于
预期收益。

后续并行方向应转为更窄的算子级实验：保持任务串行状态，只评估 Q8 GEMM/attention
内部的 kernel 并行度、融合和 CUDA Graph；生产 control 继续使用模型常驻、请求队列、
参考图 latent LRU 与文本条件 LRU。

# UAC PCM 的 v24 gap 上限（2026-11-02）

> 目的：在已验证的“单次 3072B、约 96ms 周期”传输形状下，判断 48kHz
> 立体声能否连续送到 host；如果不可以，哪些部分仍然值得做。

## 输入（实测）

- 一次 burst = 16 帧 × 192 B = **3072 B = 16 ms** PCM 数据（48kHz/2ch/16bit）；
- 周期 ≈ **96 ms**：post 0 + wait 59–61 + report 19–20 + loop 3–14（v24 实测）；
- 单次请求上限已由 v28/v28b 闭合：**16 帧可用，20 帧与 32 帧都挂死整机**；
- 驱动同时只允许 **1 个在飞请求**（v27：第二次 post 不进 cave，直接 `xfer=0 status=5`）。

## 模型

`tools/model_uac_pcm_ring.py` 的 `simulate_gap()`：1 ms 步进、10 s、64 KiB
ring、48kHz 连续源、每 96 ms 提交一个 3072B fragment。

| 指标 | 值 |
| --- | ---: |
| 周期 | 96 ms |
| posts（10 s） | 104 |
| 线上数据 | 319,488 B |
| 占空比 | **16.6%** |
| 48kHz 源 | 1,920,000 B / 10 s |
| 丢弃 | 1,535,168 B（≈80%） |
| host 空闲 | 8,336 ms / 10 s |
| ring | 始终顶满 64 KiB |

即使把周期压到 60 ms（lead 降到理论上限），占空比也只有 ~27%，仍然远低于
连续音频需要的 100%。

## 结论

1. 16/96 的占空比**不可能**承载 48kHz 连续音频；这是结构性上限，不是调度
   bug，也不是 ring 容量或 lead 参数问题。
2. **标准 UAC 音频在当前驱动能力下不可用**：host 的 `snd-usb-audio` 会看到
   每 96 ms 中 80 ms 的空洞，必然 xrun。UAC 保持禁用。
3. 可选的下一步（按代价）：
   - **关闭 gap**：需要驱动层支持多请求或更长 TD；v27/v28/v28b 已证明当前
     API 两条路都不行 → 挂账，等驱动侧突破口；
   - **自定义 host 拼接**（非标准 UAC）：host 自己按时间戳把 burst 拼起来，
     需要自写驱动/应用，不能用标准音频栈；
   - **非 USB 音频**：继续用 BT/line-in 作为产品 workaround。
4. 不依赖 gap 关闭、现在就可以做的：保持 48kHz 采样时钟与 fragment 内样本
   相位连续、序号单调，为将来连续路径准备；**不要**声称 clock lock 或零
   xrun。

## 若将来恢复 UAC，验收前置条件

- 单次请求 ≥ 16 帧且连续（当前上限 16 帧）；
- 至少 2 个请求在飞（当前 1 个）；
- ring 占用稳定在 ±1 fragment；
- host 侧可测的无 xrun 时长。

参考：[UAC_PCM_PRODUCER.md](UAC_PCM_PRODUCER.md)、
[CURRENT.md](CURRENT.md)、[UAC_U2_PIPELINE.md](UAC_U2_PIPELINE.md)。

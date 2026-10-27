# UAC PCM producer 设计（2026-10-27）

## 已证明的底层

- `usb:ds` 的 alt0-only endpoint filter 已用 runtime NOP patch 去掉；alt1 端点可以安装。
- A23 16×192 burst producer 在 alt1 `EP0x83`/MPS256/interval4 上完成 16/16 包、
  `URB 387 requested=raw=3072 status=3`。
- 这证明“alt1 ISO 传输”本身可用；还没证明连续 PCM。

## 为什么不能直接拿 A23 burst 当 PCM

[iso_burst_patch.S:44-47](../patches/iso_burst_patch.S#L44-L47) 每次提交都用
`FrameID = (MFI >> 3) + 32`，然后 15 个 TD 逐个 +1。**问题不在公式，而在同时提交的
URB 数量。**

- A23 一次只挂 1 个 URB、等完成再提交：首 TD 在 `now+32ms`；下一个 URB 在
  `完成时刻+32ms` 才开始，16ms 数据/48ms 周期 = **33%**，不是 80%。
- 同时挂 **3 个 URB**、每 16ms 提交一个：第 k 个 URB 的起点是 `post_k+32ms`，
  而 `post_k = post_0 + 16k`，所以起点正好是 `start_{k-1}+16ms`，连续且不重叠。
  此时不需要持久游标。

所以第一优先是验证 **3 URB in flight + 现有 `MFI+32` 公式**；游标是 post 抖动/多 URB
完成不可靠时的稳健性后备，而不是连续性的必要条件。

## 目标形状

- UAC AS alt1：`EP0x83`、HS ISO、192B/1ms、MPS256、48kHz/2ch/16bit。
- 16 个 TD/URB = 3072B = 16ms；最多 3 个 URB 在飞。
- 不改变已验证的 alt1/NOP/A23 producer hook；只把“帧起点”从 MFI 改成游标。

## 数据路径

```
grc:d (4096B ≈ 21.3ms)
  -> PCM ring (64KiB, SPSC, sample-aligned)
  -> URB assembler (3072B = 16ms)
  -> usbDsEndpoint_PostBufferAsync
  -> A23-style Isoch TRB producer (cursor)
  -> xHCI ring -> host snd-usb-audio
```

## Ring 规则

- 容量 64KiB；单生产者（grc:d 读线程）、单消费者（USB poster）。
- 读/写都按 4 字节立体声帧对齐；跨 4096B 块保留余量，不逐块补零。
- **欠载**：补静音并计数，不把旧数据重复发送；欠载事件进入状态/日志。
- **过载**：默认阻塞生产者（背压），不覆盖未交还的 DMA 缓冲；只在明确策略下丢最旧数据。
- 所有计数（写入/读出/欠载/过载/URB 完成）进入一个只读状态结构，供 host 诊断。

## URB 调度

| 参数 | 值 |
| --- | --- |
| TD/URB | 16 |
| 每 TD | 192B / 1ms |
| URB 时长 | 16ms |
| 在飞 URB | 3 |
| 提交提前量 | 4ms（lead32 帧） |
| 完成 | 每 TD Event Data TRB；URB 完成后才复用缓冲 |

- `cursor` 是端点上下文里的持久 `next_frame`（0..2047）。
- 第一个 URB：`cursor = (MFI + lead) & 0x7ff`。
- 后续 URB：`start = cursor`，`cursor = (cursor + 16) & 0x7ff`。
- 提交前检查 `(cursor - (MFI + lead)) & 0x7ff` 不超过窗口；落后则丢帧/欠载，不重排。
- 每 URB 的 16 个 TD 用独立 Event Data tag；完成账本区分 URB，未完成不复用。

## 模型结果（10s，1ms 步进）

| 方案 | posts | underrun | overrun | late | max gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| cursor + 3 URB | 625 | 0 | 0 | 0 | 0 |
| A23 公式 + 3 URB、每 16ms 提交 | 625 | 0 | 0 | 0 | 0 |
| A23 单 URB / 等完成 | 209 | 0 | 1215488 | 0 | 32ms |
| cursor，源暂停 200ms | 625 | 38400 | 0 | 0 | 0 |
| cursor，poster 停 20ms | 625 | 0 | 0 | 13ms | 0 |

A23 单 URB 每 48ms 只送 16ms 数据（33%），ring 溢出 1.2MB；这是结构性欠供。
**3 URB + 现有 `MFI+32` 公式在名义速率下已经连续**，不需要改 FrameID。

> **2026-10-27 硬件否决：** 3 URB 方案在第二次/第三次 `PostBufferAsync` 返回
> `0xf601`，随后 usb 模块 `svcBreak`、Atmosphere fatal。该 endpoint 一次只接受一个
> pending URB；上表的 3-URB 行只是理想模型，不可部署。详见
> [A23_STREAM_CRASH.md](A23_STREAM_CRASH.md)。

## 3 URB 已否决，下一步是单 URB 长传输

硬件结果：第二个 pending `PostBufferAsync` 返回 `0xf601`，随后 usb assert。不要再
尝试 3 URB。可行方向：

1. **单个长 URB**：把 TD 数从 16 增到 64–128（64–128ms），把 32ms lead 空档摊薄；
2. **降低 lead**：4ms/1ms 变体，接受完成-重提之间的短空档；
3. **改 usb:ds/producer**：允许排队 URB 或真正 ring（大改，需重新验证）。

游标只有在“允许提前提交下一个 URB”时才有意义；单 URB API 下它不能消除空档：

1. 在端点上下文保存 `next_frame`（当前 A23 没有）。
2. `iso_enter` 的首 TD FrameID 取 `next_frame`，不再取 `MFI+32`。
3. 每个 TD 推进 `next_frame`；16 个 TD 后写回上下文。
4. 处理 ring wrap/cycle（沿用 A23 的 Link TRB/cycle 逻辑）。
5. 保留 SIA=0 和现有 ED tag/完成路径；不改 alt1/NOP hook。
6. cave 预算：A23 injection 684B 已满；游标代码需要压缩或复用保留字段，先做离线
   disassembly/Unicorn 验证，再进硬件。

## 时钟与同步

- 第一版按 48kHz 名义速率；host 侧 `snd-usb-audio` capture 异步，应用可重采样。
- ring 占用作为漂移指标；持续偏高/偏低时再设计 feedback 或丢/插样本。
- 不在第一版声称 clock lock 或零 xrun。

## 验收

| 阶段 | 条件 |
| --- | --- |
| 离线模型 | cursor 无重叠；名义 10s 无欠载；源暂停时如实报欠载 |
| 汇编 | Unicorn/反汇编验证 FrameID 单调、ring wrap、完成 tag |
| vendor PCM burst | 一次 URB 发送真实 grc:d 数据，host 收到 16×192 |
| UAC 枚举 | macOS `AppleUSBAudio` 出现输入设备，alt1 可选 |
| 连续 | Linux `arecord` 10s：0 xrun、包连续、无 4ms 空档 |

## 分阶段

1. **本轮**：Python 调度/ring 模型与测试（[model_uac_pcm_ring.py](../tools/model_uac_pcm_ring.py)）。
2. **3 URB 验证（已失败）**：第二次 post `0xf601`，usb `svcBreak`；不再重试。
3. **单 URB 长传输/低 lead**：离线设计 + disassembly/Unicorn，先做 64 TD 的构造与
   完成账本；再决定是否上硬件。
4. 用 vendor ISO alt1 发送真实 PCM burst。
5. 接 AC/AS alt1 + macOS 枚举。
6. Linux 10s 连续验收；再收窄全局 NOP、评估 feedback。

## 不证明

- 当前模型不是 USB/线程实现；不证明 xHCI 时序、SDK 提交、缓冲交还或 host 行为。
- A23 burst 的 16/16 通过不证明连续流；4ms 空档与帧重叠是设计约束，不是已实测故障。

# A23 per-URB mailbox 设计（2026-10-28）

## 现状

`iso_enter` 每次提交都重置同一个 mailbox：

```
x5 = ring_context + 0xf80
magic / terminal / bitmap / actual / first 都在这里
```

`iso_event` 用同一个 `x5` 和 `first` 做地址/奇偶过滤；没有 URB ID。3 个 in-flight
时，只有最后一个 URB 的 16 个 ED 能匹配，前两个完成丢失（离线 replay 已证）。

## 最小 per-URB mailbox

生产版不需要诊断用的 error snapshot/first-control；把 mailbox 压到 0x20：

| offset | 内容 |
| --- | --- |
| +0x00 | magic |
| +0x04 | terminal |
| +0x08 | bitmap |
| +0x0c | actual |
| +0x10 | first TRB |
| +0x14 | consumer/first control（可选） |

3 个 mailbox × 0x20 = 0x60，能放进 ring 尾部 `0xf80..0xfe0`（现有 0x80）。

## 选择 mailbox 的索引

`iso_enter` 知道本次 URB 的起始 TRB 槽：

```
slot = (enqueue - ring_base) / 16
mailbox = 0xf80 + (slot / 32 % 3) * 0x20
```

`iso_event` 在地址过滤前可以拿到 event 的 TRB 虚拟地址，同样算出 `slot/32 % 3`，
选对应 mailbox，再做 first/parity 过滤。这样每个 URB 有独立的 bitmap/actual/first，
16 个 ED 只完成自己的 URB。

## 需要改的代码

1. `iso_enter`：
   - 不再写固定 `x5`，按本 URB 起始槽选 mailbox；
   - 写 magic/terminal/bitmap/actual/first；
   - 保留现有 TRB/ED 构造和 doorbell。
2. `iso_event`：
   - 先从 event 指针算槽/mailbox，再 unwrap/奇偶过滤；
   - 只更新该 mailbox 的 bitmap/actual；
   - 该 mailbox 的 16 ED 完成后调用一次 `complete_original`。
3. 删除诊断用的 error snapshot/context 日志（生产版不需要），腾出 cave 空间。
4. cave 预算：A23 injection 684B 已满；必须压缩/删除诊断代码，或找新的 RX
   cave。当前 `.text` 只有 20B 对齐 padding，没有第二块 684B。**这是主要风险。**

## 备选：one-in-flight

已构建 `iso-stream-serial640.nsp`（`c129dce7…`）：一次一个 URB、640 个不同 buffer，
预期 208 轮/~3328 有效包、无 fatal。见 [A23_SERIAL_BASELINE.md](A23_SERIAL_BASELINE.md)。

不改 mailbox，直接串行：

- 每 48ms 一个 URB：16ms 数据 + 32ms 空档（33%）；
- 640 个 buffer、每个只用一次，可以跑 10s/208 个 URB，不会触碰 8 项 URB 表；
- 验证 A23 完成/释放能否在长串行下稳定；
- 不是连续 PCM，但可以作为 UAC 枚举/短音频的稳定基线。

## 建议顺序

1. **one-in-flight 长串行**：先证明 A23 完成/释放/URB 表在 208 轮下不崩；
2. **per-URB mailbox**：如果 cave 能腾出空间，做 3-mailbox 生产版；
3. 若 cave 放不下，认命 one-in-flight 或换 producer/usb:ds 方案。

## 实现草案

具体指令/地址/字节预算见
[A23_PER_URB_IMPLEMENTATION.md](A23_PER_URB_IMPLEMENTATION.md)。

## 验收

- 3 mailbox、3 in-flight：每个 URB 恰好一次 `complete_original`，bitmap/actual 互不
  串扰；
- URB 表 `entry+8` 在 3 个窗口后回到 0；
- 640 池/10s 无误；再谈 UAC 标准宿主。

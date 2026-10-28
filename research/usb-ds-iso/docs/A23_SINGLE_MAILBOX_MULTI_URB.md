# A23 单 mailbox 与多 URB in flight（2026-10-28）

## 代码事实

`iso_burst_patch.S` 的 `iso_enter` 每次提交都会重置同一个 mailbox：

```
add x5, x10, #0xf80          ; x10 = endpoint/ring context
mov w9, #0x5349
movk w9, #0x324f, lsl #16    ; ISO2
stp w9, wzr, [x5]
stp xzr, xzr, [x5, #8]
str x8, [x5, #24]
```

`iso_event` 用同一个 `x5` 做：

- `bitmap`/`actual` 累计；
- `terminal`；
- `first`/TRB 地址模 247 + TD 奇偶过滤；
- 16 个 ED 后才调用 `complete_original`。

关键：**没有 URB ID、序号或 per-URB generation**。`A23_REARM_GENERATIONS.md` 已经写明这一点，并记录了第 16 轮的地址别名反例。

## 离线 replay 已证实

`tests/test_mailbox_multiplex.py` 执行真实补丁：3 个 submit 都接受；注入 slot 0/32
的 16 个 ED 后 **没有** `complete_original`；只有 slot 64（最后一个）调用一次
`0x2a980`。也就是说，3 个 in-flight URB 只有最后一个会递减 `entry+8`。细节见
[A23_MAILBOX_REPLAY.md](A23_MAILBOX_REPLAY.md)。

## 3 个 URB in flight 会发生什么

stream 每 16ms 提交一个 URB：

- URB0 提交，重置 mailbox；
- URB1 提交，**再次重置同一个 mailbox**；
- URB0 的 16 个 ED 事件可能在 URB1 重置之后才到；
- 这些事件会写进 URB1 的 bitmap/actual，可能让 URB1 提前 terminal，
  或让 URB0 的完成调用缺失/错位；
- `complete_original` 用 `entry+4` 选 URB；完成/计数/DMA unmap 就会漂移；
- 漂移到 `entry+8 == 8` 后，`FUN_0002c520` 的 busy 分支泄漏 DMA map，
  最终在 map 处 assert。

这能同时解释：

- 3 个 URB 的短 burst 有数据（TRB 数据路径本身对），但完成记账没有被验证；
- 640 个全新 buffer 仍在约 5 个 URB 后崩；
- 同 buffer 复用崩；
- 崩溃总是在 DMA map，而不是 host 数据路径。

## 之前“3 URB 成功”的边界

host 的 `posts=3/completes=3` 来自 `usbDsEndpoint_GetReportData`，**不是** A23 的
`complete_original` 调用计数。所以它只证明：

- alt1 端点、DMA 对齐、START 握手、3 个 URB 的 TRB 数据能到 host；
- 不证明 A23 的 mailbox/完成/URB 表在 3 个 in-flight 下是正确的。

## 结论

- A23 producer 的 mailbox 是 **per-endpoint 单实例**，`iso_enter` 每次重置；
  它只适合 one-at-a-time（A23 两轮离线就是串行）。
- 多 URB in flight 需要 **per-URB mailbox/ID/generation**，或者回到 one-in-flight
  并接受 16ms 数据 / 48ms 周期（33%，有 32ms 空档）。
- 连续 PCM 不能靠当前 A23 诊断 producer；需要新 producer，或者先做单 URB 串行
  的稳定非连续版本。

## 下一步

1. 离线 replay 3 个 in-flight 的 `iso_enter`/`iso_event` 序列，记录每个 `complete_original`
   调用对应的 URB 和 mailbox 状态，确认事件归属错误；
2. 新 producer 规格：每 URB 独立 mailbox/ID、提交/完成/释放一一对应、DMA unmap
   后再复用；
3. 在 1/2 有离线证据前，不再用 A23 多 URB 上硬件。

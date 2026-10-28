# A23 one-in-flight 串行基线（2026-10-28）

## 构建

`iso-stream-serial640.nsp`（SHA256 `c129dce7…`）：

- **一次只发一个 URB**，完成后才发下一个；
- 640 个不同、各自 4K 对齐的 buffer，每个只用一次；
- 16ms 定时，但实际周期约 48ms（32ms lead + 16ms 数据）；
- host：`iso-stream --transfers 1 --packets 10000`（约 10s）。

## 预期

- 约 208 个 URB（10s / 48ms）；
- 每个 URB 16ms 数据 → host 约 **3328 个有效包**，其余为空窗；
- `posts≈208`、`completes≈208`、`errors=0`；
- URB 表 `entry+8` 始终 0/1，不触碰 8 项上限，不进入 busy-map 泄漏；
- 不应再出现 usb fatal。

这不是连续 PCM（33% 占空比），但能验证：

- A23 完成/释放/URB 表在 208 轮串行下是否稳定；
- 单 mailbox 在 one-at-a-time 下是否真的每个 URB 都能完成。

## 和 3-URB 的关系

3-URB in-flight 的 48 包数据路径已通过，但完成只发生一次（离线 replay）；
串行版把“完成/释放”单独拿出来验证，不依赖 in-flight 记账。

## per-URB mailbox 的 cave 预算

- A23 injection 684B 已满。
- 可删除的诊断：
  - `iso_report` 诊断 hook（约 0x4c）；
  - `iso_event` 的 error snapshot/MFI 上下文（约 0x40–0x60）；
- 需要新增：
  - mailbox 选择/索引（约 0x30）；
  - 每 URB 的 first/bitmap/actual 更新（现有代码改写）。
- 粗算净余 0x60–0x90；**可行但没有富余**，必须重新汇编并用 Unicorn 验证。
- 如果放不下，one-in-flight 是唯一稳定的 A23 路线。

## 下一步

1. 需要实机时先跑 serial640，确认 208 轮串行不崩；
2. 之后再做 per-URB mailbox 的汇编压缩；两者都通过才谈 UAC 连续流。

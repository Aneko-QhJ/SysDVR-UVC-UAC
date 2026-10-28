# A23 buffer recycle / DMA unmap（2026-10-28）

## 正常完成路径

A23 事件 terminal：

```
iso_event -> FUN_0002a980(manager, 0x83, 0, 1, 3072, 1)
          -> FUN_0002c690(entry, 0, 1, 3072, 1)
```

`FUN_0002c690` 在 `LAB_0002c7b4`：

```
if ([URB + 0x20] != 0)
    FUN_00004c70(FUN_000030c0(entry + 0x60), [URB + 0x10]);
```

`FUN_00004c70` 是 IOVA/DMA unmap；`FUN_00003c50` 的 map 失败路径也会调用
`FUN_000040e0` 释放。所以**正常完成确实会 unmap URB 的 DMA 缓冲**——但前提是完成
选中的是**正确的 URB 条目**。

## 为什么复用仍然崩

- 完成函数用 `entry + 4`（当前 URB 下标）和 `entry + 8`（在飞计数）选
  `URB = entry + 0x78 + index*0x30`，再 unmap `[URB+0x10]`。
- A23 producer 绕过了正常提交的记账；事件完成时 `entry+4/+8` 和实际 buffer 的
  URB 可能不对齐，unmap 命中的不是刚完成的 buffer。
- 第二次 map 同一个虚拟地址时，`FUN_00003c50` 仍看到旧映射/重复映射，走到
  `svcBreak`；栈里的 `+0x2c584` 就是 map 之后的返回地址。
- A23 两轮离线验证明确用**新的 DMA 地址**；3 个不同 buffer 成功、同 buffer 复用
  失败，和这个解释一致。

## 结论

- 不是“DMA map 本身不能复用”，而是 **A23 完成路径没有可靠地 unmap 这个 buffer**。
- 连续 PCM 需要：
  1. **每 URB 新 buffer**（安全，但有限时长）；
  2. 让 A23 完成/事件正确对齐 `entry+4/+8`，或显式 unmap 该 buffer（producer 补丁，
     需离线/Unicorn）；
  3. 改 usb:ds/endpoint 的 DMA 生命周期（大改）。

## 有限缓冲池方案

先不碰 DMA recycle，用**每 URB 一个新 buffer**做有限时长验证：

- 640 × 4 KiB = 2.5 MiB，625 个 16 ms URB ≈ 10 s；
- 每个 buffer 4K 对齐、只映射一次；
- host 窗口 625–640 包、12 s 超时；
- 先验证 10 s 连续 fresh-buffer 流，再接 UAC AC/AS alt1 和标准宿主；
- 这仍不是产品级连续流；真正的无限流需要上面的 2 或 3。

## 640-buffer 池实测：仍然崩（2026-10-28 14:15）

NSP `dbab0a68…`：640 个各自 4K 对齐、每个只用一次；host 10000 包窗口。

- host：`packets=80`（5 个 URB）、`bad=0`、`zero=9920`、exit 0；
- 设备：b0/b1/b2 post/complete 成功；之后没到 640，usb 在 DMA map
  `+0x2c584` 再次 `svcBreak`，签名与复用崩溃相同；
- 结论：**新缓冲并不能解决持续流**。限制不在“复用同一个 buffer”，而在 A23
  producer 的 URB/ring 完成/再提交状态；大约 5 个 URB 后就走坏。

## 下一步

1. 离线确认 `entry+4/+8`、endpoint URB 表（8 项）和 A23 完成调用的释放路径；
2. 需要新的 producer / URB 记账修正，不能只靠 640 池；汇总见
   [A23_SUSTAINED_STREAM_LIMIT.md](A23_SUSTAINED_STREAM_LIMIT.md)；
3. UAC 10s 标准宿主在当前 A23 诊断 producer 上不可达；3-URB 一次成功只证明
   alt1 传输和短 burst，不证明持续流。

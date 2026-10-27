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

## 下一步

1. 离线确认 `entry+4/+8` 在 A23 事件完成时的实际值，及 `FUN_0002c690` 选中的 URB；
2. 设计 640-buffer 池（内存、URB 上限、ring wrap）并离线检查；
3. 有安全构建后再实机；不再直接复用 3-buffer。

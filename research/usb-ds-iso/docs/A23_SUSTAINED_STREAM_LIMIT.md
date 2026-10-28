# A23 持续流上限（2026-10-28）

## 实测阶梯

| 缓冲策略 | host 收到 | 设备 | 结果 |
| --- | ---: | --- | --- |
| 3 个不同、4K 对齐、各一次 | 48 包 | posts=3/completes=3/errors=0 | 通过 |
| 3 个缓冲，完成后复用 b0 | 16 包 | b0 复用 post `0xf601` | usb DMA map 崩 |
| 640 个不同、4K 对齐、各一次 | 80 包（5 URB） | b0/b1/b2 成功，之后崩 | usb DMA map 崩 |

640 池排除了“同 buffer 复用”这个解释：**每个 buffer 只映射一次，仍在约 5 个 URB 后崩**。

## 崩溃签名

```
usb 0100000000000006, fatal 0x4A2
PC = base+0x1927c (svc #0x26)
栈: +0x2c584 (FUN_0002c520 里 DMA map FUN_00003c50 之后)
    +0x2a3f4 -> +0x2a30c -> +0x2d49c
```

三次崩溃（22:45、00:23、14:15）签名一致，区别只是触发前跑了几轮。

## 已知的 URB 表

`FUN_0002c520` / `FUN_0002c690`：

- endpoint 对象 `+0`：producer/写下标；
- `+4`：consumer/读下标；
- `+8`：在飞 URB 计数；等于 8 返回 busy；
- `+0x78 + index*0x30`：8 个 URB 条目；
- 提交时先 `FUN_00003c50` DMA map，再入表；
- 完成时 `FUN_0002c690` 用 `+4` 选 URB，`FUN_00004c70` unmap `[URB+0x10]`，再 `+4=(+4+1)&7`、count--。

3 个 URB 在飞时，5 个 URB 恰好是“8 - 3”的边界；第 6 个提交在 DMA map 崩，和
“表/映射资源在 5 个之后走坏”一致。

## 三个候选解释（按可能性）

1. **A23 完成与 URB 表下标不对齐**：A23 事件完成调用 `FUN_0002a980` 时，`+4/+8`
   可能不是当前 URB；unmap 命中错误条目，旧映射/在飞计数漂移，第 6 次 map 时资源
   状态不一致。
2. **DMA/IOVA 资源耗尽**：完成 unmap 没真正释放前 5 个映射，第 6 次 `FUN_00003d40`
   分配失败并 assert。`FUN_00003c50` 的失败路径本身返回错误，assert 更可能来自
   IOVA 分配器。
3. **事件代际别名**：A23 只有每个 manager entry 一个 mailbox，没有 URB ID/代际；
   旧 ED 事件可能污染下一轮。不过离线文档记录的首个地址别名在第 16 轮，不是第 5，
   所以这条单独解释不了 5 的边界。

## 结论

- A23 是**诊断用 one-shot/短 burst producer**，不是持续流 producer。它的 mailbox、
  URB 记账和完成调用都不是为多轮循环设计的。
- 3 URB 成功只证明 alt1 端点、DMA 对齐、START 握手和短 burst 可用；**10 秒 PCM/
  标准 UAC 仍不可达**。
- 继续在 A23 上试池大小/复用没有意义；下一步要么修正 A23 完成与 URB 表的记账
  （离线 Unicorn 证明），要么写新的 producer。

## 下一步

1. 用 Unicorn 对 `FUN_0002c520`/`FUN_0002c690` 建 8 项 URB 表模型，注入 6 轮
   submit/complete，逐步记录 `+0/+4/+8`、URB `[+0x10]`、map/unmap，定位第 6 轮
   assert 的具体条件；
2. 若修正是局部记账，做最小 patch；否则设计新 producer：
   - 每 URB 明确 ID/代际；
   - 提交/完成/释放一一对应；
   - DMA unmap 后再复用或每 URB 新 buffer；
   - 不再依赖单 mailbox 的 terminal 位；
3. 在 1/2 有离线证据前，不再上硬件试持续流。

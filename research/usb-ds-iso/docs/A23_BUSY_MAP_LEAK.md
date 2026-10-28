# A23 busy-map leak / 8 项 URB 表（2026-10-28）

## `FUN_0002c520` 的顺序

从反编译和反汇编看，Normal producer 的顺序是：

```
if (param_5 != 0)
    uVar4 = FUN_00003c50(...);       // DMA map 先发生
if (map 失败) return error;
FUN_0000ba60(entry+4);               // 之后才 lock
if (entry[2] == 8) {                 // 在飞 URB 已满
    puVar5 = &LAB_00019c8c;          // busy sentinel
} else {
    ... 添 URB 表项、count++、producer++ ...
}
FUN_0000bab0(entry+4);
return puVar5 & 0xffffffff;
```

**busy 分支没有 unmap 刚映射的 `local_48`**。也就是说：

- 表满时，buffer 已经被 `FUN_00003c50` 映射/占用了一个 IOVA；
- 函数返回 busy（`0x19c8c`），但不把这次映射登记到 URB 表，也没有 `FUN_00004c70`/`FUN_000040e0` 释放；
- 下一次重试又 map 一次，再泄漏一次。

## 和实测的对应

- 3 个不同 URB：`entry+8=3`，从未到 8；没有 busy/泄漏；通过。
- 同 buffer 复用：第一次完成后的再次 map 在表/DMA 状态上出问题；崩溃。
- 640 个全新 buffer：如果 A23 的完成调用没有按 URB 递减 `entry+8`，post 到 8 个后表满；
  线程继续每 16ms 重试，每次 busy 都泄漏一个 IOVA；几次之后
  `FUN_00003d40`/`FUN_00003c50` 分配失败并 assert，正好是 DMA map 崩溃。
- host 只收到 80 包（5 个 URB）而设备可能已经 post 到 8 个：前几个有数据，后面的
  busy 重试只泄漏、不发送。

这比“buffer 复用”更吻合 640 池也崩的事实：**根因是完成没有释放 URB/表项，随后
busy 重试泄漏 DMA 映射**。

## 为什么 A23 完成没有释放

A23 的 terminal 完成调用是：

```
iso_event -> FUN_0002a980(manager, 0x83, 0, 1, 3072, 1)
          -> FUN_0002c690(entry, 0, 1, 3072, 1)
```

`FUN_0002c690` 只有在被调用时才 `entry+4` 消费、`entry+8--`、unmap
`[URB+0x10]`。如果 A23 的 16 个 ED/terminal 事件没有按每个 URB 完整到达，或者
完成调用没有发生，`entry+8` 只增不减，最终到 8。

这与 A23 文档里“单 mailbox、无 URB ID/代际、不能扩展成无界循环”的警告一致；
3 个 URB 的短 burst 不会暴露，8 个以上就会。

## 修法

1. **根因修**：让每个 URB 的完成调用/释放成立（A23 事件代际/URB 记账修正，或新
   producer）。这是连续流的前提。
2. **防崩修**：在 `FUN_0002c520` 的 busy 分支 unmap `local_48`（或把 count 检查
   移到 map 之前），这样 busy 不再泄漏，最多是 stall，不会把 usb 带崩。
3. **保守用法**：不要超过 3 个 URB 的短 burst；不要重试 busy。

## 下一步

- diag8 构建（`1f6f3de5…`）每次 post/complete 都写日志；下一次实机可以直接确认
  busy 是否在第 8 个 post 后开始、`errors` 是否持续增长。
- 离线：用 A23 事件 replay 确认 16 个 ED/terminal 是否每个 URB 都到达；若没有，
  新 producer 必须自己维护 URB ID/代际和完成释放，而不是复用单 mailbox。
- 在这个记账问题解决前，640 池/长流/标准 UAC 都不能作为通过结论。

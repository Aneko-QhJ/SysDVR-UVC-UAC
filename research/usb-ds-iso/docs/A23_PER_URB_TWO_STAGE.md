# A23 per-URB 两阶段 patch（2026-10-28）

## 问题

per-URB 作为 **boot-time 全局 hook** 安装时，UVC 初始化期间就会走到
`advance` x13=0；base A23 在 init 时不崩。说明 per-URB 的 enter/event selector
不能覆盖 init 的 producer/event 路径。

## 设计

分两阶段：

1. **Boot**：只装 base A23 + NOP（当前安全 `isoRuntimeEdits`），UVC init 走 base；
2. **Stream START**：host 发 `0x55` 时，在启动 stream 线程之前，用 dmnt 再应用一个
   **delta patch**，把 injection/report 换成 per-URB 版本。

这样 init 期间永远是 base A23 的单 mailbox；per-URB 只在真正开流后生效。

## Delta patch

两处编辑，长度与 base 对齐：

| 地址 | before | after |
| --- | --- | --- |
| `0x68d54` | base A23 injection 684B | per-URB 代码 672B + 12B 零填充 |
| `0x2cbe0` | base report branch（→ `0x68fb4`） | per-URB report branch（→ `0x68fec`） |

- injection 必须按 684B 重写；per-URB 的 `iso_end` 在 `0x68ff4`，尾部 12B 不再使用。
- report 只改分支目标；最小抑制仍在 per-URB 的 `iso_report`。
- hooks/NOP/descriptor 已在 boot 阶段装好，delta 不重复。

## NSP 侧

- `_logIsoTarget` 继续在 `UvcDeviceInitialize` 里应用 boot payload；
- 新增 `_applyStreamPatch()`：
  - 复用现有 `ldr:dmnt` + `isoApplyRuntimePatch`；
  - 只在 START 控制请求里调用一次；
  - 失败则 stall/不启动 stream；
- START 顺序：

```
host START(0x55)
  -> _applyStreamPatch()   // usb 模块暂停/写入/恢复
  -> _isoStartStream()
  -> ACK
```

- 停止/重连后 delta 仍在；不会回 base（重新 boot 才回 base）。

## 验证

1. **Unicorn**：用 base 作为 before、per-URB 作为 after 做一次 delta 应用，确认
   `isoApplyRuntimePatch` 的 before 校验和最终 3 个 mailbox；
2. **实机 init**：deploy 两阶段 NSP，只 boot，不 START；确认 `UvcDeviceInitialize`
   通过、设备枚举；
3. **perurb3**：START + 256 包；确认 3 个 URB 各自完成；
4. **reuse**：START + 10000 包；确认 3 缓冲循环 10s。

## 风险

- START 时 usb 模块可能不在完全 idle；dmnt attach/pause 的窗口要验证；
- delta 的 before 必须与 boot 后的实际字节一致；
- per-URB report branch 目标 `0x68fec` 依赖 672B 布局；padding 不能覆盖；
- 第一次 START 的 URB 可能在 patch 完成前被 host 提交；START 控制先 patch 再 ACK，
  主机在 ACK 前不会提交数据。
- 如果 START 时 patch 失败，必须 stall 而不是带病开流。

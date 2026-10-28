# A23 per-URB mailbox 汇编候选（2026-10-28）

## 第一次修复仍在 UVC init 崩溃

`iso-stream-perurb3-fixed.nsp`（`c4ead1e3…`）启动后：

```
ISO runtime patch result=0
UvcDeviceInitialize failed: 0xf601
usb Data Abort at 0xc
PC = base+0x68ea4 (advance)
LR = base+0x3089c (event hook)
X13 = 0
```

per-URB 版为了省空间删掉了 `iso_report`。但 A23 的 report hook 不只是诊断：
它**抑制**原 report 路径（只 copy 后跳 `report_epilogue`）。没有它，原 report 路径
在 UVC init 期间把自定义 producer 带进 `advance`，x13=0 崩溃。

## 修复

保留一个 **最小 report 抑制**（8B）：

```asm
iso_report:
    add x0, x19, #0x10
    b report_epilogue
```

- 与 A23 `report_done` 的收尾一致；不再 copy 诊断；
- report hook `0x2cbe0` 重新指向新的 `iso_report`（`0x68fec`）；
- 汇编 **672B / 684B**，余 12B；
- Unicorn 3 in-flight：slot 0/32/64 各一次 `0x2a980`，mailbox 65535/3072。

## fixed2 仍在 UVC init 崩（22:24）

`iso-stream-perurb3-fixed2.nsp`（`71ca5b1a…`）日志：

```
ISO runtime patch result=0 record=29
UvcDeviceInitialize failed: 0xf601
usb Data Abort at 0xc
PC = base+0x68ea4 (advance)
LR = base+0x3089c (event hook)
X10 = 0, X13 = 0
```

8B report 抑制没有解决问题。per-URB 的 enter/event selector 还是改变了 **init 时的
producer/event 路径**；base A23 在 init 时不崩。

结论：**per-URB patch 不能作为 boot-time 全局 hook 直接装**。它需要：

- 在 stream START 之前完全走 base A23 的固定 mailbox（dormant guard）；
- 或在 init 完成后才安装/启用 selector；
- 或者换一个不经过 init URB/event 的实现。

在这之前，per-URB 不再部署。

## 候选（不可部署）

| NSP | SHA256 | host | 预期 |
| --- | --- | --- | --- |
| `iso-stream-perurb3-fixed2.nsp` | `71ca5b1a…` | `--transfers 1 --packets 256` | 48 包，3/3/0，无 init fatal |
| `iso-stream-perurb-reuse-fixed2.nsp` | `d2ea7cc4…` | `--transfers 1 --packets 10000` | 3 缓冲循环 ~10s，约 9958 包 |

都在 `private/deployments/20261027-alt1-probe/builds/`，未部署。卡已恢复安全
`52069a44…`；卡上 staging 里的 fixed1 是崩溃版本，部署时要换 fixed2。

## 下一步

需要实机：

1. `perurb3-fixed2`（256 包）：先确认 `UvcDeviceInitialize` 能过、3 个 URB 各自完成；
2. `reuse-fixed2`（10000 包）：3 缓冲循环 10s、无 DMA map 崩。

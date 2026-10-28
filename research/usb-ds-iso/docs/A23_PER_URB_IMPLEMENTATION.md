# A23 per-URB mailbox 实现草案（2026-10-28）

## 目标

把单 mailbox 改成 3 个 0x20 的 mailbox，按 URB 起始槽 `slot/32 % 3` 选择；每个 URB
的 16 个 ED 只更新/完成自己的 mailbox。

当前 cave 684B 已满；本页给出具体指令/字节预算和必须删除的诊断代码。

## 当前地址

`inject.bin` 684B，cave `0x68d54..0x69000`：

| 地址 | 内容 |
| --- | --- |
| `0x68dbc` | `add x5, x10, #0xf80`（enter 固定 mailbox） |
| `0x68e64` | `str w9, [x5, #60]`（first control 诊断） |
| `0x68ebc` | `add x5, x5, #0xf80`（event 固定 mailbox） |
| `0x68f94` | `str w6, [x5, #4]`（error offset） |
| `0x68fac` | `str q0, [x5, #64]`（error event，超出 0x20） |
| `0x68fb4..0x69000` | `iso_report`（0x4c） |

## enter 选择

在 `0x68dbc` 用 8 条指令替换原来的 1 条：

```asm
sub  x9, x8, x10        ; x8 = enqueue/起始 TRB, x10 = ring base
lsr  x9, x9, #9         ; /512 = TRB slot/32
mov  w11, #3
udiv w12, w9, w11
msub w9, w12, w11, w9   ; slot/32 % 3
lsl  x9, x9, #5         ; *0x20
add  x5, x10, #0xf80
add  x5, x5, x9
```

`x9/x11/x12` 在这个点可用；FrameID/cycle 的 x11/x12 在 packet 循环里才赋值。

## event 选择

在 `0x68ebc` 之前用 9 条指令计算 event 的 absolute slot：

```asm
ldr  x11, [x1]          ; event 指针
sub  x11, x11, x5       ; x5 = ring context
lsr  x11, x11, #9       ; slot/32
mov  w12, #3
udiv w13, w11, w12
msub w11, w13, w12, w11 ; % 3
lsl  x11, x11, #5
add  x5, x5, #0xf80
add  x5, x5, x11
```

之后再走现有的 `[x5+24]` first、奇偶、bitmap/actual、terminal 逻辑；每个 mailbox
只完成自己的 URB。

## 必须删除/缩小

- `str w9, [x5, #60]` first control（4B）。
- `str q0, [x5, #64]` error event（4B；0x20 mailbox 放不下）。
- `iso_report` 整段（0x4c）和 `0x2cbe0` 的 report hook。
- error 块保留 +4/+8/+12 的最小状态即可；不再写 +0x3c/+0x40。

## 字节预算

- 删除：0x4c（report）+ 4 + 4 = 0x54 = 84B。
- 新增：enter 28B + event 32B = 60B。
- 净余：24B。**能放下，但没有余量**；汇编后必须重新核对 `0x68d54+len <= 0x69000`。

## 验证顺序

1. 新建 `patches/iso_burst_perurb.S`，只改上述三处，先汇编看长度；
2. 生成 per-URB manifest：injection、`0x30364`/`0x30898` hooks、descriptor 修正，
   **不**加 `0x2cbe0` report hook；
3. 用 Unicorn `Machine` 跑 3 个 in-flight：slot 0/32/64 各 16 个 ED，期望
   **3 次** `0x2a980`，每次 bitmap/actual 各自 65535/3072；
4. 再检查 `entry+8` 3 个窗口后回 0；
5. 之后才构建 NSP/运行时 payload；实机另需授权。

## 风险

- event 指针必须是可与 ring base 相减的地址；现有过滤器已经这样用，假定成立，
  但要用 Unicorn 的三个 mailbox 结果确认。
- 24B 余量很小；如果汇编超出，先删更多诊断（first control/error 上下文）。
- 3 个 mailbox 只覆盖 3 in-flight；4 个以上仍会别名。

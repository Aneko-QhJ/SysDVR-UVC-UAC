# A23 re-arm / 缓冲复用边界（2026-10-27）

## 先纠正 0xf601

`0xF601` 是 **`KernelError_SessionClosed`**：第二次/第三次 `PostBufferAsync` 时
usb 服务已经 fatal，客户端看到的是会话关闭，不是 endpoint busy。

## 崩溃栈

```
0x2d49c  FUN_0002d450  endpoint post
0x2a30c  FUN_0002a2e0  PostBufferAsync wrapper
0x2a3f4  FUN_0002a330  endpoint/entry dispatch
0x2c584  FUN_0002c520  Normal producer, return after DMA map FUN_00003c50
0x1927c  svc #0x26     svcBreak
```

- `0x2c584` 是 `FUN_0002c520` 调用 DMA map `FUN_00003c50` 后的返回地址；断点发生在
  DMA map 内部/其被调函数，不是 ring-full。
- 崩溃栈里**没有** A23 ISO producer `FUN_000302E0`；第二次提交在进入 A23 hook 之前
  就已经在 Normal producer 的 DMA map 崩了。

## A23 gate 本身是安全的

`iso_burst_patch.S` 的 gate：

```asm
ldp x8, x9, [x1, #0x18]
cmp x8, x9
b.ne reject_original
```

`reject_original` 的目标是 **0x30394**，原函数在这里：

```asm
0x30394: mov w0, #0x908c
0x30398: movk w0, #0x1, lsl #16   ; w0 = 0x1908c (busy)
0x3039c: ldp x29, x30, [sp], #16
0x303a0: ret
```

所以 gate 失败会**干净地返回 0x1908c**，不会把已修改的 ring 交给 original producer。
之前把 gate fallback 当成崩溃原因，是错的。

## 更可能的原因：0 长首 URB + 同缓冲复用

设备日志：

```
ISO stream try b=0 len=3072
ISO stream post rc=0x0 urb=387
ISO stream complete urb=387
ISO stream try b=0 len=3072
ISO stream post rc=0xf601 urb=0
ISO stream try b=0 len=3072
ISO stream post rc=0xf601 urb=0
```

- 线程三次都选 **b=0**，说明第一次 URB 很快就 complete，b0 被标回 free。
- host 在整个 100×16 包里收到 **0 字节**；第一次 URB 很可能在 host 开始 ISO 读之前
  就 0 长度完成（stream 在 `SET_INTERFACE(1)` 就启动，host 还在 sleep 100ms；
  A23 的 `MFI+32ms` 首 TD 在 host 读之前）。
- b0 没有换过，第二次提交把**同一个缓冲**再送进 `FUN_0002c520` 的 DMA map；
  这里就崩了。
- A23 的两轮离线验证明确使用**第二轮新的 DMA 地址**（见
  [A23_REARM_GENERATIONS.md](A23_REARM_GENERATIONS.md)）；同缓冲复用没有被验证过。

## 后续：3 URB 已验证（23:4x）

按“host 先提交 ISO read，再 START；b0/b1/b2 各自 4K 对齐、各用一次”的条件重跑：

```
ISO stream create rc=0x0
ISO stream start rc=0x0
ISO stream try b=0 / post rc=0x0 urb=387 / complete
ISO stream try b=1 / post rc=0x0 urb=403 / complete
ISO stream try b=2 / post rc=0x0 urb=419 / complete
ISO stream stop posts=3 completes=3 errors=0 attempts=3
```

Host：`iso-stream --transfers 1 --packets 256` → **48 valid packets, bad=0,
zero=208**。所以 **3 URB in flight 本身是可行的**；之前的崩溃是测试设置问题：

- 首 URB 在 host 读之前 0 长完成；
- b0 复用；
- b1/b2 没有 4K 对齐（`0xce8c`）。

## 现在仍未验证

- 完成后**复用同一个 DMA 缓冲**（第 4 次提交）是否安全；
- 连续多轮（>3 URB）的 ring/DMA 回收；
- 48ms 之后的持续供给。


## 下一步（先离线/构建，再实机）

1. **Host 握手**：stream 不要一 `SET_INTERFACE(1)` 就启动；等 host 把第一个 ISO
   transfer 提交后，再发 vendor START（A23 的 trigger 路径就是这个时序）。
2. **不同缓冲**：b0/b1/b2 各用一次，完成后不重复选；先验证 1 个 URB 有数据，
   再验证 2/3 个。
3. **DMA 释放/复用**：查 `complete_original` 是否 unmap；若没有，必须每 URB 用新
   DMA 缓冲，或找到安全 unmap 路径。
4. 只有 1 URB 有数据、且不同缓冲的 3 URB 不崩，才谈连续 ring。
5. 再次实机前需要新的明确授权；上次崩溃后卡上已恢复安全的一次性 NSP。

## 证据

- `private/runs/A-alt1-stream-crash-20261027/`（fatal/crash/log/NSP）
- 崩溃报告：usb `0100000000000006`，fatal `0x4A2`，PC `base+0x1927c`。

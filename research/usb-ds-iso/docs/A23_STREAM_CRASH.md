# 3-URB stream crash（2026-10-27）

## 结果

`ISO_PROBE_STREAM` 的 3 缓冲、每 16ms 提交一次实验：

- 第 1 次 `PostBufferAsync`：`rc=0x0`、`urb=387`，随后完成 `urb=387`。
- 第 2 次：`rc=0xf601`、`urb=0`。
- 第 3 次：`rc=0xf601`、`urb=0`。
- 之后 **usb 模块 User Break**，Atmosphere fatal。

崩溃报告：

```
Program ID: 0100000000000006  usb
Fatal Result: 0x4A2 (2162-0002)
Crash: User Break at base+0x19280
PC: base+0x1927c  (svc #0x26, svcBreak)
LR: base+0x9668
```

NSP 日志（`logfile.txt`，1.5KB）：

```
ISO stream create rc=0x0
ISO stream start rc=0x0
ISO stream try b=0 len=3072
ISO stream post rc=0x0 urb=387
ISO stream complete urb=387
ISO stream try b=0 len=3072
ISO stream post rc=0xf601 urb=0
ISO stream try b=0 len=3072
ISO stream post rc=0xf601 urb=0
```

没有 `ISO stream stop`，因为崩溃的是 usb 模块（`0100000000000006`），不是
SysDVR NSP；Atmosphere 随即 fatal。

> 更正：`0xf601` 是 **`KernelError_SessionClosed`**，即第二次/第三次 IPC 调用时
> usb 服务已经 fatal，不是 endpoint 返回 busy。第二次提交本身触发了 usb 的 assert；
> 崩溃栈走 `FUN_0002d450 -> FUN_0002a2e0 -> FUN_0002a330 -> FUN_0002c520`
> （Normal producer），没有走 A23 ISO hook。详见
> [A23_REARM_BOUNDARY.md](A23_REARM_BOUNDARY.md)。

## 结论

- 第二次提交进入 usb 后，在 Normal producer `FUN_0002c520` 里调用 DMA map
  `FUN_00003c50`（返回地址 `0x2c584`）时触发 `svcBreak`；客户端看到 `0xf601`
  只是 usb 服务已经死掉后的 session closed。
- A23 `iso_enter` 的 `x8 != x9` gate 目标是 **0x30394**，那里直接返回 `0x1908c`
  （busy），是安全路径；它**不是**这次崩溃的原因。
- 日志三次都是 `b=0`：首 URB 很快 0 长完成，b0 被释放后又复用。A23 的两轮离线验证
  用的是**第二轮新的 DMA 地址**；同缓冲复用没验证过。第二次提交在 DMA map 崩。
- 这次实验**没有真正测到 3 URB in flight**，因此不能据此宣称 3 URB 不可用；3 URB
  仍未验证。已确认的是：**同缓冲在 A23 完成后不能直接复用**。
- 这个 NSP 是危险构建，已归档，不再部署。

## 对连续 PCM 的影响

- 先做 **host 握手**：host 提交首个 ISO read 后再发 START，避免首 URB 在 host 读之前
  0 长完成。
- 再用 **b0/b1/b2 各一次**（不重复选），先验证 1 个 URB 有数据，再验证 2/3 个。
- 查 `complete_original` 是否真正 unmap DMA；若没有，需要每 URB 新缓冲或安全 unmap。
- 3 URB / 长 URB / 连续 ring 仍未验证；这次崩溃不是 3-URB 的否决证据。

## 证据

`research/usb-ds-iso/private/runs/A-alt1-stream-crash-20261027/`：

- `fatal.log`（SHA256 `5b7992de…`）
- `crash.log`（`4d62b2bb…`）
- `logfile.txt`（`1873fffd…`）
- `iso-stream-v3.nsp`（`3468fad4…`，危险，仅归档）

源码 diff 存档：
`private/analysis/alt1-stream-rejected-20261027/uvc_device.stream.patch`。
`source/uvc/uvc_device.c` 已回到一次性 ISO alt1 版本；stream 代码不再留在主树。

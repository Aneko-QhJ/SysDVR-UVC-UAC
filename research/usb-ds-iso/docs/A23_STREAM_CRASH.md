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

## 结论

- **该 `usb:ds` endpoint 一次只接受一个 pending URB。** 第二次
  `PostBufferAsync` 被拒绝，返回 `0xf601`。
- 第二次/第三次失败后的路径（或我们的重试）触发了 usb 模块的 `svcBreak`，这是
  usb:ds 的主动 assert，不是随机访存异常。
- **3 URB in flight 不可用。** [UAC_PCM_PRODUCER.md](UAC_PCM_PRODUCER.md) 里
  3-URB timed 的 625/0 只是理想模型，硬件不接受。
- `0xf601` 的具体 Result 名称未确认；只能确定它是第二次 pending post 的拒绝，
  不应据此推断更多。
- 这个 NSP 是危险构建，已归档，不再部署。

## 对连续 PCM 的影响

- cursor/游标解决不了“单 URB”限制：下一个 URB 只能在完成后再提交；A23 的
  `MFI+32ms` 会留下 32ms 空档。
- 可选方向：
  1. **单个长 URB**（例如 64–128 个 TD）把 32ms 空档摊薄；
  2. 降低 lead（4ms/1ms）并接受更小的完成-重提空档；
  3. 改 usb:ds/producer 支持排队 URB 或真正的 ring（大改，需重新验证）。
- 在离线验证/新 producer 之前，不再上硬件试 3 URB。

## 证据

`research/usb-ds-iso/private/runs/A-alt1-stream-crash-20261027/`：

- `fatal.log`（SHA256 `5b7992de…`）
- `crash.log`（`4d62b2bb…`）
- `logfile.txt`（`1873fffd…`）
- `iso-stream-v3.nsp`（`3468fad4…`，危险，仅归档）

源码 diff 存档：
`private/analysis/alt1-stream-rejected-20261027/uvc_device.stream.patch`。
`source/uvc/uvc_device.c` 已回到一次性 ISO alt1 版本；stream 代码不再留在主树。

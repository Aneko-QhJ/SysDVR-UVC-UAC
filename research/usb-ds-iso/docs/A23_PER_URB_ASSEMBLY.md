# A23 per-URB mailbox 汇编候选（2026-10-28）

## 源码与大小

[patches/iso_burst_perurb.S](../patches/iso_burst_perurb.S)：

- enter：`slot=(enqueue-ring_base)/16`，`idx=slot/32%3`，选 `ring+0xf80+idx*0x20`；
- event：event 指针算同一个 idx，再走现有 first/parity/bitmap/actual；
- 删除 `iso_report`、first-control、error snapshot；
- 汇编结果 **656B / 684B**，余 **28B**。

## 离线验证

用 `/tmp/a23-burst` 的 manifest 替换 injection、去掉 `0x2cbe0` report hook，
生成临时 per-URB 包；Unicorn `Machine` 3 个 in-flight：

```
submit 0/32/64 都 rc=0
slot 0  -> 0x2a980
slot 32 -> 0x2a980
slot 64 -> 0x2a980
每个 mailbox: magic=ISO2, terminal=1, bitmap=0xffff, actual=3072
```

也就是说，3 个 URB 各自完成一次，不再只有最后一个。

## 候选 NSP

| NSP | SHA256 | host | 预期 |
| --- | --- | --- | --- |
| `iso-stream-perurb3.nsp` | `a736ca70…` | `--transfers 1 --packets 256` | 48 包，posts=3/completes=3/errors=0 |
| `iso-stream-perurb-reuse.nsp` | `84b58635…` | `--transfers 1 --packets 10000` | 3 缓冲循环 ~10s，约 9958 包，无 fatal |

两个都未部署，归档在
`private/deployments/20261027-alt1-probe/builds/`。

## 风险

- event 指针必须是可与 ring base 相减的地址；现有过滤器已经这样用，但实机要确认。
- report hook 已移除；stream host 不读 A23 report，正常 `GetReportData` 仍走原路径。
- 3 个 mailbox 只覆盖 3 in-flight；4 个以上仍会别名。
- reuse 版依赖 per-URB 完成后的 DMA unmap 真正发生；这是实机第一要看的点。

## 下一步

需要实机测试：

1. 先 `perurb3`（256 包窗口）：确认 3 个公完成、48 包、无 fatal；
2. 再 `perurb-reuse`（10000 包窗口）：确认 10s/3 缓冲循环、无 DMA map 崩溃。

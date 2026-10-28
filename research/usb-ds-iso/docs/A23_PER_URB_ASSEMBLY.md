# A23 per-URB mailbox 汇编候选（2026-10-28）

## 第一次实机崩溃与修复

`iso-stream-perurb3.nsp`（`a736ca70…`）在启动后崩溃：

```
usb Data Abort at 0xc
PC = base+0x68ea4  (advance: str w9,[x13,#12])
X13 = 0, X10 = 0
LR = base+0x3089c  (event hook return)
```

原因：event mailbox 选择用了 **x11/x12/x13**，其中 x13 是原事件路径仍在使用的
ring 结束指针；hook 返回后 original 代码用 x13=0 进入 `advance`，写 `[x13,#12]`
崩溃。

第一次修复用 x9/x10 做除法，但 x10 是 entry 指针、x9 是 manager 指针，导致 3 个
URB 全都不完成；Unicorn 立即暴露。

最终：

- 只保存/恢复 **x11**；
- 除法临时用 **x6/x7**（原代码在后续才重新赋值）；
- 不碰 x9/x10/x12/x13；
- 汇编 **664B / 684B**，余 20B。

## 离线验证

Unicorn 3 in-flight：

```
submit 0/32/64 rc=0
slot 0/32/64 各一次 0x2a980
每个 mailbox: magic=ISO2, terminal=1, bitmap=0xffff, actual=3072
```

## 修复后的候选

| NSP | SHA256 | host | 预期 |
| --- | --- | --- | --- |
| `iso-stream-perurb3-fixed.nsp` | `c4ead1e3…` | `--transfers 1 --packets 256` | 48 包，3/3/0 |
| `iso-stream-perurb-reuse-fixed.nsp` | `91fc5290…` | `--transfers 1 --packets 10000` | 3 缓冲循环 ~10s，约 9958 包 |

两个都在 `private/deployments/20261027-alt1-probe/builds/`，未部署。卡已恢复安全
`52069a44…`；旧 staging 里的 perurb3/reuse 是崩溃版本，部署时要换成 `-fixed`。

## 下一步

需要实机测试：

1. `perurb3-fixed`（256 包）：3 个 URB 各自完成、48 包、无 fatal；
2. `perurb-reuse-fixed`（10000 包）：3 缓冲循环 10s、per-URB unmap 后复用不再崩。

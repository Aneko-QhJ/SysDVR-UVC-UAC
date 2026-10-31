# UAC U2：第 2 个 burst 的 ring/dequeue 复位（v16 r2 → v18 实机）

> 状态：**v17 否掉 ring 位置，v18 否掉事件掩码**。v18 实机显示
> `mask=0x00000000 bit9=0 ep10=0x00` 始终成立（doorbell 路径不检查掩码），
> 而 seq2 的 TD 在 cons 处结构有效。新焦点：完成码 0xdb/0xde 时 driver 的
> `event_original` 会做门铃确认（`0x30ff4` 轮询 `regs+0x78` 再写
> `regs+0x5C/0x78`），cave 跳过它。下一步 v19 先在 cave 记录事件完成码。
> 下一次上机需要新的明确授权。当前事实以 [CURRENT.md](CURRENT.md) 为准；
> v15/v16 的过程见 [UAC_U2_CONTINUOUS.md](UAC_U2_CONTINUOUS.md)。

## 结论（一句话）

v16 r2 证明 cave 为第 2 个请求**写了完整 TD**，但驱动在完成时把
`prod/cons/copy` 复位回 ring base（`done` 行），而控制器已经消费了
0x200 字节、dequeue 停在 base+0x200。第 2 套 TD 写在 base，落在控制器
dequeue 之后，永远不被取指——host 只看到 transaction error。

## 证据

### 设备侧（v16 r2，`private/runs/UAC-u2-v16-submit-state-r2`）

```text
seq=1 pre   prod=cons=ring          empty=1
seq=1 post  prod=ring+0x200         box ISO2, trb0 ctl=0x64e01411 (frame 0x64E)
seq=1 done  prod=cons=ring          copy 回 0x…dff0       ← 驱动复位
seq=1 report/complete 3072/3072 status=3
seq=2 pre   prod=cons=ring          empty=1
seq=2 post  prod=ring+0x200         box ISO2, trb0 ctl=0x72801411 (frame 0x728)
seq=2       100 ms 无 completion → cancel=0
```

- 两次 `post` 都有 `ISO2` box 和推进的 prod，说明 `iso_enter` **接受并写了**
  16 Isoch + 16 ED TRB；cave 的 `prod == cons` 门不是原因。
- `done` 行在 `GetReportData`/`ParseReportData` 之后读取：prod、cons 都被
  复位到 ring base，copy 从 `ring+0xf70` 回到 `ring+0xff0`（驱动自己的
  ring 末端槽）。这是驱动完成路径的清理，不是 cave 写的（cave 只把
  `cons = prod`，即 ring+0x200）。
- 一个 TD 集 = 16 Isoch + 16 ED = 32 × 16B = **0x200**。控制器消费完第 1 套
  后，dequeue 在 base+0x200。

### doorbell 不是原因

`doorbell_tail`（usb.elf `0x31c74`）在检查通过后写 `regs+4 = dci << 8`
（0x31cd8/0x31cdc）；检查失败时返回 `0x1928c`。`PostBufferAsync` 的返回值
会经 `0x2c664`（`blr x8`）→ `0x2c668`（`mov w20,w0`）原样带回 app，而两次
post 都是 `rc=0x0`，所以**doorbell 确实响了**，不是被门铃检查拦下。

补充：`doorbell_tail` 里的掩码 `[manager+0x22A5C]` 的置位/清位代码
（`0x31324`/`0x311a8`）位于 `event_original`（`0x30f70`）内部；U2 cave 对
DCI 9 的 transfer event 直接处理、不调用 `event_original`，所以该掩码不
会因 UAC 事件被设置。这与“doorbell 返回 0”一致。

### 与 A23 的差异（待验证）

A23 的持续流（3 缓冲循环，约 9958 包）在同一套 driver/cave 结构上跑通。
一个可能的差别是：A23 持续提交时**环里始终有另一个 URB**（prod != cons），
驱动的“环空复位”路径没有被触发；而 v15/v16 是严格的 one-at-a-time，每个
burst 之间环都会空一次，于是每次都回到 base。A23 的 per-URB cave 还按
TRB slot 选择 mailbox，天然支持 2-3 个 in-flight。

这条差异是 v17 之后若要做的“pipelining + per-URB cave”方向的依据；本轮先
用更小的 v17 诊断验证“dequeue 位置”这一层。

## v17 诊断（已构建，未实机）

- 开关：`-DUAC_U2_RING_ADVANCE`（与 `-DUAC_U2_BURSTS=4` 一起）。
- 行为：在 post burst 2..N 之前，用 dmnt 把端点的 `prod` 和 `cons` **同时**
  写成 `ring + (seq-1)*0x200`，让 cave 的第 2 套 TD 正好落在控制器 dequeue
  的位置；写入前后各有一条 `UAC U2 state pre` 日志。
- 只写 cave 在提交时本来就会写的同一组字段；4 个 burst 最多到 base+0x600，
  还没碰到 `ring+0xf70` 的 Link/回卷，不涉及 cycle 翻转。
- 构建：`ef1e63c0…`（92472B），cave 仍 `806f54cb…` / 592B，与 v14 逐字节
  相同。工作目录 `private/analysis/UAC-u2-v17-ring-advance-20261101`。

### 一次 boot 怎么读

| 观察 | 结论 |
| --- | --- |
| `ring advance seq=2 … to=ring+0x200`，随后 `post` 的 trb0 在 base+0x200，host 收到第 2 个 3072B、设备 seq2 `complete 3072/3` | **dequeue 假设成立**；接着做 cave 内自维护/流水线版本 |
| `advance` 成功但 seq2 仍无 completion | 不是 dequeue 位置；回到驱动复位/控制器状态分析 |
| `advance` 返回非 0 或设备 crash/fatal | 停止，不重试；读卡取 crash 报告 |

停止条件与以往相同：任一次失败即停，读卡、恢复 `52069a44…`、不重试。

## 2026-11-01 02:10 v17 实机：位置假设被否

host：`urb[2] 192B` + `urb[3] 2880B` = 3072B，之后全 bad；
`valid=57 bad=935 bytes=3072`，`cancel remaining=8/64`；设备全程在线。

设备日志（`private/runs/UAC-u2-v17-ring-advance-20261101`）：

```text
ring advance seq=2 slots=1 from=0x…d000 to=0x…d200 rc=0x0     ← 写入成功
seq=2 pre   prod=cons=0x…d200 empty=1
seq=2 post  prod=0x…d400 cons=0x…d200 box ISO2 copy=0x…df70   ← TD 写到了 +0x200
trb0 dump(base) 全 0（符合预期，TD 在 +0x200）
seq=2       100 ms 无 completion → cancel=0
train end posted=2 completed=1
```

结论：**cave 把第 2 套 TD 正好写在了控制器 dequeue 的下一槽，仍然没有被
取指**。ring 位置不是阻塞点。

新的首要假设：**cave 对 DCI 9 的 transfer event 直接处理、不调用
`event_original`，跳过了 driver 的事件确认/端点重启**，所以控制器在第一次
完成之后不再服务新的 TD 集。相关静态位置：

- `[manager+0x22A5C]`（模块 `0xFCA5C`）是按 DCI 的 pending 掩码；
  `0x31324` 置位、`0x311a8` 清位并轮询 `regs+0x78`，两处都在
  `event_original`（`0x30f70`）内部。
- `doorbell_tail` 只有在 `[endpoint+0x0A] & 0x1f != 0` 时才检查该掩码；
  UAC 端点这个字节的值未知。
- `event_original` 的完成处理还会写 event ring/EPRD（`0x308e0` 之后由事件
  环消费者统一做），这部分 cave 没有跳过。

## v18 仪器化（已离线构建，0 实机，需新授权）

只改 app、不动 payload，在 v16 的状态日志上补三项：

1. 读 `[module+0xFCA5C]` 的 pending 掩码（普通内存，dmnt 可读），打印
   `mask=0x…` 与 `bit9`；
2. 读 endpoint 对象的 `+0x0A` 字节（决定 `doorbell_tail` 是否检查掩码），
   打印 `ep10=0x…`；
3. 每个 post 后在 **cons** 处 dump 前 32 字节（`UAC U2 td@cons`）——post 后
   cave 已把 prod 前进 0x200，TD 集从 cons 开始；固定读 ring base 会看到 0。

| 项 | 值 |
| --- | --- |
| 构建 | `35a67deb…`（91846B），`-DUAC_U2_BURSTS=4`（不带 RING_ADVANCE） |
| payload | 29 条 / cave `806f54cb…` / 592B，与 v14 逐字节相同 |
| 工作目录 | `private/analysis/UAC-u2-v18-event-mask-20261101` |

一次 boot 的判定：

| 观察 | 结论 | 下一步 |
| --- | --- | --- |
| seq2 `pre`/`post` 的 `bit9=1` | 确认“缺事件确认”：cave 没走 `event_original` 的清位路径 | 在 cave 的 `iso_event` 里复刻 `0x311c4..0x311f8`（清 bit9、轮询 `regs+0x78`、写门铃），再做一次有界验证 |
| `bit9=0` 且 `ep10 & 0x1f == 0` | 掩码检查不适用，doorbell 路径无条件响铃 | 转向控制器端点状态：查 ep10、事件环 consumer、端点 restart 相关字段 |
| `bit9=0` 但 `ep10 & 0x1f != 0` | 掩码被检查但未置位，问题在更早的 ring/端点状态 | 结合 `td@cons` 的 TRB 内容与 v14 成功值继续比对 |
| `td@cons` 的 trb0/trb1 与 v14 不同 | TD 内容本身有差异 | 按 IOVA/frame/cycle 逐项对照 |

停止条件与以往相同：任一次失败即停，读卡、恢复 `52069a44…`、不重试。

## 2026-11-01 02:2x v18 实机：掩码假设被否，焦点转向 doorbell ack

host：`urb[3] 1344B` + `urb[4] 1728B` = 3072B，之后全 bad；
`valid=81 bad=911 bytes=3072`，`cancel remaining=8/64`；设备在线。

设备日志（`private/runs/UAC-u2-v18-event-mask-20261101`）：

```text
state pre/post/done/timeout（全部）：mask=0x00000000 bit9=0 ep10=0x00
td@cons seq=1 trb0 addr=0x80030000 len=192 ctl=0x2b701411
td@cons seq=2 trb0 addr=0x80030000 len=192 ctl=0x33401411   ← 结构同 seq1，仅 frame 变
seq=2 100 ms 无 completion → cancel=0；train end posted=2 completed=1
日志最后 USB host disconnected；随后 usb fatal 2162-0002（PC 0x19254）
```

结论：

- **掩码假设被否**：`[manager+0x22A5C]` 从未置位；`ep10=0x00` 说明
  `doorbell_tail` 根本不检查它（`tst w10,#0x1f` 为 eq），门铃是无条件写
  寄存器。
- seq2 的 TD 内容有效：同一 IOVA、长度 192、cycle 1、frame 0x334（seq1
  0x2B7，差 125 frame ≈ 16 ms），与 v14 成功结构一致。
- 新假设：UAC 的 transfer event 完成码若是 **0xdb/0xde**，driver 的
  `event_original` 会走 `0x30ff4` 的门铃确认块（轮询 `regs+0x78` 的
  bit9，再写 `regs+0x5C`/`regs+0x78`）；cave 跳过它，控制器的 doorbell
  状态一直 pending，后续写入被忽略，TD 不再被取指。
- 本次 usb fatal 发生在 `USB host disconnected` 之后（teardown/关机），
  不是数据失败的原因；签名与已知 teardown fatal 相同。

## v19 计划（离线实现，需新授权）

1. **先确认完成码**：在 cave 的 `iso_event` 入口把 `[event+8] >> 24` 写到
   mailbox `ring+0xf84`（app 已能读 `box[1]`），一次 boot 看事件码；
2. 若为 0xdb/0xde，在 cave 里复刻 `0x30ff4` 的 ack（轮询
   `regs+0x78` bit9，再写 `regs+0x5C`/`regs+0x78`），保持单请求 pending；
3. 若完成码不是 0xdb/de，按 `event_original` 的对应分支（`0x31274` 等）
   重新定位；
4. 仍不重试：每次 candidate 只跑一次，失败即停。

## 风险

- 这是**跨进程写**（app 通过 dmnt 写 usb 模块的 ring 字段），写点与 cave
  提交时的写点相同，但发生在驱动空闲期；若假设错误，可能让后续请求状态
  异常（不排除 crash）。因此只跑一次、失败即停。
- 4 个 burst 仍是 64 ms，不构成持续音频；PCM/时钟/共存仍未测。
- 8 个 descriptor-parser NOP 的全局风险仍未隔离。

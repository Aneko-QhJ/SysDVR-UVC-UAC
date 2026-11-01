# UAC U2：第 2 个 burst 的 ring/dequeue 复位（v16 r2 → v19）

> 状态：**v17 否掉 ring 位置，v18 否掉事件掩码，v19/v20 否掉 per-ED 完成，
> v21 否掉 idle cancel，v22 否掉 alt 重装，v23 实机成功（4/4 burst）**。
> SET_INTERFACE(0)→(1) 并不会重新安装端点（install object/table 不变、
> installed 仍为 1），只有第一个 TD 集被取指。v23 结论：安装器 `0x295d0`
> 只遍历描述符；装点的是 `0x2fd30 → 0x2feb0`（写 64B 上下文 + `regs+0x58`
> commit + 清 halt），完成错误路径 `0x30ff4` 重写 ring/上下文却**不 commit**。
> 每 burst 重放 `0x2feb0` 后，host 收到 **12288B（4×3072）**，设备
> `posted=4 completed=4`、seq1..4 都 `complete 3072/3`，无 crash——
> 第一个 TD 集之后的墙被打破。详见
> [UAC_U2_ENDPOINT_CONTEXT.md](UAC_U2_ENDPOINT_CONTEXT.md)。
> v20 的 per-ED 完成对 seq1 正常（3072/3），但 `done` 仍然 prod=cons=ring、
> seq2 仍不被取指——per-ED 不是差异点。下一步 v21：在 burst 之间用
> `usbDsEndpoint_Cancel`（空闲时）复位端点，验证控制器 dequeue 是否随之
> 重启。
> v19 的 mailbox 完成码在 app 读取前被驱动清理（`event=0`）；cave 自己的接受
> 检查要求 `[event+8]>>24 == 1`，所以 0xdb/0xde 的 `0x30ff4` ack 不是我们的
> 分支。真正的差异在 driver 的 code-1 路径（`0x31230` → `0x31cf0`：每个 ED
> 调一次 complete_original，w4=192、force=0，并更新 cons）与 cave 的“累计后
> 一次完成（w4=3072、force=1、cons=prod）”之间。
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

## v19 事件完成码（已离线构建，0 实机，需新授权）

cave 只加 12 字节：在 `iso_event` 的邮箱指针建立后插入

```asm
ldr w6, [x1, #8]   /* 26 08 40 b9 */
lsr w6, w6, #24    /* c6 7c 18 53 */
str w6, [x5, #4]   /* a6 04 00 b9 */
```

把 transfer event 的完成码写进 mailbox `+4`；cave 每次 enter 会把 `+4` 清零，
所以 **seq2 若为 0 就说明根本没有事件到达**。app 侧同时修正了旧 box dump 的
错位（原先把 `+4/+8/+0xc` 当 completed/actual/first），现在读
`magic +0 / event +4 / done +0xc / completed +0x10 / actual +0x14 / first +0x18`，
并在 `eventWait` 之后、`GetReportData` 之前 dump 一次，保住 seq1 的最后一个
完成码。

| 项 | 值 |
| --- | --- |
| 构建 | `301f216d…`（91955B），cave `ffef1d7b…` / **604B**（+12，limit 684） |
| assembly | `patches/iso_burst_uac84_dci9_eventcode.S` |
| 工作目录 | `private/analysis/UAC-u2-v19-event-code-20261101` |
| 其余 | 29 条 edits、endpoint/DCI/完成参数与 v14 相同；其余 28 条 edit 不变 |

一次 boot 的判定：

| 观察 | 结论 | 下一步 |
| --- | --- | --- |
| seq1 完成后的 `event=0xdb` 或 `0xde` | 与 `0x30ff4` 的 ack 分支一致 | v20 在 cave 里复刻轮询 `regs+0x78` + 写 `regs+0x5C/0x78` |
| `event=0xdc` | 走的是清位/ack 分支（`0x311a8`），与之前测到的 `mask=0` 不符 | 重新核对事件码与掩码时序 |
| seq2 的 `event=0`（post 后 dump） | 第 2 个请求**完全没有事件**到达 | 问题在控制器/端点，不在事件处理 |
| 任意 crash/fatal | 停止 | 读卡取报告，不重试 |

停止条件与以往相同：一次 boot、失败即停、读卡恢复 `52069a44…`。

## 2026-11-01 02:4x v19 实机：完成码被驱动清掉

host：`urb[2] 1152B` + `urb[3] 1920B` = 3072B，之后全 bad；
`valid=57 bad=935 bytes=3072`；设备在线，无新 crash/fatal/erpt。

设备日志（`private/runs/UAC-u2-v19-event-code-20261101`）：

```text
post seq1 box: magic=ISO2 event=0 done=0 completed=0 actual=0 first=ring
eventWait 之后的 box: magic=0 event=0 done=0 completed=0 actual=0 first=0  ← 被驱动清掉
seq2 post box: magic=ISO2 event=0 …（无事件）；100 ms 无 completion → cancel
```

结论：

- v19 无法从 mailbox 观察完成码：**驱动在完成清理时把 mailbox 擦掉**，
  app 在 `eventWait` 之后读到全 0；cave 的写入本身发生过（否则 seq1 不会
  正常完成）。
- 从 cave 自己的接受检查反推：成功 ED 事件满足 `[event+8]>>24 == 1`，
  所以 `event_original` 的 **code-1 分支（`0x31230`）** 才是我们的路径，
  不是 0xdb/0xde 的 `0x30ff4` ack。
- driver 的 code-1 路径：`0x31238` 计算下一个 TRB 指针并写
  `cons = [endpoint+0x20]`（`0x31264 str x8,[x19,#32]`）→ `0x31cf0(event,
  endpoint)` → 对 ISO（`attrs&3 == 1`）调用
  `complete_original(w4 = transferred = 192, w3 = 0 force, w5 = 1)`：
  **每个 ED 完成一次**，由 driver 的 `entry+44` 累加到 3072。
- cave 的路径：自己累计 16 个 ED → 一次
  `complete_original(w4 = 3072, w3 = 1 force, w5 = 1)`，然后把 `cons = prod`。
- 差异：**per-ED 完成 + 逐事件更新 cons** vs **一次完成 + cons=prod**。
  前者可能让 driver 在每个 TD 上做正确的 entry/ring 清理，从而避免
  “完成后回 base”把第 2 套 TD 抛到控制器 dequeue 之后。

## v20 per-ED 完成（已离线构建，0 实机，需新授权）

按 driver 的 code-1 路径改写 cave 的事件处理（`patches/iso_burst_uac84_dci9_pered.S`）：

- 在 `virtual_tag` 保存绝对 TRB 地址（`mov x11, x6`）；
- 每个通过校验的 ED（code=1、len=192、奇槽、未完成过）执行：
  - `cons = TRB+0x10`；若当前 TRB 是 Link（`ctl & 0xfc00 == 0x1800`）则
    `cons = ring base`（`csel`），写入 `[context+0x20]`；
  - `complete_original(w4=192, w3=0 force, w5=1)`（`bl`），然后返回；
- 3072 的 bitmap/actual 只保留诊断用途：到达 3072 只置 done 标志，不再
  作为完成条件；**不再有单次 3072 的 `b complete_original`**。

| 项 | 值 |
| --- | --- |
| 构建 | `48b251ea…`（91960B），cave `0896c7bf…` / **640B**（limit 684） |
| assembly | `patches/iso_burst_uac84_dci9_pered.S` |
| 工作目录 | `private/analysis/UAC-u2-v20-per-ed-20261101` |

一次 boot 的判定：

| 观察 | 结论 |
| --- | --- |
| seq2 收到数据、设备 `complete 3072/3` | per-ED 完成修复了 ring/driver 清理；继续做 4-burst/连续性 |
| 仍无 seq2 数据，但 seq1 完成/日志正常 | per-ED 不是差异点；回到驱动清理路径（`0x2c7b4`）或控制器 halt |
| 任一 crash/fatal | 立即停；cave 的 per-ED 调用序列需要重新核对 |

停止条件与以往相同：一次 boot、失败即停、读卡恢复 `52069a44…`。

## 2026-11-01 03:0x v20 实机：per-ED 完成不影响复位

host：`urb[2] 576B` + `urb[3] 2496B` = 3072B，之后全 bad；
`valid=57 bad=935 bytes=3072`；无新 crash/fatal/erpt。

设备（`private/runs/UAC-u2-v20-per-ed-20261101`）：

```text
seq1 post  box ISO2, trb0 ctl=0x26a01411
eventWait 后 box 全 0
report 3072/3072 status=3；complete rc=0
done       prod=cons=ring        ← 仍然回 base（per-ED 没改变）
seq2 post  box ISO2, trb0 ctl=0x2fe01411 → 100 ms 无 completion → cancel
```

结论：**per-ED 完成对 seq1 正常工作，但不是差异点**——驱动的 ring 复位
（prod=cons=ring）和第 2 套 TD 不被取指的行为完全没变。也就是说，
“一次完成 vs 每 ED 完成”不影响复位；复位来自完成的清理路径
（`0x2c7b4` 附近）或端点/控制器状态本身。

## v21 idle cancel（已离线构建，0 实机，需新授权）

v20 证明 per-ED 完成不改变复位的结论后，v21 改为在 **burst 之间复位端点**
（只改 app，payload 回到 v16 的单次完成 cave）：

- 在每个 burst 完成后、下一个 post 之前，且此时没有在飞请求，调用一次
  `usbDsEndpoint_Cancel(endpoint)`；
- 记录 `UAC U2 idle cancel seq=%u rc=0x%x`，并在 cancel 之后立即再 dump 一次
  `UAC U2 state after-cancel …`，看 prod/cons/copy/cycle 是否变化；
- 超时 cancel 已观察到会把 ring 复位回 base；如果空闲 cancel 也让控制器
  dequeue 重启，那么写回 base 的第 2 套 TD 就应该能被取指。

| 项 | 值 |
| --- | --- |
| 构建 | `ed52a9d7…`（91954B），cave `806f54cb…` / 592B（与 v14/v16 相同） |
| defines | `-DUAC_U2_BURSTS=4 -DUAC_U2_IDLE_CANCEL` |
| 工作目录 | `private/analysis/UAC-u2-v21-idle-cancel-20261101` |

一次 boot 的判定：

| 观察 | 结论 |
| --- | --- |
| `idle cancel rc=0x0`，seq2 收到数据 | idle cancel 复位了端点/控制器 dequeue；继续做 4-burst |
| `idle cancel rc=0x0`，seq2 仍无 completion | cancel 没有重启控制器；回到端点状态/控制器 halt 分析 |
| `idle cancel` 返回错误，后续 post 也失败 | cancel 干扰了端点；停，退回无 cancel 版本再想别的复位路径 |
| 任一 crash/fatal | 立即停，读卡取报告 |

停止条件与以往相同：一次 boot、失败即停、读卡恢复 `52069a44…`。

## 2026-11-01 14:3x v21 实机：idle cancel 是 no-op

host：`urb[2] 960B` + `urb[3] 2112B` = 3072B，之后全 bad；
`valid=57 bad=935 bytes=3072`；无新 crash/fatal/erpt。

设备（`private/runs/UAC-u2-v21-idle-cancel-20261101`）：

```text
seq1 complete 3072/3
seq2 pre          prod=cons=ring, copy=ring+0xff0
idle cancel rc=0x0
after-cancel      prod=cons=ring, copy=ring+0xff0   ← 与 pre 完全相同
seq2 post         prod=ring+0x200, box ISO2
100 ms 无 completion → cancel
```

结论：**空闲 `usbDsEndpoint_Cancel` 返回成功但完全不改变端点状态**，也不重启
控制器 dequeue；seq2 仍然失败。cancel 不是复位手段。

## v22 alt-cycle（已离线构建，0 实机，需新授权）

思路：不依赖跨请求的 ring 复用，让每个 burst 都遇到“刚安装”的端点。

- 设备：`-DUAC_U2_ALT_RETRIGGER` 让 `SET_INTERFACE(0)`（`UAC_ACT_STOP`）清
  `burstPosted`；`-DUAC_U2_BURSTS=1` 使每次 alt1 只 post 一个 3072B burst。
- host：`uac-raw-probe --alt-cycle --cycles 4 --transfers 8 --delay-ms 30
  --timeout-ms 500`；每个周期 alt0 → alt1 → SET_CUR → 30 ms → 提交 8 个 URB
  → 收集，打印 `cycle[i] alt0/alt1/set_cur/valid/bad/bytes`。
- payload 仍是 v16 单次完成 cave（`806f54cb…` / 592B）。

| 项 | 值 |
| --- | --- |
| 构建 | `8335b6f1…`（91936B），cave 592B，`g_u2BurstBuffers` 0x1000（1 个） |
| defines | `-DUAC_U2_BURSTS=1 -DUAC_U2_ALT_RETRIGGER` |
| 工作目录 | `private/analysis/UAC-u2-v22-alt-cycle-20261101` |
| host 二进制 | `host/uac-raw-probe`（本机编译通过；guest 需重新编译） |

一次 boot 的判定：

| 观察 | 结论 |
| --- | --- |
| 每个 `cycle[i]` 都有 ~3072B，设备每个周期 `complete 3072/3` | **每个 burst 用新端点**可行，连续 4 burst 拿到 12288B |
| 只有第 1 个周期有数据 | 重新安装也没有重启控制器；需要换思路（驱动内部端点状态） |
| 某些周期 `alt1` 失败 | SET_INTERFACE 在运行中不安全；停，不重试 |
| 任一 crash/fatal | 立即停，读卡取报告 |

停止条件与以往相同：一次 boot、失败即停、读卡恢复 `52069a44…`。

## 2026-11-01 14:4x v22 实机：alt 重装不成立

host：`cycle0` 3072B（valid=57 bad=71），`cycle1..3` 全 0（valid=1 bad=127 每个）；
alt0/alt1/SET_CUR 每个周期都成功；设备在线、无新 crash/fatal/erpt。

设备（`private/runs/UAC-u2-v22-alt-cycle-20261101`）：

```text
4 次 post（seq=1..4，每次 1/1）        ← alt0 清 burstPosted 生效
seq1 complete 3072/3
seq2..4 post rc=0 → 100 ms 无 completion → cancel
每个周期 precheck：同一个 install obj/table、installed=1、ring/prod/cons 在 base
```

结论：

- **alt0→alt1 不会重新安装端点**：install object/table 一模一样、installed
  仍是 1；驱动只在 Configured 路径跑安装器。
- 因此“每个 burst 都用新端点”这条路走不通；v22 否掉。
- 目前所有尝试（位置、per-ED、cancel、alt 重装）都失败，共同点是
  **安装后只有第一个 TD 集能被取指**。剩下的杠杆是安装时对控制器
  ring/dequeue 的编程（安装器 `0x295d0` 及其寄存器写入），cave 的“写 TD +
  门铃”路径无法复位它。

## v23 方向（离线优先，需新授权才能上机）

1. 静态读安装器 `0x295d0` 与它写入的端点上下文/寄存器（ring base、dequeue、
   cycle），确认控制器为什么在第一个 TD 集后不再取指；
2. 候选修法：cave 在每次 post 前按安装路径重写 dequeue/ring 寄存器，或在
   完成路径里调用安装器的一个安全子集；任何跨进程写/重编程都要先离线验证；
3. 若不成立，考虑换 host 侧路径（AppleUSBAudio 连续流）或重新评估
   A23 与 UAC 的端点安装差异；
4. 上机仍需新授权、一次 boot、失败即停。

## 风险## 风险## 风险## 风险

- 这是**跨进程写**（app 通过 dmnt 写 usb 模块的 ring 字段），写点与 cave
  提交时的写点相同，但发生在驱动空闲期；若假设错误，可能让后续请求状态
  异常（不排除 crash）。因此只跑一次、失败即停。
- 4 个 burst 仍是 64 ms，不构成持续音频；PCM/时钟/共存仍未测。
- 8 个 descriptor-parser NOP 的全局风险仍未隔离。

## 2026-11-01 15:0x v23 离线：安装器只是描述符遍历器，缺的是 commit

读 `usb.elf` 的结论（细节、地址表与指令出处见
[UAC_U2_ENDPOINT_CONTEXT.md](UAC_U2_ENDPOINT_CONTEXT.md)）：

- `0x295d0` 只在总线状态 4→5（`SET_CONFIGURATION`）里遍历描述符，调用
  `vtable[+96]`（= `0x2fd30`）装端点、再把 `install_obj+0x14D0+idx*16`
  置 1；函数体内没有任何寄存器/上下文访问。
- `0x2fd30 → 0x2fd80 + 0x2feb0`：建/找端点对象、分配 ring、memset、把
  base/enqueue/dequeue/cycle 复位，`0x30b50` 写 64B 端点上下文（state=1、
  TR dequeue 物理地址 + DCS），然后写 `regs+0x58` **commit**、清
  `regs+0x54/0x50` 的 halt。
- 完成错误路径 `0x30ff4`（码 3/4/5/9/10/14/15/31、`0xDB`/`0xDE`）在 burst
  之后 memset ring、重装同一份上下文，却**不 commit、不清 halt**，反而置
  `regs+0x50`。这就是“只有第一个 TD 集被取指”的机制：v16/v19 观察到
  burst 完成后 prod/cons/copy 回 base，而控制器仍停在旧状态。
- 附带发现：UAC 的 DCI-9 cave 仍用 `ISO_ENTRY=0x270`（DCI 7 的对象），
  UAC 配置里该槽为空，`iso_event` 一直落到 `event_original`；v19/v20 对
  cave 事件分支的评价需要用这个前提重读。本轮不修（一次一个变量）。

v23 候选：`patches/iso_burst_uac84_dci9_rearm.S`，在 `prod==cons` 门之后
保存 `x0/x1/x2/x30`、`bl 0x2feb0`、恢复并重载 `x8/x10`，其余 cave 不变；
cave 620B（limit 684）、29 条 edits、NSP `d984f729…`（91927B）、
`-DUAC_U2_BURSTS=4`，工作目录 `private/analysis/UAC-u2-v23-rearm-20261101`。
**未部署、0 实机**；上机需新授权，一次 boot、失败即停。
## 2026-11-01 16:0x v23 实机：4/4 burst 成功

`d984f729…`（91927B，cave 620/684B，每 burst 重放 `0x2feb0`）一次 boot：

- host：`claim/alt1/SET_CUR` ok；`done transfers=62 packets=16 valid=217
  bad=775 bytes=12288`；四个 3072B burst（t=34/194/356/498 ms）。
- 设备：seq1..4 每个 `post rc=0`、`complete rc=0 requested=3072
  transferred=3072 status=3`；`UAC U2 train end posted=4 completed=4`；
  每 burst 后 prod/cons/copy 仍被驱动复位回 base，但下一个 burst 被取指。
- 判定：**commit（`regs+0x58`）+ 清 halt（`regs+0x54/0x50`）就是缺失步骤**；
  `0x30ff4` 复位 ring/上下文不 commit，旧代码第二个 TD 集因此不被取指。
- crash：无；卡 erpt 27 / crash 21 与部署前相同。
- 证据：`private/runs/UAC-u2-v23-rearm-20261101`、`private/card-cycles/20261101-u2-v23-rearm`。
- 收尾：恢复 `52069a44…`、删 `/logfile.txt`、安全弹出；无重试。

下一轮：把“每 burst 重放 `0x2feb0`”收敛为“首 burst 后只 commit/清 halt”或
ring 跨 burst 连续，再验证 8/16 burst 与更短间隔。


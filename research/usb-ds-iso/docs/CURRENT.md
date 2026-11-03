# 当前状态（2026-11-03 22:2x，Asia/Shanghai）

> 本文件是唯一“当前状态”，只写现在成立的事实、最佳配置、下一步与边界。
> 逐轮时间线见 [README_HISTORY.md](../README_HISTORY.md)，U2 数据路径细节见
> [UAC_U2_PIPELINE.md](UAC_U2_PIPELINE.md)，全部文档见 [INDEX.md](INDEX.md)、
> [ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)。[STATUS.md](STATUS.md)、
> [PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md) 等是旧快照，不再作为入口。

## 一分钟

- 目标：让 Switch `usb:ds` 输出标准 UAC 音频（48 kHz / 2ch / 16 bit = 192 B/ms）。
- **数据路径最好一轮（v29m 重复轮）**：64/64 posts、**63 个完整 3072 B
  片段（193536 B）**、host 与设备字节相等、**1 次单套 miss、0 恢复**、
  无 crash/fatal/erpt；alt0 不崩。
- **同一 NSP 的方差**：v29m 首跑 58 段 / 3 miss / 1 recover（179904），
  重复跑 63 段 / 1 miss / 0 recover（193536）——**58 是方差，不是
  map-soft-2 的影响**；单轮比较需要至少两次重复。
- **lead 扫描**：16（v29j）54 段、32（v29h）62 段、40（v29l）58 段；
  lead 32 仍是最好，40 没有收益。
- **收尾/map 安全**：v29m 两轮枚举 5 次 `SET_INTERFACE(0)` 均无
  `svcBreak`、无新 crash/fatal；v29l 的 `2162-0004` 未复现。
- **已否掉的路线**：单次请求 >16 帧、两 buffer 流水线、4 在飞/4 套环
  （v29i）、lead 4/16/40。
- 限制：占空比约 47%，48 kHz 连续仍不成立；UAC 默认仍禁用（仅
  `UAC_HOST_PROBE`）。
- **v29n 实机：rearm race 确认**：NSP `5421884e…`（92960 B，v29m
  payload + app rearm-race 日志）。设备 60 段 / **misses=4**，日志里
  **4 条 `UAC U2 rearm race` 与 4 次 miss 一一对应**（seq 4/16/45/63，
  buf 3/7/4/6）；host==device（184320）。
- 机制：ring 在投递瞬间被排空，cave 走空 ring rearm（`0x2feb0` 的
  0x1000 memset + commit），把刚发出那套的 pending completion 一起
  wipe，控制器回 `status=5`——不是驱动 `0x30ff4`。
- **v29o 实机：缩短 memset 没有消除 miss**：NSP `855e7d41…` 得到 62 段
  （190464 B）、**misses=2、2 条 rearm race**，仍 1:1 对齐；host==device，
  无 crash/fatal/erpt。
- 解释：丢的不是 mailbox 里的 pending completion，而是 **rearm 本身**
  （`0x2feb0` 的 context reset + commit + halt clear）与刚发出的 set
  竞争——自然排空时不需要 rearm。
- **v29p 实机是退步**：57 段（175104 B）、**misses=4、recoveries=1**；
  跳过非 base 的 rearm 后控制器停住（`cons` 冻在 `+0xd380`、`prod`
  继续前进），多出 miss 和一次 100 ms stall；**base 门判据不成立**。
- 剩下的 2 条 rearm race 显示：drain 时**驱动自己**会把 ring 复位到
  base（pre 非 base、post base），所以 cave 仍走 rearm——竞态源在驱动
  的 drain reset，不在 cave 的空 ring 门。
- **离线更正（v29q 分析）**：那次复位是 `0x30ff4`，触发条件是控制器的
  **error code 事件**（码集 3/4/5/9/10/14/15/31/0xdb/0xde），而空档来自
  **app 自己的逐 post 诊断**——每次 post 一行 SD 日志 + 两次 dmnt dump。
  v29p 的 cursor 帧差均值 **40.2**、中位 33（一套 = 16），host 覆盖
  177024 B / 2609 ms = **35.3%**：延迟 D 让 `MFI+32` 盖过 cursor，空档
  里的帧必然在控制器上漏服务（**具体 error code 未观测**，只知
  `0x30ff4` 接的是 3/4/5/9/10/14/15/31/0xDB/0xDE）→ 复位 → 丢一套。
  62/63 段与 35% 是**带诊断的上界**，不是数据路径上限；58 vs 63 的
  “方差”也由此而来。
- **v29q 实机证实了这一点**（payload 与 v29m 逐字节相同，只去掉 app 的
  逐 post 日志与 dmnt cursor dump）：**span_ms=1201**（v29p 2609，快
  2.17×），host 活跃窗 33–1185 ms、**覆盖 81.7%**（v29p 35.3%），
  **59 段**（181248 B，v29p 57），misses=2、recoveries=1，
  `max_gap_ms=181`、`max_react_ms=129`；无 crash/fatal/erpt。
- 扣掉那次 181 ms 空档后，64 次 post / 1024 ms = **每条 16.0 ms**，正好
  等于一套 TD：**节奏本身已经修好**。剩下的损失全在那一次 miss 事件：
  2 个 `status=5`（v29s 后来证明是 code 23 = Missed Service，驱动只置
  halt、不复位 ring）→ app 等 100 ms 才 cancel、再 32 ms lead 才出数据，
  host 侧看到 **~176 ms 无数据**，丢 5 套（2 miss + 3 被 cancel）。
- **v29r（stall 阈值 32 ms）是负结果，且原因干净**：一条 TD 集要
  `MFI+32` 才被取指、再 16 帧才完成，**首个 completion 约需 48 ms**；
  32 ms 阈值在它之前就触发，app 把自己刚投的 3 套 cancel 掉再重投，形成
  cancel 风暴。日志正好 8 条 `pipe stall recover ... limit_ms=32`
  （recoveries 上限）后第 9 次 stall 退出循环：posted=27、completed=24
  （全是 cancel 记账）、**bytes=0**，host 只在 18–354 ms 漏出 4032 B。
  → **100 ms 不是随手定的下限**，阈值必须 > lead + 一套（≈48 ms）。
- **v29s 拿到了错误码：23 = Missed Service**。设备日志：
  `evlog miss count=2` → `[0] code=23 len=192 off=0xba0`、
  `[1] code=23 len=192 off=0xbc0`——**第 6 套（0xa00..0xbff）的最后两个 ED
  槽**；两次 miss 读到的条目相同（同一次事件、两个 URB 各报 status=5）。
- **驱动对 code 23 只置 halt，不复位 ring**：`0x31274` 置 `regs+0x50` 的
  dci 位、轮询并 ack `regs+0x5c`，然后走 `0x31118` 用 `w2=0x3228c`
  完成 URB（app 看到的 status=5）。**prod/cons 不变**，所以 cave 的下一次
  post 在 `prod` 直接写、不 rearm，halt 永远不清 → 没有 completion →
  app 的 100 ms stall 定时器才 cancel（`0x30470` 把 ring 复位到 base）→
  下一次 post 走 `0x2feb0`（commit + 清 halt）→ 首套还要 32 ms lead。
  **194 ms 空档就是这么来的**（`max_gap_ms=194`）。
- 对照 xHCI 1.1 编号：13 = Short Packet、23 = Missed Service、26 = Stopped
  ——与驱动自己的三个特殊分支完全吻合。训练结束后那个
  `code=14 len=0`（Ring Underrun，TRB 指针为空）走了 `0x30ff4`，是收尾的
  ring wipe。
- **结论：miss 是 host/控制器漏服务（两帧没被服务），不是 cave 竞态**；
  真正可动的是“halt 之后的恢复”。`ISO_ENTRY` **已由实测确认**，未隔离项
  只剩 8 个 descriptor-parser NOP。
- **v29t（miss 立即 cancel/重投）成立，新最好**：同一次 code-23 miss
  （第 2 套槽 12/13，off=0x580/0x5a0），但 `status=5` 一到就 cancel：
  `recoveries=1`、`cancelled=1`（v29s 是 3），**`max_gap_ms=77`**
  （v29s 194）、`max_react_ms=31`（147）；**61 段 / 187392 B**、span
  1146 ms，host 188544 B、覆盖 **88.9%**（v29s 78.7%）。
- **host 预排关闭**：同一 v29t 镜像、probe 改 `--transfers 16`（256 帧
  预排）结果与 8 个几乎一样——仍是一条 `code=23`（第 5 套槽 11/12，
  off=0xb60/0xb80）、`misses=2`、61 段、`max_gap_ms=88`、覆盖 86.6%。
  宿主不缺排队的工作，漏服务不是预排问题。
- **漏帧位置有规律**：v29s `0xba0/0xbc0`、v29t `0x580/0x5a0`、h16
  `0xb60/0xb80`——**永远是某套的 Isoch 槽 11–14**（一套 16 帧的尾部几帧），
  也就是控制器“已取到的 TD 材料用尽”的位置。
- **v29u（4 在飞）是负结果**：仍是一条 `code=23`，位置回到第 5 套槽 13/14
  （`0xba0/0xbc0`，与 v29s 相同）；`misses=2`、`max_gap_ms=95`、60 段
  （184320 B）、host 覆盖 87.7%。span 1114 ms 是最短的一次，但恢复要
  cancel **2** 套（4 在飞多一套），整体不如 v29t。
- **设备侧 miss 排查到此为止**：host 预排（8/16）、在飞深度（3/4）、cave
  空 ring 门、memset 长度、lead 扫描（16/32/40）都没有改变 code 23；
  漏帧永远落在某套的 Isoch 槽 11–14。**v29t 仍是最佳配置**。
- **v29v 长跑给出稳态数字（4.45 s）**：256 posts、**247 段（758784 B）**、
  **3 次 code-23 事件**（每次恰好连丢 **两帧**）、3 次恢复（每次 cancel 1 套）、
  **`span_ms=4449`**（理论下限 4096，差值 ≈ 3×80 ms）、`max_gap_ms=80`、
  `max_react_ms=34`；设备侧覆盖 **88.8%**、host 窗 **90.3%**。
  漏的槽位这次是 0xb60/0xb80（第 5 套 11/12）、0x4a0/0x4c0（第 2 套 **5/6**）、
  0x160/0x180（第 0 套 11/12）——**并不总在套尾**，此前的“尾部规律”是
  小样本错觉（v29u 的 4 在飞负结果正好与之相符）。
- **长期 ring 复用首次得到证据**：4.45 s 里环走了 **~43 次六套 wrap**、
  游标两次 2048 帧回卷，没有卡死或漂移。
- **v30b（64 在飞）是退步，深度曲线在 32 见顶**：host 250.5 套 / 覆盖
  91.4%（32 深是 253.2 / 94.1%）、设备 **2 次 code-23**（32 深 1 次）、
  `max_gap_ms=90`（32 深 78），并且重现 1 次 `p0` 单包丢失；64 个 URB
  全部提交成功，说明不是资源上限，而是队列更长反而推迟了队首补投。
  **深度曲线：8→16→32→64 = 246.4/251.5/**253.2**/250.5 套、
  89/91.4/**94.1**/91.4%、事件 4/2/**1**/2。**
- **v30a：host 32 在飞 → 当前最好**。depth 8→16→32：
  host 交付 **246.4 → 251.5 → 253.2 套**、覆盖 **89% → 91.4% → 94.1%**、
  host 可见丢包 **2 → 0 → 0**、设备 code-23 事件 **4 → 2 → 1**。32 深这次
  设备 **253 段（777216 B）**、`span_ms=4351`、`max_gap_ms=78`、
  `max_react_ms=31`、无提交失败。
- **v29z：host 16 在飞**。同一 v29v 镜像、同一 instrumented
  probe，只把 `--transfers` 8→16：**`detail` 行 0 条、单包丢失 0**
  （v29y 的 8 深是 2 个、都在 `p0`），host **772608 B / 251.5 套**、
  **192 个满 3072 的 URB**、覆盖 **91.4%**（均最好）；设备 **251 段**
  （771072 B）、**2 次 code-23**（v29y 4 次）、`span_ms=4444`、
  `max_gap_ms=87`。→ **host 侧 p0 漏帧是补投节奏**，加深在飞即消除；
  剩 2 次设备事件在 libusb per-packet 里看不到（另一路）。
- **v29x 第三次长跑复现**：250 段（768000 B）、2 次 code-23（第 3 套槽
  14/15、第 4 套槽 **2/3**）、`span_ms=4426`、`max_gap_ms=90` → 稳态在
  247/250/250 段、2–3 事件、4419–4449 ms、80–90 ms 之间稳定。
- **v29w 长跑复现（250 段）**：同一 v29v 镜像再跑一次长跑——
  256 posts、**250 段（768000 B）**、**2 次 code-23 事件**（第 3 套槽 5/6、
  第 1 套槽 6/7）、2 次恢复、`span_ms=4419`、`max_gap_ms=84`；host
  768576 B。与 v29v（247 段 / 3 事件 / 4449 ms）在方差内 → **稳态可复现**：
  4.5 s 里约 1–2 次“两帧”漏服务。
- **宿主侧采集修正**：那次开的 `xhci-hcd` tracepoint 采到空 trace——
  设备在 **Bus 001 / `ehci-pci`**，xhci 是 Bus 002/003 的键盘鼠标，内核
  没有 ehci tracepoint。改用 **usbmon bus 1**（工具 `--format usbmon`）。
- 卡：安全 `52069a44…` 已恢复并弹出（21:5x）；v29q…v29z 日志均已归档。

## 阶段进度

| 阶段 | 状态 | 关键结果 | 证据 |
| --- | --- | --- | --- |
| U0 枚举 | 通过 | 257 B / 4 接口，macOS 绑定 `AppleUSBAudio`，2ch/48k | `UAC-u0d-20261030` |
| U1a 控制 | 通过 | 13/13；`SET_CUR(48000)` ACK 并回读 | `UAC-u1a-r7-20261030` |
| U1b alt | 通过 | alt 0→1→0 均 ACK，无 NOP | `UAC-u1b-20261030` |
| U2 单 burst | 通过 | v14：3072 B / status=3，2/2 可重复 | `UAC-u2-v14-trigger-success-20261031` |
| U2 顺序 4-burst | 通过 | v23：12288 B；重放 `0x2feb0` 的 commit + 清 halt | `UAC-u2-v23-rearm-20261101` |
| U2 2 在飞 | 通过 | v29b：8/8 全 `3072/3`，host = 设备 = 24576 B | `UAC-u2-v29b-sets-20261102` |
| U2 滚动流 | 部分 | v29c：61 段 / 2.1 s，收尾在 TD 环 wrap | `UAC-u2-v29c-stream-20261102` |
| U2 wrap 对齐 | 通过 | v29d：`+0xa00→+0x000`、cycle 翻转，set 不拆 | `UAC-u2-v29d-wrap-20261102` |
| U2 3 在飞 + 恢复 | 通过 | v29e：64 posts、56×`3072/3`、4 miss 全 recover | `UAC-u2-v29e-quad-20261102` |
| U2 miss 容忍 | 通过 | v29f：61 段、host==device、3 miss 无连锁 | `UAC-u2-v29f-miss-20261102` |
| U2 收尾 map-soft | 通过 | v29h：alt0 只返回错误，控制台不崩 | `UAC-u2-v29h-map-soft-20261102` |

单次请求上限仍是 **3072 B / 16 帧**：20 帧（3840 B）、32 帧（6144 B）都会挂死
`usb:ds`，上限落在 17–19 帧，“加大单次 transfer”路线已关闭。

## 数据路径最近十轮

| 轮次 | 做法 | host | 设备 | 判定 |
| --- | --- | --- | --- | --- |
| v29h | IOVA 节点耗尽返回错误（map-soft） | 190464 B | 62×`3072/3`、2 miss | 收尾不崩 |
| v29i | 4 套环（`+0x800`）+ 4 在飞 | 187392 B | 61×`3072/3`、3 miss | 负结果：4 套深度不够 |
| v29j | v29h + lead 32→16 | 170688 B | 54×`3072/3`、4 miss、2 stall | 负结果：lead 16 太小 |
| v29k | v29h + lead 32→40 | —（崩溃，无数据） | —（开机枚举 alt0 崩溃） | 0 数据；第二入口 `0x3dac` 崩溃，v29k 未测 |
| v29l | v29k + `0x3dac`→`0x409c`（map-soft-2） | 179712 B | 58×`3072/3`、3 miss、1 recover | lead 40 负结果；host 比设备多 1536 |
| v29m | 回退 lead 32 + 双 map-soft | 179904 B | 58×`3072/3`、3 miss、1 recover | 首跑；后被证明是方差 |
| v29m-r2 | 同一 NSP 重复 | **193536 B** | **63×`3072/3`、1 miss、0 recover** | **新最好；host==device** |
| v29n | v29m + app rearm-race 日志 | 184320 B | 60×`3072/3`、4 miss | **4/4 rearm race 对齐，机制确认** |
| v29o | v29n + `0x2feb0` memset 0x1000→0xf00 | 190464 B | 62×`3072/3`、2 miss、2 race | memset 缩短未消除 miss；rearm 本身是竞态源 |
| v29p | v29o 门改：仅 base 才 rearm | 177024 B | 57×`3072/3`、4 miss、1 stall | **退步**：跳过 rearm 会停流；门判据不成立 |
| v29q | v29m payload + app 静默流水线 | 180672 B（58.8 套） | **59×`3072`、2 miss、1 recover、span 1201 ms** | **成立**：覆盖 81.7%（v29p 35.3%）；损失集中在那一次 miss → halt |
| v29r | v29q + `STALL_MS=32` | **4032 B** | posted=27、completed=24、**bytes=0**、8 recover | **负结果**：阈值 < lead+一套（≈48 ms）→ cancel 风暴 |
| v29s | v29q + `ISO_ENTRY 0x300` / 只记录型 `iso_event` | 183744 B（59.8 套） | 59×`3072`、2 miss、1 recover、span 1250 ms | **诊断命中**：code=23（Missed Service）@0xba0/0xbc0；驱动只置 halt |
| v29t | v29s + miss 立即 cancel/重投（app-only） | **188544 B（61.4 套）** | **61×`3072`、2 miss、1 recover/cancelled=1、span 1146 ms** | **成立，新最好**：`max_gap_ms` 194→**77**、覆盖 **88.9%** |
| v29t-h16 | 同一镜像 + host `--transfers 16` | 188928 B（61.5 套） | 61×`3072`、2 miss、1 recover、`max_gap_ms=88` | **负结果**：host 预排不是杠杆；漏帧仍在槽 11–14 |
| v29u | v29t + `IN_FLIGHT=4` | 186816 B（60.8 套） | 60×`3072`、2 miss、1 recover（cancel 2）、`max_gap_ms=95` | **负结果**：4 在飞不改 code 23；恢复更贵，回 v29t |
| v29v | v29t 配置 + 256 posts / 恢复上限 64 | 762816 B（248.3 套） | **247×`3072`、6 miss/3 事件、3 recover、span 4449 ms** | **稳态成立**：覆盖 88.8%（host 90.3%）、`max_gap_ms=80`、环 43 次 wrap 正常 |
| v29w | 同 v29v + xhci trace 尝试 | 768576 B（250.2 套） | 250×`3072`、4 miss/2 事件、2 recover、span 4419 ms | **复现**：`max_gap_ms=84`；trace 空（设备在 EHCI，非 xHCI） |
| v29y | 同镜像 + per-packet probe（8 在飞） | 756864 B（246.4 套） | 245×`3072`、8 miss/4 事件、4 recover、span 4559 ms | 宿主 `p0=1/0` ×2（相隔 1344 ms）：**宿主在 URB 第 0 帧漏服务** |
| v29z | 同镜像 + per-packet probe，**16 在飞** | **772608 B（251.5 套）** | **251×`3072`、4 miss/2 事件、2 recover、span 4444 ms** | **新最好**：`detail` 0 条、覆盖 **91.4%**、`max_gap_ms=87` |
| v30a | 同镜像 + per-packet probe，**32 在飞** | **777792 B（253.2 套）** | **253×`3072`、2 miss/1 事件、1 recover、span 4351 ms** | **新最好**：`detail` 0、覆盖 **94.1%**、`max_gap_ms=78` |
| v30b | 同镜像 + per-packet probe，64 在飞 | 769536 B（250.5 套） | 250×`3072`、4 miss/2 事件、2 recover、span 4432 ms | **退步**：事件回到 2、`p0` 重现；深度曲线在 32 见顶 |

## 当前最佳配置（v29t = v29s payload + 立即恢复 app）

| 项 | 值 |
| --- | --- |
| NSP / NSO | v29t `cac6ed88…`（93059 B）/ `cb22dd47…` |
| cave | `patches/iso_burst_uac84_dci9_pipe_quad_log.S`（548/684 B，lead 32，`ISO_ENTRY=0x300`） |
| ring | link `+0xc00`（六套对齐）；mailbox `+0xf00/+0xf40/+0xf80/+0xfc0`，`set=(offset>>9)&3`；游标 `+0xfb8` |
| 在飞 | 3；miss 容忍（status=5 只释放槽并补投）；**100 ms** stall 才 cancel + 重投（**不要降到 48 ms 以下**，v29r 已证）；alt0 STOP 先 cancel + 收 report |
| 驱动 | 3 处队列补丁 + 12 处 link `0xff0→0xc00` + map-soft `0x3fe0` + map-soft-2 `0x3dac`（46 条 edits） |
| app | `-DUAC_U2_BURSTS=8 -DUAC_U2_STREAM_POSTS=64 -DUAC_U2_LIGHT_LOG -DUAC_U2_PIPELINE -DUAC_U2_QUIET_PIPE -DUAC_U2_EVENT_LOG`；miss 立即恢复；（**不要**再加 `CURSOR_DIAG`） |
| host | 长跑（最佳）：`uac-raw-probe3 --trigger-first --delay-ms 30 --packets 16 **--transfers 32** --rearm --max-urbs 512 --timeout-ms 10000 --keep-alt`（**不要用 64**，v30b 已证更差；短跑 64 用 `--transfers 8 --timeout-ms 5000`） |
| 结果（短跑 64） | **61×3072（187392 B）**、host 188544、span **1146 ms**、host 覆盖 **88.9%**、misses=2、recoveries=1（cancelled=1）、无 crash/fatal |
| 结果（长跑 256，**32 在飞**） | **253×3072（777216 B）**、host **777792**、span **4351 ms**、覆盖 **94.1%**、2 miss（1 事件）、1 recovery、`max_gap_ms=78` |
| 对照 | v29q 59 段 / 1201 ms / 81.7%；v29s 59 段 / 1250 ms / 78.7%；v29m 带诊断 63 段但 2609 ms / 35% |
| 对照 | v29m 同 payload 带诊断：63 段但 span 2609 ms、覆盖 35.3%——**段数不是节奏指标** |

## 构件与关键事实

- **端点**：AS `EP 0x84`，端点字 `0x00C00584`（不是 `0x00C00184`），DCI 9、
  MPS 192、interval 4。安装对象 `base+0x17b038`，`installed` 在 `+0x1610`，
  表项指针在 `+0x1608`。
- **Ring**：0x1000；一套 = 16 帧 × 192 B = 3072 B，16 对 Isoch + ED TRB，
  `prod` 每次前进 `+0x200`。最佳配置 link `+0xc00`（六套对齐；偶数保 mailbox
  交替），四 mailbox 都在 link 之后。
- **cave**：`pipe_quad` 680/684 B（区段 `0x68d54..0x69000`）；per-set
  mailbox、全局游标、空 ring 时重放 `0x2feb0`；lead 32。
- **驱动补丁**：队列 3 处（`0x0c4` stub、`0x2c628` 总是提交、`0x2c80c`
  跳过自动提交）、link 12 处（`0x2f530`/`0x2ff40`/`0x30578`/`0x310c8` 的
  `add`/`clear`）、map-soft 1 处（`0x3fe0` 的 `cbz x0, 0x40d0` → `0x409c`）、
  map-soft-2 1 处（`0x3dac` 的 `cbz w0, 0x40cc` → `0x409c`）。
- **payload**：46 条 = cave + 2 分支 + 18 描述符 + 8 NOP + 3 队列 + 12 link
  + 1 map-soft + 1 map-soft-2。
- **接口预算**：`usb:ds`/libnx 最多 4 个接口，UVC 2 + UAC 2 = 4，因此 UAC 不能与
  `ISO_PROBE` 的 vendor 接口同 build。

## 下一步

1. **当前最佳配置 = v29v 镜像 + host `--transfers 32`**：253/256 段、覆盖
   94.1%、1 次 code-23、`max_gap 78 ms`。64 已证更差，不要再用。
2. **再跑一次 32 深**（同镜像、同命令）分辨方差与趋势：若这次 0–1 次
   事件、253–256 段 → 32 就是稳态最优，可以进入 8–10 s 连续测试；
   若波动到 3–4 次 → 单次结果不可作结论，需要多次取中位数。
3. 8–10 s 连续测试要改设备侧 app（`STREAM_POSTS=512/640`），见
   [UAC_U2_HOST_TRACE.md](UAC_U2_HOST_TRACE.md) 之外的常规构建流程。
4. 设备侧不再动；8 个 descriptor-parser NOP 仍未隔离。

判定：先复跑 32 深确认方差，再谈长跑。

## 边界与纪律

- 实机授权：2026-11-01 16:19 起常设授权——部署/测试不再逐轮申请，插卡与开机前
  通知用户即可；一次 boot、失败即停、不重试。
- “部署”只等于把文件拷到卡上；插卡、开机、关机由用户执行。
- VM 纪律：**Switch 开机前必须 suspend/detach**；主界面后再 resume + attach；
  确认 guest 只在 attach 后看到 `1209:ca57`（这是 11-03 崩溃的直接原因）；
  必要时一次 VM suspend/resume 让 guest 枚举；probe 一次。
- 收尾：恢复安全卡 `52069a44…`、删日志/新报告、安全弹出；设备现场状态不推定。
- `private/` 是原始证据，只读；不覆盖、不移动、不清理。

## 不证明

48 kHz 连续 PCM、标准宿主（Linux `snd-usb-audio`）互操作、>2.7 s 稳态与长期
ring/缓冲复用、0 miss、16 ms/段、时钟同步/反馈、A23 10 s 连续、旧超时根因。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [../START_HERE.md](../START_HERE.md) | 60 秒上手与当前边界 |
| 本文件 | 唯一当前状态 |
| [../WORKFLOW.md](../WORKFLOW.md) | 一轮怎么走 |
| [RESEARCH_RULES.md](RESEARCH_RULES.md) | 安全边界与验收定义 |
| [UAC_U2_PIPELINE.md](UAC_U2_PIPELINE.md) | U2 数据路径专题（逐轮） |
| [UAC_U2_ENDPOINT_CONTEXT.md](UAC_U2_ENDPOINT_CONTEXT.md) | 端点安装与 re-arm |
| [UAC_PCM_GAP.md](UAC_PCM_GAP.md) | 占空比/PCM 模型 |
| [../README_HISTORY.md](../README_HISTORY.md) | 逐轮时间线（只追加） |
| [INDEX.md](INDEX.md)、[ARCHIVE_INDEX.md](ARCHIVE_INDEX.md) | 文档索引与历史阶段 |
| `../private/` | 原始证据（不入库，只读） |

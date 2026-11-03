# UAC U2：连续 ring / 双 buffer 流水线（v26 设计，离线）

> 状态：**v26A 实机部分成功（8 post/8 report，只有偶数 buffer 上线）；v26B
> 帧游标已离线实现并构建（`116a1204…`，92342B），0 实机**。v23 证明
> “每 burst 重放 `0x2feb0`”能让 4 个顺序 burst 全部完成；v24 把 dmnt dump
> 去掉后 gap 96 ms；v25 把 TD 帧 lead 压到 4 ms 失败（1536B、`0x748c`），
> 回退 32 ms。v29d（2026-11-02 18:3x）：link 移到 `+0xc00`（六套对齐），
> 离线构建 NSP `287907b8…`，0 实机。本文件先设计、后实现连续 ring，不重复
> [UAC_U2_CONTINUOUS.md](UAC_U2_CONTINUOUS.md) 与
> [UAC_U2_ENDPOINT_CONTEXT.md](UAC_U2_ENDPOINT_CONTEXT.md) 的事实。

## 现状

v24（lead 32、light log）一次 burst 的时间线：

```text
post ──(cave 重放 0x2feb0: memset ring + 上下文 + commit + 清 halt)──>
     ──32 ms TD 帧 lead──> 16 ms 16 包 ──~12 ms 事件/驱动──> completion
     ──20 ms report──> 12-14 ms loop ──> 下一个 post
```

wire gap 96 ms，其中只有 16 ms 有数据。`post_ms=0`，重放开销不是问题；
`report_ms`、`loop_ms` 与 32 ms lead 是空档来源。

## 关键观察

驱动只在控制器**报错**（服务漏/underrun）时走 `0x30ff4`，把 ring 复位到
base 并置 halt。每次 burst 结束时设备没有后续 TD、host 仍在取数，于是报错
→ 复位 → 必须重放 setup。**如果 ring 里始终有一套 TD 排在后面，控制器
不会跑空，驱动不会复位，也就不需要每 burst 重放。**

因此连续流的核心不是“更快地重放 setup”，而是“ring 不空”。

## 两个可行方案

### A. 16 ms 定时投递（推荐先做）

- app 以 16 ms 为节拍 post 下一个 3072B buffer，保持 2 个在飞；
- 每个 post 的 cave 帧号仍是 `MFI/8 + 32`；16 ms 的投递间隔让相邻 TD 集
  的帧窗口天然相邻（后一套在前一套结束后开始）；
- cave 只在 ring 为空时做一次完整 setup（首 burst 或驱动复位后），ring
  非空时直接在 `prod` 写下一套 TD、不 memset、不重装上下文；
- 完成与 report 异步处理：每 16 ms 检查 completion/report，reap 已完成的
  URB，再决定 post；2 个在飞给调度留 16 ms 余量。

cave 需要的改动（`patches/iso_burst_uac84_*.S`）：

1. 把 `prod == cons` 的门从“拒绝”改成“empty → 完整 setup；非空 → 直接写”；
2. 非空路径跳过 `bl rearm_endpoint`（`0x2feb0`）、跳过 link 修正（link 已
   指向 `ring+0xf70`）；
3. 写完照旧 `prod = next`、`dsb`、门铃；cycle 用 `[x1+0x40]` 的当前值；
4. ring 到 `ring+0xf70` 时用现有 `advance` 的 Link 处理（`0x1802|cycle`，
   cycle 翻转），2 个在飞 + 16 个 buffer 也不会超过 8 槽。

app 需要的改动：

1. 把“post → eventWait → report → 下一个 post”改成 16 ms tick：
   初始 post 2 个；每 tick 若在飞 < 2 且还有 buffer，则 post 下一个；
   同时 reap 完成的 URB（report 可能一次返回多个 entry）；
2. 结束/掉线路径：先 `usbDsEndpoint_Cancel` 所有在飞请求，再 teardown；
   host 侧继续带 `--keep-alt`（v24 的收尾崩溃触发点是 host 的
   `SET_INTERFACE(0)`）；
3. 日志只保留 cheap 行（v24 的 `UAC_U2_LIGHT_LOG`）和每 burst 的 timing；
   16 ms 节拍下不能再做 dmnt dump。

判定（一次 boot，8 个 buffer）：

| 观察 | 结论 |
| --- | --- |
| host 连续收到 ≥ 8×3072B，且 burst 之间没有 ~80 ms 空档；设备 `posted=completed=8`，`done` 的 `prod/cons` 跟着前进（不再每次回 base） | **ring 连续成立**；下一步 16/32 buffer 与 PCM/时钟 |
| 仍只有第 1 个 burst，或 gap 不变 | 驱动仍在每次完成时复位；查 `0x30ff4` 的触发码与 ring 状态，回到单 burst 机制 |
| 1536B/`0x748c` 或漏服务 | 16 ms 节拍/帧对齐不对；回到单 burst 的 lead/时序 |
| 任一 crash/fatal | 停，读卡；重点看 v11 的 pending-request 崩溃是否重现 |

### B. cave 维护帧游标（后续）

- cave 在端点对象里维护“下一个可用帧号”（上一套 TD 的最后一帧 + 1），
  每次 post 直接接着排，不依赖 MFI；
- 好处：app 可以任意速度 post（不必卡 16 ms 节拍），ring 满时再等；
- 代价：cave 要读写游标、处理 wrap/cycle，还要在驱动复位后重新对齐 MFI；
  实现和验证成本都高于 A。

A 先用 16 ms 节拍验证“ring 不空就不会复位”；若 A 成立，B 只是把节拍
从 app 移到 cave，边际收益有限。

## 风险

- **v11 的 pending-request 崩溃**：alt0 teardown 时仍有在飞 ISO 请求会让
  usb sysmodule fatal。A 的结束路径必须先 cancel 再让 host 收尾；`--keep-alt`
  只能去掉 host 侧主动 alt0。
- **驱动仍可能复位**：只要某个 16 ms 窗口没有排到 TD（app 调度抖动），
  控制器就会漏服务并复位；A 用 2 个在飞 + 16 ms 余量吸收抖动，但首次
  验证仍可能看到部分 gap。
- **report 一次多个 entry**：`UsbDsReportData.report_count` 最多 8；
  app 现有的 `for (i < report_count && i < 8)` 已能处理，但 buffer→urbId
  的映射需要按 id 查找，不能假设按顺序。
- **帧 lead 32 ms** 仍是空档的一部分；A 成立后再考虑把 lead 降到 16
  （v25 的 4 ms 已证明太低）。

## v26A 候选（已离线实现）

| 项 | 值 |
| --- | --- |
| cave | `patches/iso_burst_uac84_dci9_pipe.S`，636/684 B（v23 rearm cave +16 B） |
| cave 行为 | `prod==cons` → 重放 `0x2feb0`、修 link、写 base；`prod!=cons` → 直接在 `prod` 写、不 memset、不重写 link；两条路径都进同一个 mailbox/TD 写入段 |
| app | `-DUAC_U2_BURSTS=8 -DUAC_U2_LIGHT_LOG -DUAC_U2_PIPELINE`；16 ms tick、2 个 buffer 在飞、report entry 按 urb id 匹配、失败/停滞先 cancel 在飞请求；`_uacLogSubmitState` 在 pipeline 构建里不编译 |
| NSP | `5e6c29af…`（92322B），NSO `d6480771…`，29 条 edits / cave `df43d0a8…` |
| 工作目录 | `private/analysis/UAC-u2-v26a-pipe-20261101` |
| 测试 | `tests/test_uac_u2_pipeline.py`（7 项：cave 分支/尺寸/唯一 rearm 调用 + app 结构与 cancel） |
| 预期 | 8×3072B 连续、`pipe end posted=8 completed=8`、ring `prod/cons` 前进不回 base、无 crash |

一次 boot 的判定：

| 观察 | 结论 |
| --- | --- |
| host 连续 ≥ 8×3072B、burst 之间无 ~80 ms 空档；设备 `posted=completed=8` | ring 连续成立，进入 16/32 buffer 与 PCM/时钟 |
| gap 仍 ~80–96 ms，`done` 仍回 base | 驱动仍在每次完成时复位；查 `0x30ff4` 触发码与 ring 状态 |
| 1536B/`0x748c` 或漏服务 | 16 ms 节拍/帧对齐不对；回退单 burst 时序 |
| 任一 crash/fatal | 停，读卡；重点看 v11 pending-request 崩溃 |

### 2026-11-02 00:3x 实机：管道可用，但同帧窗口漏服务

- 设备 `train begin count=8`，buf0..7 全部 `pipe post rc=0`、全部 report；
- **偶数 buf 0/2/4/6 `xfer=3072 status=3`，奇数 buf 1/3/5/7 `xfer=0 status=5`**；
  `pipe end posted=8 completed=8 bytes=12288`；
- host 只收到 4×3072B（gap 79/64/80 ms）；
- 结论：cave 对每次 post 都算 `MFI/8 + 32`，背靠背的两套 TD 落在同一帧窗口，
  一套被漏服务。管道（post/report/cancel）本身是通的。
- 收尾：usb `svcBreak`（同栈）在 host 重连后再次 `SET_INTERFACE(0)` 时出现；
  `--keep-alt` 只去掉了 probe 自己的 restore，内核重绑/枚举仍会发 alt0。

### v26B：cave 帧游标（已实现，app 不变）

1. cave（`patches/iso_burst_uac84_dci9_pipe_cursor.S`，**672/684 B**）在
   mailbox 空闲区 `ring+0xf80+0x38` 存 16-bit“下一可用帧”：
   `frame = max(MFI/8 + 32, cursor)`（游标在前才用），写完 16 帧后
   `cursor = frame + 16`；空 ring 的 memset 会把游标清零，自动回 MFI 基准；
2. app 与 v26A 相同（`BURSTS=8 + LIGHT_LOG + PIPELINE`，2 在飞、
   completion 驱动 top-up）——游标保证相邻 TD 集的帧窗口连续，不再同日而语；
3. NSP `116a1204…`（92342B），NSO `7551a37a…`，cave 比 v26A 多 36 B；
   工作目录 `private/analysis/UAC-u2-v26b-cursor-20261101`；
4. 预期：buf0/buf1 的帧窗口相邻，8 个 buffer 全部上线，gap 接近 0；
   `tests/test_uac_u2_pipeline.py` 新增 4 项（读/写顺序、scratch 偏移、
   帧选择模型、cave +36B 与指令）。
5. 收尾崩溃仍未解决，需在 app 的 alt0 处理里先 cancel，或单独研究内核
   重绑/重枚举路径。

### 2026-11-02 01:0x 实机：帧游标没有改变奇偶模式

- 设备：同样 8 post / 8 report，偶数 buf `3072/3`、奇数 buf `0/5`；
  `pipe end posted=8 completed=8 bytes=12288`；最终 ring 回 base；
- host：4×3072B（t=31/111/191/256 ms，gap 80/80/65），与 v26A 几乎相同；
- 判定：**游标没有改变行为**。消歧需要下一步之一：
  1. **诊断**：app 在每次 post 前后读 `ring+0xfb8`（游标 scratch）与
     ring 的 prod/cons/cycle（dmnt，读-only），确认游标是否被写入/读到、
     ring 是否在中途被复位；
  2. **门铃假设**：奇数 set 可能在偶数 set 的完成复位中被清掉（门铃合并 /
     服务错误复位）。候选：非空路径**不再敲门铃**，看控制器是否连续取指；
     若停止，则每个 TD 集都需要自己的门铃，“两套排队”不成立。
- 收尾：本轮无新 crash 报告（crash 21），新增 1 份 erpt `760e51fa`。

### v27 读-only 游标诊断（已离线构建）

- 构建：v26B cursor cave（672/684 B）+ app
  `-DUAC_U2_CURSOR_DIAG`；NSP `bdb80208…`（92862B），NSO `2b88e833…`；
  工作目录 `private/analysis/UAC-u2-v27-cursor-diag-20261102`；
- app 的 `_uacLogCursor(tag, seq)` 读端点对象（`base+0xFC300`：
  ring/prod/cons/cycle）与 cave 游标 scratch（`ring+0xFB8`），每个 post
  前后、每次 reap、train 结束各打一行：
  `UAC U2 cursor <tag> seq=N ring=… prod=… cons=… cycle=… cur=… rc=…`；
- 纯读：不 flush、不写；诊断会拉长 train 时间，本轮不看 gap；
- 判读：
  - `cur` 每次 +16、奇数 buffer 的 `done` 时 `cur` 在前 → cave 侧正确，
    是驱动/控制器把排队的奇数 set 清掉 → 下一步做门铃路径实验；
  - `cur` 恒 0 或不前进 → scratch 被覆盖或 cave 没读/写 → 改偏移或换
    scratch；
- 本轮只验证读数，不改数据面行为；crash 仍按老规矩停、读卡。

### 2026-11-02 01:3x v27 诊断结果：**驱动是单 transfer，流水线走不通**

- `cur` 证明游标本身工作正常：每个偶数 post 后 `prod=ring+0x200`、
  `cur = frame+16`（906→1006→1105→1205）；
- 每个奇数 post 后 `prod/cons/cur` **完全不变**——第二次
  `usbDsEndpoint_PostBufferAsync` 返回 `rc=0`，但驱动**没有调用 cave**
  （没有建 TD），随后以 `xfer=0 status=5` 完成；
- 每次 transfer 完成（`done`）后 ring 都被复位：`prod=cons=ring`、`cur=0`；
- 结论：**usb:ds 的端点 API 是单 transfer 的**。一个 transfer 在飞时再
  post 一个 buffer，驱动只会把它记成错误完成；`prod!=cons` 的流水线路径
  在真实驱动里不会被调用。v26A/v26B 的“两套 TD 排队”方案到此为止。

修正后的路线（按代价排序）：

1. **加大单次 transfer**：一个请求提交 2–4 个 3072B 段（32–64 ms 数据），
   cave 的 TD 数从固定 16 改为按请求长度；每次 transfer 的固定开销
   （32 ms lead + ~12 ms 事件 + ~20 ms report + ~12 ms loop）被摊薄，
   但 transfer 之间仍有 ~76 ms 空档，只是占空比从 16% 升到 ~45%；
2. **研究驱动为什么单 transfer**：`0x2c520` 提交路径在什么条件下跳过
   cave（忙标志/队列），是否有第二条提交路径（UVC 的 ISO 端点能持续
   排队，说明驱动本身支持多请求）；
3. 接受 ~96 ms gap，先把 PCM/时钟/与视频共存做对，再回头攻连续流。

### 2026-11-02 01:4x v28 多段单 transfer（离线构建，0 实机）

- 依据 v27：端点单 transfer，第二次 post 不达 cave。v28 不再排队，改为
  **一次请求承载 2 段 3072B（6144B = 32×192B = 32 ms）**。
- cave `patches/iso_burst_uac84_dci9_pipe_multi.S`（**676/684 B**，比 v26B
  多 4 B）：
  - 请求长度门 6144：`mov w9,#0x1800; cmp w3,w9`（6144 不是 12 位立即数）；
  - **TD 数由请求长度推导**：包循环结束条件从固定 16 次改为
    `x16 = buffer + w3(uxtw)`、`cmp x2,x16`——32 个 Isoch+ED 对；
  - 事件侧 ED 槽上界 `512 → 1024`；完成门从 `sum == 3072` 改为
    **32 位 ED 位图全满**（`cmn w6,#1`），`actual` 仍累加供日志；
  - 帧游标不变，写完一套后 `cursor = frame + 32`。
- 为什么先到 2 段：事件位图是 32 位，32 个 ED 正好填满；4 段需要 64 位
  位图或分块完成（留 v29）。
- app：`UAC_U2_SEGMENTS`（1..2）、`UAC_U2_BURST_BYTES = 192*16*segments`、
  `UAC_U2_BUF_BYTES` 按页对齐；多段构建与 `UAC_U2_PIPELINE` 互斥
  （编译期 `#error`），并打印 `UAC U2 multi segments=2 size=6144`。
- 构建：`-DUAC_U2_SEGMENTS=2 -DUAC_U2_BURSTS=1 -DUAC_U2_LIGHT_LOG`；NSP
  `85861e90…`（92167B）、NSO `149d21ec…`；payload 29 条 / cave
  `f5f7776b…`；工作目录 `private/analysis/UAC-u2-v28-multi-20261102`。
- 期望（一次 boot）：`post rc=0 size=6144`、`UAC U2 multi segments=2
  size=6144`、`report req=6144 xfer=6144 status=3`、`complete 6144`；host
  一个 32-packet URB 收满 6144B；线 gap ≈ 32 ms 数据 + ~76 ms 固定开销
  （占空比 ~30%，v24 为 16%）。
- 判别/停止：`PostBufferAsync` 拒绝 6144 或 cave 未被进入（无 TD、无
  completion）→ 驱动/控制器对单次 transfer 长度有上限，记录 rc 后停；
  崩溃即停、读卡。**未部署、0 实机。**

### 2026-11-02 13:1x v28 实机：6144B 单次 transfer **挂死**，上限仍是 3072B

- host：`claim/alt1/SET_CUR` ok；`packets=32`、31 个 URB 全部
  `valid=32 bad=0 bytes=0`，`done ... bytes=0`；
- 设备：precheck 通过（`word=0x00c00584 dci=9 installed=1`）；
  `train begin count=1`；`UAC U2 multi segments=2 size=6144`；
  `post begin seq=1/1` 之后日志中断——**`PostBufferAsync` 没有返回**
  （无 `post rc`），控制台死机，用户硬关机；
- 无新 crash/erpt/fatal（27 / 20 文件+dumps / 14 与部署前相同）；
- 判定：**6144B / 32 对 TD 的单次请求在 usb:ds 提交路径内挂死**。不是干净
  拒绝（没有 rc），所以“加大单次 transfer”在当前驱动上走不通；单次请求
  上限仍是 3072B（16 对 TD，v24 基线）。不要重试 6144。
- 下一步（离线）：读 `0x30364` 之后的 ISO 提交/收尾路径，找 16-TD 或
  `0x200` 的固定假设，解释挂死来源；在找到上限来源前不再试 6144。备选是
  接受 ~96 ms gap，先做 PCM/时钟/与视频共存。

### 2026-11-02 14:1x 提交路径拆解与 v28b（20 帧，离线）

- 拆解 `usb.elf`：
  - `0x2c520`：DMA map（`0x3c50`）→ entry 入队（8 项）→ 条件满足时
    `blr [vtable+136]`（=`0x302e0`）提交一个请求；**提交后没有等待**，
    解锁后直接返回；
  - 传给 cave 的 `w3 = min(requested, controller max)`；6144 能过 cave 的
    长度门，说明没有被驱动截断；
  - cave 路径：`0x30364` → 写 TD → `b 0x31c74` doorbell → `ret` 回
    `0x2c668`；
  - `0x2feb0`（rearm/commit）与 `0x30ff4`（错误完成）里的 poll 都是
    **2000 × 50 ns 上限**，不是死循环；
  - `0x30b50` 构建的 endpoint context **没有 TD 计数/环大小字段**；ring
    固定 `0x1000`，驱动的 link 在 `+0xff0`（cave 用 `+0xf70`，只有 ≥123
    对 TD 时才会碰到，属潜在不一致）；
  - 全路径没找到 16-TD / `0x200` 常量 → 挂死更可能来自**控制器/硬件**对
    32-TD 单请求的处理，而不是驱动线程。
- v28b 候选（限定 20 帧）：一次 3840B（20×192B），cave
  `iso_burst_uac84_dci9_pipe_multi20.S`（672/684B，与 v26B 同尺寸）；长度门
  `cmp w3,#0xf00`（3840 是 12 位立即数）、ED 槽上界 `0x280`、完成门
  `cmp w4,#0xf00`；app `-DUAC_U2_FRAMES=20`；NSP `b9b5459b…`（92135B）。
- 判定：若同样挂死 → 单次上限在 **17–20 帧**，连续流在本驱动上关闭；
  若通过 → 上限在 **21–32 帧**，可再二分。

### 2026-11-02 15:5x v28b 实机：20 帧（3840B）也挂死，上限 17–19 帧

- host：`claim/alt1/SET_CUR` ok；`packets=20`、50 个 URB 全部
  `valid=20 bad=0 bytes=0`，`done ... bytes=0`；
- 设备：precheck 通过；`train begin count=1`；`UAC U2 multi frames=20
  size=3840`；`post begin seq=1/1` 之后日志中断——`PostBufferAsync` 没有
  返回；控制台死机，但 **USB 链路没有掉**（guest 仍看得到 `1209:ca57`）；
- 无新 crash/erpt/fatal（27 / 20 文件+dumps / 14）；
- 判定：**16 帧（3072B）可用、20 帧（3840B）卡死 → 单次请求上限在
  17–19 帧**。“加大单次 transfer”路线关闭；连续流只剩“另找驱动提交入口
  （UVC 式队列）”或“改驱动”两条路，当前不做。
- 下一步：回到 v24 基线（16 帧、gap ~96 ms），做 PCM/时钟/与视频共存；
  连续流挂账。不要重试 >16 帧的单次请求。

### 2026-11-02 16:3x v29a 驱动队列补丁（离线，诊断）

拆解结论：驱动队列是**串行**的——`0x2c520` 只在队列为空时提交
（`0x2c628` 的 `b.ne`），`0x2c690` 在完成清理后于 `0x2c808–0x2c848`
自动提交下一个排队项。v26A/v27 的第二个 post 没进 cave，就是因为这个门。

v29a 补丁（usb.elf，3 处）：
- `0x0c4` 放 3 条指令的 stub：`sub w9,w12,#1`（w12 = 追加后的 tail，故
  w9 = 刚追加的 entry）、`and w9,w9,#7`、`b 0x2c62c`；
- `0x2c628`：`b.ne 0x2c668` → `b 0x0c4`（总是走提交块）；
- `0x2c80c`：`cbz w8,0x2c84c` → `b 0x2c84c`（跳过完成的自动提交，由 app
  pipeline 保持 2 个在飞）。

配置：cave 仍用 v26B cursor（672/684B），app `BURSTS=8 + LIGHT_LOG +
PIPELINE + CURSOR_DIAG`；NSP `feaa2d55…`（92899B），payload 32 条。

**这一轮只回答两个问题**：第二个 post 是否被驱动提交（cursor 行
`prod=+0x200` → `+0x400`、`cur` 前进），以及控制器是否接受两个 16-TD 集
（挂死 = 不接受，同 v28 类）。共享 mailbox（magic/done/bitmap/sum/first
TRB 都在 `ring+0xf80`）会导致完成账本错误，v29a 不解决；通过后再做 v29b
的 per-set 账本。

### 2026-11-02 16:20 v29a 实机：队列补丁成立，2 在飞被接受

- host：`claim/alt1/SET_CUR` ok、exit=0；62 transfers、`valid=249 bad=743
  **bytes=21504**`（t=34–306 ms 七个 3072B 片段，之后为空）；
- 设备 cursor：`post buf=0` → `prod=ring+0x200 cur=476`；`post buf=1`
  → `prod=ring+0x400 cur=494`——**第二个 post 确实进了 cave**；
- 完成：`done buf=0 3072/3`、`done buf=1 0/status=2`；后续 post 到
  `+0x600/+0x800`，完成返回 status=2/5，ring 在另一套 TD 排队时被复位；
  `pipe end posted=8 completed=8 bytes=3840`（app 只记到 3840，host 实收
  21504）；
- 无死机；新增 1 份 erpt `2162-0004`（Data Abort，16:20）；
- 判定：**队列补丁 + 控制器 2 在飞成立**（v24 同窗口 12288B → 21504B）。
  剩余问题是账本：cave mailbox 共享、driver 对仍在飞的 entry 返回
  status=2、完成清理把另一套排队 TD 的 ring 复位。
- v29b：per-set mailbox（bitmap/sum/first TRB 各两套）、定位并阻止复位
  来源（`0x2c690` 清理 / `0x2a8b0` / 错误路径）、app 只把 status=3 当完成。

### 2026-11-02 16:2x v29b per-set mailbox（离线）

- v29a 证明控制器接受两个 16-TD 集（host 21504B），但单一 mailbox 把两套的
  ED 混在一起：完成返回 status=2/5，驱动的错误路径把另一套排队 TD 的 ring
  复位。
- v29b cave `patches/iso_burst_uac84_dci9_pipe_sets.S`（**680/684B**）：
  - 每套一个 mailbox：A 在 `ring+0xf80`、B 在 `ring+0xfc0`；
  - enter 用 `(prod - ring) >> 9 & 1` 选套，event 用 ED 的 ring 偏移选套；
  - 帧游标改为全局 `ring+0xfb8`（x17），不再放进 mailbox；
  - 空间来源：去掉 interval 检查（描述符固定 4）与首控制镜像
    `mailbox+0x3c`（B 套会写到 `ring+0xffc`，落在驱动 link TRB `0xff0`
    内，必须去掉）。
- app：pipeline 不再把 `urb_status == 2` 的 report 当完成，缓冲区留在飞
  等 3 或错误码。
- 构建：NSP `203519a7…`（92812B）、NSO `8faede4c…`；32 条 payload；
  工作目录 `private/analysis/UAC-u2-v29b-sets-20261102`。
- 判定：两套各自 `3072/3`、无复位、流超过 306ms、host >21504B → 继续
  v29c（lead/节奏）；若复位仍在 → 下一个目标是驱动 report/complete 路径。

### 2026-11-02 16:31 v29b 实机：per-set mailbox 成立，2 在飞稳定

- host：`claim/alt1/SET_CUR` ok、exit=0；62 transfers、`valid=281 bad=711
  bytes=24576`（t=33–305 ms 八个 3072B 片段）；
- 设备：8 个 post、8 个完成**全部 `xfer=3072 status=3`**；
  `pipe end posted=8 completed=8 bytes=24576`（与 host 完全相等）；
- ring：prod 从 `+0x200` 一路推进到 `+0xc00`，cons 逐步跟随，**两套之间
  没有 `prod=cons=ring` 复位**；只有最后一次完成后的收尾复位；
- cursor：每套 +16 前进，收尾回 0；
- 无新 crash/erpt/fatal（27 / 21 项 / 14 不变）；
- 判定：**per-set mailbox 修好了完成账本**，2 在飞可以稳定跑完 8 个 buffer；
  数据 128 ms / 墙钟 272 ms ≈ **47% 占空比**（v24 单请求 16.7%）。train 仍受
  `BURSTS=8` 限制，不是持续流。
- 下一步 v29c：放宽 train 长度（或按时间持续投递）、测稳态占空比/丢包，
  再试 lead 32→16；在飞仍限 2 套（mailbox 只有 A/B）。

### 2026-11-02 16:4x v29c 滚动流（离线）

- v29b 的 train 被 `BURSTS=8` 限在 272ms；v29c 把“train 长度”和“缓冲池”
  拆开：
  - `UAC_U2_STREAM_POSTS`（默认 = TRAIN_POSTS）决定总 post 数，本次 64；
  - 8 槽缓冲池循环复用，但**只有上一请求完成后的槽**才会再次投递
    （`free_slot`），在飞仍 ≤2；
- cave 与驱动队列补丁同 v29b（680/684B + 3 处 usb.elf 编辑）；
- 风险：A23 曾因“完成后立刻复用同一 DMA 缓冲”崩 usb（`0xf601` + map
  svcBreak）。这里复用间隔约 4 个 post（~200ms），驱动已 unmap；若复用仍
  崩，前 1s 日志会暴露；
- 构建：NSP `b1f812e4…`（92483B）、NSO `0aa4f494…`；工作目录
  `private/analysis/UAC-u2-v29c-stream-20261102`；
- host：`--packets 16 --transfers 8 --rearm --max-urbs 256
  --timeout-ms 3000 --keep-alt`；
- 判定：64/64 完成、设备 bytes = host bytes（~196608）、无复位/停滞，
  测稳态占空比；之后再试 lead 32→16 与 3 在飞。

### 2026-11-02 16:54 v29c 实机：稳态成立，TD 环 wrap 是下一个墙

- host：`claim/alt1/SET_CUR` ok、exit=0；187 transfers、`valid=2073
  bad=919 **bytes=187968**`，数据 t=33–2097 ms（持续 ~2.1s）；
- 设备：`pipe end posted=64 completed=63 bytes=187392`；61 个
  `xfer=3072 status=3`，随后 2 个 `status=5`、1 个 stall→cancel；
- wrap：post 63 `prod=ring+0xddf0` → post 64 `prod=ring+0x080` 且
  `cycle` 翻转——cave 在 `+0xf70`（自己的 link 槽）回卷，而驱动在
  `+0xff0` 写 link，且一套 16-TD 被拆到环首；两次 status=5 正好落在 wrap；
- 缓冲复用没有崩（8 槽、2 在飞、复用间隔 ~4 post）；
- 首次开机时 VM 未 suspend，控制台崩溃（16:52 的 crash/fatal/erpt，
  已归档）；按纪律重开后本次运行本身无崩溃；
- 下一步 v29d：对齐 link 槽。两个选项——
  1. patch 驱动 `0x2feb0`/`0x30ff4` 里的 link 常量 `0xff0 → 0xf70`，让
     controller 在 cave 的 link 处回卷（mailbox 在 `0xf80..0xfdf`，位于
     link 之后，不再被取指）；
  2. 在 prod 接近 `+0xf70` 时先 rearm/复位，保证一套 TD 不跨 wrap。
  修好后重跑 64/128 post 看是否 100%，再谈 lead 32→16 与 3 在飞。

### 2026-11-02 18:3x v29d link 槽对齐（离线）

v29c 的 wrap 失败不只是“驱动 link 在 `+0xff0`、cave link 在 `+0xf70`”的
不一致：`+0xf70` 落在第 8 套 0x200 TD（0xe00..0xfff）内部，一套 TD 在 link
处被拆开。`advance` 在 link 处额外写一个 16 B Link TRB，但不把它算进 32 个
TRB，于是每次 wrap 把写游标推后 **0x90**（实测 0x90 → 0x120 → 0x1b0 …）。

一旦某套的起点不再 0x200 对齐，它的 ED 偏移 `>>9 &1` 就跨两个 block，A/B
mailbox 各记一部分，`sum == 3072` 永远不成立 → status=5（v29c 的 2 个）。

修法：把 link 放到 `+0xc00`——六套 0x200 正好对齐；六是偶数，wrap 后 A/B
仍交替（若用 8 套反而回到奇数相位）。`0xc00..0xfff` 不再被取指，mailbox
`0xf80/0xfc0` 与 cursor `0xfb8` 留在外面。

- cave：`patches/iso_burst_uac84_dci9_pipe_wrap.S`（**680/684 B**），三处
  立即数（x13、ED 上界、unwrapped tag）；
- 驱动：四处 setup/error（`0x2f530`、`0x2ff40`、`0x30578`、`0x310c8`）的
  `add x9,x8,#0xff0` → `#0xc00` 与两个清零（`0xff0/0xff8` →
  `0xc00/0xc08`），共 **12 条**；
- app：`BURSTS=8 + STREAM_POSTS=64 + LIGHT_LOG + PIPELINE + CURSOR_DIAG`；
- 构建：NSP `287907b8…`（92628 B）、NSO `36b801d7…`，44 条 edits；工作目录
  `private/analysis/UAC-u2-v29d-wrap-20261102`；
- 测试：`tests/test_uac_u2_wrap.py`（10 项：cave 立即数、组装尺寸、12 条编码、
  64 post 对齐/双在飞 mailbox 模型）。

判定：64/64 完成、wrap 后不再 status=5 → 100%。若控制器在六套之前就报
status=5，说明它不接受提前的 link；下一步把 mailbox 移出 ring（或按 set 序号
记账），不再继续挪 link。

### 2026-11-02 19:28 v29d 实机：wrap 修好，空 ring/underrun 提前停流

- host：`claim/alt1/SET_CUR` ok、exit=0；187 transfers、`valid=697 bad=2295
  **bytes=57024**`，数据 t=33–801 ms（18 个完整 3072 B + 192 B），之后空。
- 设备：`posted=22 completed=20 bytes=55296`——18 个 `3072/3`、2 个
  `xfer=0 status=5`；seq 11 与 seq 17 两次 wrap 都是 `prod=+0xa00 → +0x000`、
  cycle 1→0 / 0→1，wrap 后的 sets 继续 `3072/3`。**一套 TD 不再被拆开，
  A/B mailbox 相位保持**。
- 失败点：第一次 `status=5` 在 seq 3（第 3 个 post），驱动把 ring 复位到
  base；第二次在 seq 21（sets `+0x600/+0x800` 已排队）后 100 ms 无完成，
  app 取消 2 个在飞请求。两次都不在 wrap 上。
- 判定：**link 对齐成立**；ring 在“2 在飞 + 约 34–40 ms/post”的节奏下会被
  控制器跑空，一次 `status=5` 后 app 只等完成、不再 re-arm，流停住。
- 下一步 v29e：16 ms tick 投递（不等完成）、`status=5` 后 cancel+重投、
  lead 32→16；3 在飞需要第三个 mailbox。
- 无 crash/fatal，USB 链路未掉；新增 erpt `8bb5ccee…` 已归档并删除；卡恢复
  `52069a44…`、删日志、安全弹出。

### 2026-11-02 19:4x v29e 四 mailbox / 三在飞（离线）

v29d 的失败点不在 wrap：一次空 ring re-arm 后（seq 3），一次在 sets
`+0x600/+0x800` 已排队时（seq 21），两次都让端点停止完成。2 个在飞 +
约 30 ms/post 留不住 TD；一次 `status=5` 后 app 只等完成，不再投递。

- cave `patches/iso_burst_uac84_dci9_pipe_quad.S`（**680/684 B**）：
  四个 mailbox 在 `+0xf00/+0xf40/+0xf80/+0xfc0`，`set = (offset >> 9) & 3`；
  三套连续 set 必得三个不同 mailbox，wrap（block 5 → block 0）后仍成立；
  done 门改为在选中的 mailbox 上检查（v29d 的 cave 检查固定的 mailbox 0）。
- app：`posted - completed < 3`；非 3 完成时 `usbDsEndpoint_Cancel` 剩余在飞
  请求、释放槽并 `++completed`，下一次 post 走空 ring 的 re-arm；日志
  `UAC U2 pipe recover cancelled=%u`。
- 构建：NSP `0607f72b…`（92906 B）、NSO `283668f3…`，44 条 edits；工作目录
  `private/analysis/UAC-u2-v29e-quad-20261102`；新增
  `tests/test_uac_u2_quad.py`（7 项：四 mailbox、三连续 set 不同 mailbox、
  done 门顺序、组装尺寸、三在飞、恢复分支）。
- 判定：≥64 posts、0 `status=5`，或 recover 行后继续；若仍提前停，记录
  `posted/completed`、wrap 位置与 recover 行，再决定 4 在飞或 frame 调度。

### 2026-11-02 19:45 v29e 实机：三在飞 + 恢复，跑满 64 posts

- host：`claim/alt1/SET_CUR` ok、exit=0；187 transfers、`valid=2265 bad=727
  **bytes=180672**`，数据 t=33–2673 ms（110 个有数据的 URB），之后空。
- 设备：**posted=64 completed=64 bytes=172032**——56 个 `3072/3`、4 个
  `xfer=0 status=5`，每个 `status=5` 后都有 `UAC U2 pipe recover cancelled=1`
  并继续到 64 posts。无 crash/fatal/erpt，USB 链路未掉。
- rearm：seq 37/44/54 的 post 把 `prod/cons/cur` 复位到 base（`cur=0`），
  紧随其后的那套以 `status=5` 结束；4 次 miss 都落在这种 rearm 之后。
- 判定：**3 在飞 + 4 mailbox 成立，恢复路径成立**（56/64 = 87.5% 数据）。
  剩余 miss 不是 wrap，而是 cave 在空 ring 上 re-arm 时仍有完成 pending：
  `prod==cons` 只表示没有 TD，不表示没有完成。
- 下一步 v29f：普通空 ring 直接写 base（只在驱动复位后 re-arm），或加到
  4 在飞；之后再 lead 32→16。判定 0 `status=5`、bytes=196608。

### 2026-11-02 20:3x v29f miss 容忍 / stall 恢复（离线）

v29e 的 4 次 miss 都紧跟在一套 `status=5` 之后：app 立即 cancel 其余在飞请求，
ring 被复位，下一套再走空 ring 的 re-arm，于是又 miss。v29f 不再主动 cancel：

- `status=5` 只释放失败槽、`++misses`，日志 `UAC U2 pipe miss buf=%u status=%u`；
  循环立刻补投一套，其余在飞请求保持；
- 100 ms 无完成时走 stall 路径：`usbDsEndpoint_Cancel`、释放其余槽、
  `++recoveries`，日志 `UAC U2 pipe stall recover cancelled=%u rc=0x%x`，
  然后继续投递，最多 8 次；
- end 行改为
  `pipe end posted=%u completed=%u bytes=%u misses=%u recoveries=%u`；
- cave/mailbox 与 v29e 相同（quad 680/684 B）；app 其余 defines 不变。
- 构建：NSP `7b242bf8…`（92934 B）、NSO `eb433668…`，44 条 edits；工作目录
  `private/analysis/UAC-u2-v29f-miss-20261102`；`tests/test_uac_u2_quad.py`
  改为检查 miss 分支与 stall 分支。
- host：`--packets 16 --transfers 8 --rearm --max-urbs 512 --timeout-ms 5000
  --keep-alt`（给 stall 恢复留出跑完 64 posts 的窗口）。
- 判定：64/64、0 `status=5`、device bytes → 196608；若 stall recover 后继续
  也算恢复成立。仍 miss 时再加到 4 在飞或 lead 32→16。

### 2026-11-02 21:00 v29f 实机：miss 容忍成立，收尾崩溃

- host：`claim/alt1/SET_CUR` ok、exit=0；312 transfers、`valid=2265 bad=2727
  **bytes=187392**`，数据 t=34–2610 ms（111 个有数据的 URB），**host bytes 与
  设备 bytes 完全相等**。
- 设备：**posted=64 completed=64 bytes=187392 misses=3 recoveries=0**——
  61 个 `3072/3`、3 个 `xfer=0 status=5`；每个 miss 后只有
  `pipe miss buf=…`，没有 cancel、没有 stall 恢复，流继续到 64 posts。
- 3 次 miss 仍跟在 cave 的空 ring re-arm 后（seq 35/53/57：`prod/cons/cur`
  复位、`cur=0`），每次 wipe 一套在飞 set；但不再引发连锁。
- **收尾崩溃**：`pipe end` 之后 `USB host disconnected` → `connected`，
  重复 `SET_INTERFACE(0)`，usb sysmodule User Break（base+0x19280，fatal
  PC +0x19254 / LR +0x177f4）；crash/fatal `01793624628` 已归档，无新 erpt。
- 判定：**数据路径最好一轮**（61 段、host==device、3/64 miss）；miss 容忍
  成立。剩余问题：收尾 `SET_INTERFACE(0)` 崩溃（第一优先）与 3 次 rearm 丢套。
- 下一步 v29g：断开时先 cancel/清端点状态；必要时隔离 `SET_INTERFACE(0)`
  路径；之后再 4 在飞或 lead 16。

### 2026-11-02 21:0x v29g 收尾 cancel（离线）

v29f 的数据路径最好（64/64、61 段、host==device），但 `pipe end` 之后
host 断开/重连、重复 `SET_INTERFACE(0)`，usb sysmodule 在 `+0x1927c` 以
User Break 崩溃；栈是 DMA map/submit 路径（`0x2c584 → 0x2a3f4 → 0x2a464`）。
怀疑 alt0 重装端点时仍有排队/映射的请求。

- app：`UAC_ACT_STOP`（alt0）在 `_ctrlAck` 前 `usbDsEndpoint_Cancel`，
  `eventWait` 100 ms + `GetReportData` 收掉一份 report，日志
  `UAC U2 teardown cancel rc=0x%x wait=0x%x`；
- 数据路径与 v29f 相同（3 在飞、miss 容忍、stall 恢复），cave/mailbox 不变；
- 构建：NSP `a599149a…`（92541 B）、NSO `d5b8c6db…`，44 条 edits；工作目录
  `private/analysis/UAC-u2-v29g-teardown-20261102`；新增 teardown 测试
  （cancel 在 ACK 之前、包含 GetReportData）。
- 判定：数据仍 64/64、host==device；收尾无 crash/fatal。若仍崩，下一步隔离
  `SET_INTERFACE(0)` 路径或 patch 断言点。

### 2026-11-02 21:10 v29g 实机：数据 63 段，alt0 cancel 执行但仍崩

- host：`claim/alt1/SET_CUR` ok、exit=0；312 transfers、`valid=2273 bad=2719
  **bytes=193536**`，数据 t=33–2673 ms；host bytes 与设备 bytes 相等。
- 设备：**posted=64 completed=64 bytes=193536 misses=1 recoveries=0**——
  63 个 `3072/3`、1 个 `status=5`（单套丢失，流继续）。
- 收尾：`UAC_ACT_STOP` 的 cancel 执行了
  `UAC U2 teardown cancel rc=0x0 wait=0xea01`（没有 pending report 可收），
  随后 host 断开/重连、重复 `SET_INTERFACE(0)`，仍在 `+0x1927c` User Break；
  crash/fatal `01793625172`、erpt `cf451457` 已归档。
- 判定：**数据最好的一轮**；**app 侧 alt0 cancel 不能规避崩溃**，问题在
  usb:ds 自己的 alt0/DMA-map 路径。
- 下一步 v29h：隔离 AS 的 `SET_INTERFACE(0)`（stall 不 ACK）；或离线确认
  `0x9448 → 0x9650` 断言点的安全跳过；或先接受收尾崩溃、把 miss 降到 0。

### 2026-11-02 21:2x 收尾崩溃分析 + v29h map-soft（离线）

崩溃签名（v29f/v29g）：`PC +0x1927c`（`svc #0x26`）、`LR +0x9668`，栈
`0x944c → 0x9514 → 0x9534 → 0x9560 → 0x40d0 → 0x3ce0 → 0x2c584 → 0x2a3f4
→ 0x2a464`。

- `0x9650` 是 abort helper：`bl 0x1927c`；`0x9370` 是 panic 报告/落盘函数，
  `0x9448` 调用 `0x9650`；`0x9540`/`0x9520`/`0x94b0` 是 panic 入口链。
- `0x40c8..0x40d8` 是 5 个 `bl 0x9540` 的 panic stub；本次命中的是 `0x40d0`。
- 全文件里只有 `0x3fe0` 的 `cbz x0, 0x40d0` 跳到这个 stub：
  `0x3fd0` 调 `0x3140`（全局分配器 `0x33f000 → 0xa410`）申请 **0x80 B** 的
  IOVA 节点；返回 0 就 panic。
- 因此崩溃不是“状态断言”，而是 **IOVA 节点分配失败**：alt0 重装端点需要
  再 map 一次，节点池已被前面的请求/复位耗尽（与 A23 的 busy-map 泄漏同类），
  usb:ds 直接 abort 整机。
- app 侧 cancel 不能改变分配器状态，所以 v29g 的
  `teardown cancel rc=0x0 wait=0xea01` 之后仍然崩。

v29h 只改一处驱动：`0x3fe0` 的 `cbz x0, 0x40d0` → `cbz x0, 0x409c`。
`0x409c` 是失败记账/返回路径（`[x24,#72]++` 后返回 0），map 失败变成
`0x19a8c` 错误返回给 submit 路径，而不是 `svcBreak`。

- 构建：`--driver-map-soft`，45 条 edits，NSP `9610b3a0…`（92589 B）、
  NSO `b136b181…`；工作目录 `private/analysis/UAC-u2-v29h-map-soft-20261102`；
  `tests/test_uac_u2_quad.py` 增加 map-soft 编码/目标测试。
- 判定：数据仍 64/64、host==device；alt0 可以报错，但**不得**产生
  crash/fatal；若仍崩，说明还有第二个 panic stub 被命中。

### 2026-11-02 22:16 v29h 实机：收尾崩溃关闭，数据 62 段

- host：`claim/alt1/SET_CUR` ok、exit=0；312 transfers、`valid=2329 bad=2663
  **bytes=190464**`，数据 t=33–2769 ms；host bytes 与设备 bytes 相等。
- 设备：**posted=64 completed=64 bytes=190464 misses=2 recoveries=0**——
  62 个 `3072/3`、2 个 `status=5`（单套丢失）。
- 收尾：`UAC U2 teardown cancel` 后 alt0 走 map-soft 的错误返回，
  **没有 crash/fatal**（22/15/2 不变），控制台留在主界面；新增 1 份 erpt
  `8f0c9c7b` 已归档并从卡删除。
- 判定：**v16 起的 `SET_INTERFACE(0)` 收尾崩溃关闭**（IOVA 节点耗尽改为
  错误返回）；数据 62 段、host==device。剩余：2 次 miss、~47% 占空比。

### 2026-11-02 22:2x v29i 四套环 / 四在飞（离线）

v29h 之后收尾崩溃关闭，剩 2 次单套 miss。四在飞需要四个连续 set 在整环周期内
落到四个不同 mailbox：6 套环上 block `3,4,5,0` 的 `&3` 是 `3,0,1,0`，两套
共享 mailbox 0；所以 v29i 把环收成 4 套（link `+0x800`），block
`0,1,2,3`，wrap `3→0` 仍唯一。

- cave：`patches/iso_burst_uac84_dci9_pipe_quad4.S`（680/684 B），三处
  `0xc00`→`0x800`；mailbox/游标位置不变；
- 驱动：12 条 link 编辑改为 `0x800/0x808`（builder `--link-slot 0x800`），
  另有 v29h 的 map-soft 编辑，共 45 条；
- app：`posted - completed < 4`；其余（miss 容忍、stall 恢复、alt0 cancel）
  不变；
- 构建：NSP `35f49d8e…`（92589 B）、NSO `996738db…`；工作目录
  `private/analysis/UAC-u2-v29i-four-20261102`；新增四套环/链接槽测试。
- 判定：64/64、0 miss、host==device（196608）；alt0 仍不得 crash。

### 2026-11-02 22:30 v29i 实机：4 在飞/4 套环未降低 miss

- host：`claim/alt1/SET_CUR` ok、exit=0；312 transfers、`valid=2233 bad=2759
  **bytes=187392**`，数据 t=33–2706 ms；host==device。
- 设备：**posted=64 completed=64 bytes=187392 misses=3 recoveries=0**——
  61 个 `3072/3`、3 个 `status=5`；每次 miss 前都出现 ring 复位
  （`prod=cons=cur=0`）。
- 收尾：alt0 仍走 map-soft 错误返回，无 crash/fatal，无新报告。
- 判定：**4 在飞没有降 miss**（v29h 2 → v29i 3）；4 套环丢掉 6 套的缓冲
  深度，负结果。回退 v29h 配置，只改 lead（v29j）。

### 2026-11-02 22:3x v29j lead 16（离线）

v29i（4 在飞/4 套环）是负结果，miss 2→3。v29j 回到 v29h 的数据配置（3 在飞、
6 套环、link `+0xc00`、quad mailbox、miss 容忍、stall 恢复、alt0 cancel、
map-soft），只改 TD 帧 lead：`MFI/8 + 32` → `+16`。

- cave：`patches/iso_burst_uac84_dci9_pipe_quad16.S`（680/684 B），
  `add w9, w9, #32` → `#16`；
- app：`posted - completed < 3`；
- 驱动：45 条 edits（12 条 link `+0xc00` + map-soft + 3 queue）；
- 构建：NSP `b6e80871…`（92589 B）、NSO `74fa23da…`；工作目录
  `private/analysis/UAC-u2-v29j-lead16-20261102`；新增 lead-16 cave 测试。
- 判定：64/64、0 miss、host==device（196608）；若 miss 更多或出现 `0x748c`
  类漏服务，说明 16 太小，下一步试 24 或回 32。

### 2026-11-02 22:44 v29j 实机：lead 16 太小

- host：`claim/alt1/SET_CUR` ok、exit=0；312 transfers、`valid=1601 bad=3391
  **bytes=170688**`，数据 t=33–2898 ms。
- 设备：**posted=64 completed=64 bytes=165888 misses=4 recoveries=2**——
  54 个 `3072/3`、4 个 `status=5`；两次 100 ms stall 各 cancel 3 个请求。
- 收尾：alt0 仍走 map-soft，无 crash/fatal/erpt。
- 判定：**lead 16 太小**（miss 2→4、段数 62→54）；current best 仍是 v29h
  （lead 32）。下一步试 40/48，或诊断 ring 复位来源。

### 2026-11-03 08:5x v29k lead 40（离线）

v29j 证明 lead 16 太小（miss 2→4、2 次 stall），v29h 的 lead 32 仍是最好。
v29k 回到 v29h 的全部数据配置（3 在飞、6 套环、link `+0xc00`、quad mailbox、
miss 容忍、stall 恢复、alt0 cancel、map-soft），只把 TD 帧 lead 从 32 提到 40：
`add w9, w9, #32` → `#40`。

- cave：`patches/iso_burst_uac84_dci9_pipe_quad40.S`（680/684 B）；与 v29j
  cave 逐字比较只有 `+0x68e10` 一个字不同（`0x11004129` → `0x1100a129`）；
- app：`posted - completed < 3`；驱动 45 条 edits（12 条 link `+0xc00` +
  map-soft + 3 queue）与 v29h 相同；
- 构建：NSP `f05f72a1…`（92589 B）、NSO `b48f0435…`；工作目录
  `private/analysis/UAC-u2-v29k-lead40-20261103`；`tests/test_uac_u2_quad.py`
  增加 lead-40 用例（编码、只差一个字、680 B）。
- 判定：≥62 段、0 `status=5`、host==device（196608），alt0 不崩；若 40 更差，
  说明 lead 不是杠杆，转 ring 复位诊断。

### 2026-11-03 12:0x v29k 实机：开机枚举 alt0 崩溃（无数据）

- 部署 `f05f72a1…` 后第一次开机；VM（Parallels Debian 13）未 suspend 就保持
  attach，Switch 开机时 guest 立即枚举 `1209:ca57`（12:06:50），uvcvideo
  probe 控制超时（-110），设备 12:07:34 断开。
- 设备日志（766 B）：`UAC u2 patch result=0 record=44 last-rc=0x0`（45 条
  edits 全部写入）、4 次 `SET_INTERFACE(0)`（2 次 app 因 wIndex mismatch
  忽略、1 次 ignored、1 次 action=4 rate=48000）、
  `UAC U2 teardown cancel rc=0x0 wait=0xea01`；**没有任何 `UAC U2 post`**，
  probe 未运行。
- 崩溃：usb sysmodule fatal `2162-0002`，PC `+0x1927c`、LR `+0x9668`，栈与
  v29f/v29g 相同（`0x40d0←0x3ce0`）。`0x40d0` 是 stub `0x40cc` 中
  `bl 0x9540` 的返回地址，即 `0x3dac: cbz w0, 0x40cc`（`bl 0x4a20` 返回
  0）的 panic；map-soft 的 `0x3fe0`（返回地址会是 `0x40d4`）不是本次入口。
- 判定：**run 无效**（0 probe、0 数据），v29k 未验证；直接原因是开机时 VM
  仍 attach，同时暴露第二个 panic 入口 `0x3dac→0x40cc`，map-soft 没有关闭
  alt0 崩溃。
- 恢复：安全 `52069a44…` 已恢复，日志与 crash `01793678846` / fatal
  `01793678845` 已归档并删除，12:08 弹出。证据
  `private/runs/UAC-u2-v29k-lead40-20261103`、
  `private/card-cycles/20261103-u2-v29k-lead40`。
- 下一步：v29l = lead 40 + `0x3dac → 0x409c`（map-soft-2）；实机前 Switch
  关机、VM suspend/detach，主界面后再 attach。

### 2026-11-03 12:2x v29l map-soft-2（离线）

v29k 的开机崩溃栈（`0x40d0←0x3ce0`）对应 `0x3dac` 的
`cbz w0, 0x40cc`（`bl 0x4a20` 返回 0），不是 v29h map-soft 的 `0x3fe0`
（其返回地址会是 `0x40d4`）。v29l 在 v29k 之上只加一条驱动编辑：
`0x3dac` → `0x409c`，让 `0x4a20` 失败也走同一个错误收尾
（`[x24,#72]++` 后返回 0，调用者 `0x3ce0 cbz x0` 走 `0x3d1c` → `0x19a8c`）。

- 驱动 46 条 edits：v29k 的 45 条 + `0x3dac`（`00190034` → `80170034`）；
- cave 与 app 不变：quad40（lead 40，680/684 B）、3 在飞、`STREAM_POSTS=64`；
- 构建：NSP `49956ad1…`（92676 B）、NSO `4f9aedbf…`；工作目录
  `private/analysis/UAC-u2-v29l-map-soft2-20261103`；`tests/test_uac_u2_quad.py`
  增加 map-soft-2 用例（编码、跳转目标 0x409c）；
- 判定：alt0/IOVA 两个 panic 入口都变成错误返回；数据路径仍回答 lead 40
  的问题（≥62 段、host==device、alt0 不崩）。

### 2026-11-03 12:3x v29l 实机：lead 40 负结果

- host：`rc=0`，claim/alt1/`SET_CUR` ok；312 transfers、`valid=2113
  bad=2879 **bytes=179712**`，数据 t=49–2449 ms。
- 设备：**posted=64 completed=64 bytes=178176 misses=3 recoveries=1**——
  58 个 `3072/3`、3 次 `status=5`（buf 2/5/6），seq 42 后 100 ms stall
  cancel 3 个请求；**host 比设备多 1536 B**（一个被打断的半套）。
- 枚举：4 次 `SET_INTERFACE(0)` 都执行了 teardown cancel，没有 `svcBreak`；
  新增 1 份非致命 erpt `2162-0004`（Data Abort，v16-r2 也出现过），
  无 crash/fatal。
- 判定：**lead 40 是负结果**（v29h lead 32：62 段 / 2 miss / 0 recover）；
  lead 16/32/40 = 54/62/58，32 附近最好，lead 路线收敛。map-soft-2 第一次
  经受住枚举 alt0，但 `--keep-alt` 下没走到收尾 alt0。
- 恢复：日志与 erpt 已归档并删除；卡随即部署 v29m。证据
  `private/runs/UAC-u2-v29l-map-soft2-20261103`。

### 2026-11-03 12:3x v29m lead 32 + map-soft-2（离线，已部署）

v29l 证明 lead 40 不如 32，所以 v29m 回到 v29h 的数据路径（quad cave、
lead 32、3 在飞），保留 v29h 的 `0x3fe0` map-soft 和 v29l 的 `0x3dac`
map-soft-2，共 46 条 edits。

- NSP `a1318cf0…`（92676 B）、NSO `7bd8bf08…`；cave
  `patches/iso_burst_uac84_dci9_pipe_quad.S`（680/684 B）；
- 与 v29h manifest 比较只多 `0x3dac` 一条；app 不变；
- 判定：62 段、host==device（190464）、alt0 不崩；这是做 ring 复位诊断前
  的基线配置。

### 2026-11-03 12:4x v29m 实机：lead 32 未复现 v29h

- host：`rc=0`；312 transfers、`valid=2241 bad=2751 **bytes=179904**`，
  数据 t=18–2802 ms。
- 设备：**posted=64 completed=64 bytes=178176 misses=3 recoveries=1**——
  58 个 `3072/3`、3 次 `status=5`、1 次 100 ms stall；host 比设备多 1728 B。
- 与 v29l（lead 40 + map-soft-2）数值完全相同（58/3/1、178176 B），
  与 v29h（lead 32 + map-soft only）不同（62/2/0、190464 B）。
- 枚举：5 次 `SET_INTERFACE(0)` 无 `svcBreak`，无新 crash/fatal/erpt；
  v29l 的 `2162-0004` 没有复现。
- 判定：**回退 lead 没有恢复 62**。两轮 map-soft-2 一致、map-soft-only
  的 v29h 不同，所以先重复 v29m 分离方差与 map-soft-2 影响；不要在这之前
  改 ring 或 lead。

### 2026-11-03 13:0x v29m 重复轮：63 段 / 1 miss（新最好）

- 同一 NSP `a1318cf0…`、同一 probe、同一 VM 纪律，结果与首跑不同：
- host：`rc=0`；312 transfers、`valid=2273 bad=2719 **bytes=193536**`，
  数据 t=18–2514 ms。
- 设备：**posted=64 completed=64 bytes=193536 misses=1 recoveries=0**——
  63 个 `3072/3`、1 次 `status=5`、无 stall；**host==device**。
- 枚举 5 次 `SET_INTERFACE(0)` 无 `svcBreak`，无新 crash/fatal/erpt。
- 判定：**首跑 58/3/1 是 run-to-run 方差**，不是 map-soft-2 的稳定影响；
  同一构建两轮 58↔63。v29m 重复轮成为新的最好数据轮（63 段、1 miss），
  下一个目标是那一跳 miss 前的 ring 复位。

### 2026-11-03 13:1x v29n rearm-race 诊断（离线）

对已归档设备日志做离线分类：把每个 post 的 `cursor pre/post` 配对，pre 非空
（`prod != cons`）而 post 出现 rearm wipe（`prod == cons == ring`、`cur == 0`）
记为一次 “rearm during post”。结果：

| run | rearm-during-post | miss |
| --- | --- | --- |
| v29h | 2（seq 5/55） | 2 |
| v29i | 3（seq 44/51/60） | 3 |
| v29f | 3 | 3 |
| v29m-r2 | 1（seq 39，buf 6） | 1 |
| v29m 首跑 | 2 | 3 |
| v29l | 1 | 3（另有多轮普通 empty rearm 后的 miss） |

多数 miss 能在 post 内看到一次 rearm wipe，说明 cave 在 ring 刚被排空时
rearm（memset + 0x2feb0）与这次投递竞争；但仍不能从现有日志区分 cave
rearm 与驱动 `0x30ff4` 复位，所以 v29n 只在 app 加一行观测：

- payload 与 v29m 完全相同（46 条 edits，cave 680/684 B）；
- app `_uacLogCursor` 记住 pre 的 ring/prod/cons，post 后若 pre 非空且出现
  wipe，则 `LOG("UAC U2 rearm race seq=... pre_prod=... pre_cons=...")]
  post_prod=... post_cons=...")`；不改变驱动、cave 或时序；
- 构建 NSP `5421884e…`（92960 B）、NSO `f4b351c6…`；工作目录
  `private/analysis/UAC-u2-v29n-rearm-diag-20261103`；
- 判定：数据路径应与 v29m 相同（63 段最好，方差 58–63）；rearm-race 行
  与 miss 对齐 → 修 cave rearm 竞态；不对齐 → 查 `0x30ff4`。

### 2026-11-03 15:4x v29n 实机：rearm race 与 miss 一一对应

- host：`rc=0`；312 transfers、`valid=2169 bad=2823 **bytes=184320**`，
  数据 t=18–2802 ms。
- 设备：**posted=64 completed=64 bytes=184320 misses=4 recoveries=0**——
  60 个 `3072/3`、4 次 `status=5`、无 stall；host==device。
- 新日志把每一次 miss 都标了出来，且**4 条 `UAC U2 rearm race` 与 4 次
  miss 完全对齐**：

  | seq | buf | pre_prod | pre_cons | 结果 |
  | --- | --- | --- | --- | --- |
  | 4 | 3 | `+0xd600` | `+0xd480` | status=5 |
  | 16 | 7 | `+0xd400` | `+0xd220` | status=5 |
  | 45 | 4 | `+0xd600` | `+0xd560` | status=5 |
  | 63 | 6 | `+0xd400` | `+0xd260` | status=5 |

- 机制确认：post 前 ring 还剩少量 TD，但 cave 的 gate 看到
  `prod == cons`，走空 ring rearm；`0x2feb0` 先对 ring 做 0x1000 的
  memset（连同 mailbox/cursor），把刚发出那套的 pending completion
  wipe 掉，控制器对那套回 `status=5`。不是驱动 `0x30ff4`。
- 判定：下一轮修 `0x2feb0` 的 memset——跳过或缩小到 `0xf00`，保留
  mailbox/cursor；保持 v29m 数据路径，一次只改这一处。

### 2026-11-03 15:5x v29o re-arm keeps the mailbox（离线）

v29n 的 4/4 对齐说明 miss 来自 cave 空 ring rearm 的 wipe。0x2feb0 的
memset 在 0x2ff18（长度在 0x2ff14 的 `mov w2,#0x1000`），清掉整个
0x1000，包括四个 mailbox（+0xf00..+0xfc0）和 cursor（+0xfb8），把仍
pending 的 completion 一起抹掉。

- v29o 只改 `0x2ff14`：`mov w2,#0x1000` → `#0xf00`（`02008252` →
  `02e08152`），TD 区与 link（+0xc00）仍被清，mailbox/cursor 保留；
- `0x30ff4` 的错误路径有自己独立的一份 0x1000 memset（0x3109c），
  不改；
- 调用面：0x2feb0 的两个调用者是安装路径 0x2fd50 和 cave 的
  `rearm_endpoint`；cave 在每次 post 都会用自己的 magic/零重写 mailbox，
  stale done 不会挡住新 set；
- 构建：NSP `855e7d41…`（92959 B）、NSO `afaac6f2…`；47 条 edits；工作
  目录 `private/analysis/UAC-u2-v29o-rearm-keep-mailbox-20261103`；
- 判定：rearm-race 行可能仍出现，但 `status=5` 应下降；若仍有
  miss+race，说明新 set 复用了同一 mailbox，或 completion 丢在别处。

### 2026-11-03 16:0x v29o 实机：memset 缩短没有消除 miss

- host：`rc=0`；312 transfers、`valid=2361 bad=2631 **bytes=190464**`，
  数据 t=18–2801 ms。
- 设备：**posted=64 completed=64 bytes=190464 misses=2 recoveries=0**——
  62 个 `3072/3`、2 次 `status=5`、无 stall；host==device。
- **2 条 `UAC U2 rearm race` 仍与 2 次 miss 一一对应**（seq 30/34，
  buf 5/1），说明把 memset 缩到 0xf00、保住 mailbox/cursor 并没有解决：
- 丢的是 **rearm 本身**（`0x2feb0` 的 memset + prod/cons reset +
  context commit + halt clear）与刚发出的 set 竞争。自然排空（控制器还
  在跑、没有 halt）时不需要重置 context；只有驱动 `0x30ff4` 复位后才
  需要。
- 判定：v29o 不优于 v29h（62/2/0）；下一版改 cave 的空 ring 门——自然
  排空直接在 `prod` 写，只有 halt/base 才 rearm；空间从 rearm 后的
  死 link copy 腾出。

### 2026-11-03 16:1x v29p empty-gate（离线）

v29o 证明 memset 缩短不够：rearm 本身（context reset + commit + halt
clear）与刚发出的 set 竞争。v29p 改 cave 的空 ring 门：

- 先判 `prod == cons`；若不等，正常写；
- 若相等，再读 ring base：`prod != base` 说明只是自然排空，控制器还在
  跑，直接落到 `pipe_nonempty`，在 `prod` 写下一套，不 rearm；
- 只有 `prod == cons == base`（驱动 `0x30ff4` 复位后的状态，或首次
  burst）才调 `0x2feb0` replay；
- rearm 后那段 link copy 删除：驱动 link 已在 `0x2ff40` 补到 `0xc00`，
  `[x1,#0x28]` 必等于 link slot，copy 是死代码；cave 从 680 降到
  **652/684 B**（32 B 空闲），`iso_event` 移到 `0x68edc`；
- 构建：NSP `a9858913…`（93189 B）、NSO `cfa7e451…`；46 条 edits
  （v29n 驱动集，不含 `0x2ff14` 的 memset 改动）；
- 判定：自然排空的 rearm-race 行应消失，miss 应降到 0 或只剩 base
  场景；若停流，说明自然排空后控制器仍需要 replay，base 判据不成立。

### 2026-11-03 16:2x v29p 实机：base 门退步

- host：`rc=0`；312 transfers、`valid=2057 bad=2935 **bytes=177024**`，
  数据 t=18–2609 ms。
- 设备：**posted=64 completed=64 bytes=175104 misses=4 recoveries=1**——
  57 个 `3072/3`、4 次 `status=5`、1 次 100 ms stall；host 比设备多 1920 B。
- 第一条 race（seq 5）后：`cons` 冻在 `+0xd380`，`prod` 从 `+0xd800`
  继续前进到 wrap，app 连投 3 套都没有 completion，直到 100 ms stall
  cancel——**跳过非 base 的 rearm 会让控制器停住**。
- 同时 seq 5/33 仍有 rearm race：pre 时 prod 非 base，post 却是
  `prod=cons=base`，说明 drain 时**驱动自己**把 ring 复位到 base，
  cave 只是跟着 rearm。base 门不能把两者分开。
- 判定：v29p 退步（57/4/1 vs v29m 63/1/0）；回退 v29m；下一个杠杆是
  驱动的 drain reset 路径，不是 cave 的空 ring 门。

### 2026-11-03 16:4x 离线：流水线的空档是测量本身造成的（v29q 静默流水线）

v29p 的 cursor 行（`_uacLogCursor`）记录了每次 post 的帧游标，把 64 次
post 的帧差列出来就能看出流水线并没有按“一套 16 帧”的节奏走：

| 指标 | 值 |
| --- | --- |
| post 次数 / 可用帧差 | 64 / 59（2 次 memset 清零、3 次 wrap） |
| 帧差总和 | **2374**（64 套理论值 1024） |
| 均值 / 中位数 | 40.2 / 33 |
| 帧差 ≥ 24（空档 ≥ 8 帧） | 44 / 59 |
| 帧差 ≥ 32（空档 ≥ 16 帧） | 36 / 59 |
| host 数据 / 时间 | 177024 B / 2609 ms = **35.3%** 的 192 B/ms |

- cave 的帧号是 `max(MFI/8 + 32, cursor)`：只要“上一次 completion → 本次
  post”的延迟 D > 1 ms，`MFI+32` 就会盖过 cursor，并在上一套结束后留出
  D 帧空档。3 在飞的深度正好只够填满 cursor 路径，没有余量。
- 而这个延迟就在循环里：每次 post 写一行 SD 日志 + 两次 dmnt cursor dump
  （`svcDebugActiveProcess` + `svcReadDebugProcessMemory` + close）；每次
  completion 再写一行 SD 日志 + 一次 dmnt dump。SD 行是 open + get-size +
  write(+flush) + close。v29p 的中位帧差 33 = 16（一套）+ 17（延迟），与
  “一次 completion 周期的日志开销 17 ms”一致。
- 机制链：空档 → 控制器在空档里的帧漏服务（xHCI 语义是 missed service；
  **实机未观测到具体码**，`0x30ff4` 接的码集是 3/4/5/9/10/14/15/31/
  `0xDB`/`0xDE`）→ 驱动 `0x30ff4` memset ring、复位指针、置 halt → 正在
  写的那套被丢弃 →
  `status=5` miss → 下个 post 走 `0x2feb0` replay 恢复（v29m 的 1 miss
  就是这么来的）。
- 所以 v29h/v29m 的 62/63 段与 35% 占空比是**带诊断的上界**，不是数据路径
  的上限；rearm 门、memset 长度、lead 扫描都在这个被污染的节奏上比较，
  这也解释了同一 NSP 58 段 vs 63 段的“方差”。

v29q（离线构建 NSP `8e81d119…`，92350 B）：

- payload 与 v29m **逐字节相同**（cave 680/684 B、46 条 edits）；只改 app：
  去掉 `-DUAC_U2_CURSOR_DIAG`，把 pipeline 的逐 post/completion 行改成
  `UAC_U2_PIPE_LOG`（`-DUAC_U2_QUIET_PIPE` 时展开为空）；
- 计数留在 RAM，末尾一行：
  `UAC U2 pipe timing waits=.. timeouts=.. span_ms=.. max_gap_ms=.. max_react_ms=..`；
- miss 是稀有事件，仍保留 `UAC U2 pipe miss buf=.. status=..` 一行，保证
  丢的那一套可归因；
- 判定：`span_ms` 接近 64×16=1024 ms、`max_react_ms` ≈ 0–2、host 覆盖
  接近 192 B/ms、misses→0，则空档来自 app 测量；若 `span_ms` 仍 ~2.6 s、
  `max_react_ms` 仍 ~17 ms，则延迟在驱动/宿主路径，需要下一个杠杆。

### 2026-11-03 18:4x v29q 实机：节奏修好，只剩一次 miss 的恢复

- 设备：`posted=64 completed=64 bytes=181248 misses=2 recoveries=1`；
  `pipe timing waits=61 timeouts=20 **span_ms=1201** max_gap_ms=181
  max_react_ms=129`；日志里只有两条 `pipe miss buf=4/5 status=5` 与一次
  `pipe stall recover cancelled=3`；无 crash/fatal/erpt。
- host：`rc=0`；312 transfers、`valid=1017 bad=3975 bytes=180672`，数据
  **t=33–1185 ms**（活跃窗 1152 ms），其中 **~176 ms 完全无数据**
  （urb 56–66 全 bad，端点被 halt）。
- 覆盖：180672 / (1152 ms × 192 B/ms) = **81.7%**（v29p 35.3%）；设备侧
  59 段 = 944 ms 音频 / 1201 ms = 78.6%。
- **节奏**：1201 − 181 = 1020 ms ≈ 64 × 16 ms——把那次空档扣掉后每套正好
  16.0 ms，`MFI+32` 与 cursor 不再打架。v29p 的 40.2 帧均值/35% 覆盖
  完全由 app 的 SD 日志 + dmnt dump 造成，**假设成立**。
- 剩下的损失全在那一次 miss 事件：2 个 `status=5` 让驱动 `0x30ff4`
  memset ring 并置 halt（`prod=cons=base`、`trb0=0` 的收尾状态可证），
  app 的 100 ms stall 阈值 + cancel + 下一套 32 ms lead，合计 ~176 ms
  无数据，丢 5 套（2 miss + 3 被 cancel）。
- 下一版只动 app：把 stall 阈值 100 ms 降到 32 ms（v29r），看 host 空档
  能否压到 ~70 ms；若 `max_gap_ms` 不降，说明驱动 `0x30ff4` 自己的
  `regs+0x78` 轮询（最多 100 ms）才是那段时间的占据者。

### 2026-11-03 18:5x v29r 实机：stall 阈值 32 ms 是负结果

- 设备：**posted=27、completed=24、bytes=0、misses=0、recoveries=8**；
  日志正好 8 条 `pipe stall recover cancelled=3 rc=0x0 limit_ms=32`，
  第 9 次 stall 直接 `pipe stall posted=27 completed=24 limit_ms=32`
  退出循环；`pipe timing waits=8 timeouts=18 span_ms=0 max_gap_ms=0
  max_react_ms=0`。
- host：`valid=4992 bad=0 bytes=4032`，数据只在 t=18–354 ms 漏出。
- 机制：一套 TD 要等 `MFI+32` 才被取指，再 16 帧才完成，**首个
  completion 约 48 ms**。阈值 32 ms 在它之前触发 → app cancel 掉刚投的
  3 套（计入 completed）→ 重投 → 再看 32 ms 没 completion → 再 cancel，
  形成 cancel 风暴；recoveries 上限 8 用完后 train 退出。
- 结论：**stall 阈值必须大于 lead + 一套（≈48 ms）**；100 ms 是合理值，
  这条路线关闭。181 ms 空档的下一格仍是“error code 是几号、驱动
  `0x30ff4` 的 `regs+0x78` 轮询是否占满”，需要 v29s 的记录型 cave。

### 2026-11-03 19:0x v29s 错误码诊断（离线）

- **前情**：v29q 唯一的损失是一次 miss 事件（2 个 `status=5` → 驱动
  `0x30ff4` memset + 置 halt → app 100 ms 阈值 + cancel + 32 ms lead，
  共 181 ms 无数据）。这一路的所有推断都缺一格：**到底是哪个 completion
  code 把端点停住的**。`0x30ff4` 接的码集是 3/4/5/9/10/14/15/31/
  `0xDB`/`0xDE`，实机一个都没观测到。
- **为什么一直没看到**：所有 UAC cave 的 `ISO_ENTRY` 都是 `0x270`——那是
  DCI-7（A23 EP `0x83`）的对象；UAC 配置没有 DCI 7，`[obj+0x10]` 为 0，
  `iso_event` 在 `cbz x5` 就 `b event_original`。**自 v14 起 cave 的事件
  分支从未执行过**。
- v29s 的 cave（`patches/iso_burst_uac84_dci9_pipe_quad_log.S`，548/684 B）：
  - `ISO_ENTRY = 0x300`（manager+0x22300，DCI-9 对象）；
  - `iso_event` 只做一件事：DCI 9 且 `[event+8]>>24 != 1` 时，**先**
    `bl event_original`（保存 `x0/x1/x30`），**再**把 `{event word, ring
    offset}` 追加到 `ring+0xc20`（计数 `ring+0xc10`，16 项）；
  - `{event word}` 里含 code（bit31..24）与长度；offset 用 `[event]` 的
    TRB 指针按 `[obj+0x38]`（物理基址）换算，`(off>>9)&3` 给 mailbox 归属；
  - enter 路径与 v29q **逐字节相同**，46 条 payload edits 不变——只换了
    cave 文件；
  - 顺序为什么必须“先原函数、后记录”：`0x30ff4` 在完成 URB **之前**会
    memset 整个 0x1000 ring，先写就会被自己描述的那个事件擦掉。
- app（`-DUAC_U2_EVENT_LOG`）：`_uacLogEventScratch()` 在 **miss 时**与
  **结尾**各读一次（独立 dmnt 会话，不进热循环），输出
  `UAC U2 evlog miss count=N` 与逐条 `code/len/off`。
- 构建：NSP `795f6ec6…`（92837 B），NSO `5d3de8cd…`；`iso_enter=0x68d54`、
  `iso_event=0x68ef8`、`iso_end=0x68f78`。
- 判定：数据路径不倒退（≥59 段、覆盖 ~82%），且 `count ≥ 1`。
  `count=0` 说明对象偏移或 hook 不对，先停。

### 2026-11-03 19:1x v29s 实机：错误码是 23（Missed Service）

- 设备：`posted=64 completed=64 bytes=181248 misses=2 recoveries=1`；
  `pipe timing waits=61 timeouts=14 span_ms=1250 **max_gap_ms=194
  max_react_ms=147**`；host 183744 B、数据窗 34–1250 ms、覆盖 78.7%。
- 日志（关键四行）：

```text
UAC U2 pipe miss buf=5 status=5
UAC U2 evlog miss count=2 rc=0x0
UAC U2 evlog miss [0] code=23 len=192 off=0xba0
UAC U2 evlog miss [1] code=23 len=192 off=0xbc0
UAC U2 pipe miss buf=6 status=5      ← 第二次读到同样的两条
UAC U2 pipe stall recover cancelled=3 rc=0x0 limit_ms=100
```

- **code 23 = Missed Service**（与 xHCI 1.1 编号一致：13 = Short Packet、
  26 = Stopped、14 = Ring Underrun 也都对得上驱动自己的分支）。len=192
  说明是正常长度的 ED；offset 0xba0/0xbc0 是第 6 套（0xa00..0xbff）的
  最后两个槽——**控制器没能在那一帧及时服务**。两次 miss 读到的记录相同：
  同一次事件，两个 URB 各报一次 `status=5`。
- 驱动的 code-23 分支 `0x31274`：置 `regs+0x50` 的 dci 位、轮询并 ack
  `regs+0x5c`，然后 `b 0x31118` 用 `w2=0x3228c` 调 `complete_original`
  ——app 因此看到 `status=5`。**它不复位 ring、不重载上下文**。
- 所以：halt 之后 prod/cons 不变 → 下一次 post 在 `prod` 直接写（不 rearm）
  → halt 永不清除 → 没有任何 completion → 100 ms 后 app 的 stall 定时器
  cancel（`0x30470` 把 ring 复位到 base）→ 下一次 post 走 `0x2feb0`
  （commit + 清 halt）→ 首套还要 32 ms lead。**194 ms 就是这么来的**。
- 收尾那条 `code=14 len=0 off=0x7ffdd000`（Ring Underrun、TRB 指针为空）
  走 `0x30ff4` 做了最后一次 ring wipe，与结束时 `prod=cons=base`、
  `trb0=0` 一致。
- 判定：**miss 是 host/控制器漏服务，不是 cave 竞态**；可动的只有“halt
  之后多快恢复”。v29t：`status=5` 一到就 cancel + 重投，不等 100 ms。

### 2026-11-03 19:2x v29t 实机：立即恢复把 194 ms 压到 77 ms

- 设备：`posted=64 completed=64 **bytes=187392** misses=2 **recoveries=1**`；
  `pipe miss recover cancelled=1 rc=0x0`；
  `pipe timing waits=63 timeouts=16 span_ms=1146 **max_gap_ms=77
  max_react_ms=31**`。host 188544 B、数据窗 34–1138 ms、覆盖 **88.9%**、
  45 个满 3072 的 URB。
- miss 仍是同一种：`evlog count=2` → `code=23 len=192 off=0x580`、
  `off=0x5a0`（第 2 套槽 12/13），与 v29s/0xba0-0xbc0 同型；收尾还有一条
  `code=14`（Ring Underrun）。
- 差别只在 app：`status=5` 报告一到就 `usbDsEndpoint_Cancel` + 重投，
  不再等 100 ms。结果：
  | 指标 | v29s | v29t |
  | --- | --- | --- |
  | recoveries | 1（stall 路径） | 1（miss 路径） |
  | 恢复时被 cancel 的套数 | 3 | **1** |
  | `max_gap_ms` | 194 | **77** |
  | `max_react_ms` | 147 | **31** |
  | 段数 / span | 59 / 1250 ms | **61 / 1146 ms** |
  | host 覆盖 | 78.7% | **88.9%** |
- 解读：剩下的 77 ms = cancel + 32 ms lead + 16 ms 一组，已经接近理论下限
  （≈50 ms + 抖动）。**miss 本身才是下一个目标**：code 23 表示控制器在这
  两帧上没被服务，属于宿主提交节奏，不是设备能决定的。
- 下一步不需要重建：同一镜像把 probe 的 `--transfers` 从 8 加到 16
  （256 帧预排），看 code 23 是否消失。

### 2026-11-03 19:3x v29t-h16 实机：host 预排不是原因

- 同一 v29t 镜像，只把 probe 的 `--transfers` 从 8 改成 16（256 帧预排）：
  设备 `posted=64 completed=64 bytes=187392 misses=2 recoveries=1`、
  `span_ms=1169 **max_gap_ms=88** max_react_ms=42`；host 188928 B、
  覆盖 86.6%。**与 8 URB 的 188544 B / 88.9% / 77 ms 在噪声内相同。**
- `evlog miss count=2` → `code=23 len=192 off=0xb60/0xb80`（第 5 套
  Isoch 槽 11/12）。
- **规律**：三次实机的漏帧位置是 v29s `0xba0/0xbc0`（槽 13/14）、
  v29t `0x580/0x5a0`（槽 12/13）、h16 `0xb60/0xb80`（槽 11/12）——
  全部落在**一套 16 帧的尾部几帧**（槽 11–14）。随机命中这个区间的概率
  约 25%，连续三次说明是结构性的：控制器走到一套末尾时，**前面已取到的
  TD 材料用尽**。
- 因此 v29u 把在飞深度 3→4 套（`-DUAC_U2_IN_FLIGHT=4`）：六套环里
  0x800 仍然 `prod != cons`，空 ring 的 rearm 门不会误触；控制器手里多
  一整套 TD。

### 2026-11-03 19:4x v29u 实机：4 在飞也不改漏帧

- 设备：`posted=64 completed=64 bytes=184320 misses=2 recoveries=1`；
  `pipe miss recover cancelled=2`；`span_ms=1114 **max_gap_ms=95**
  max_react_ms=34`；`evlog` 仍是一条 `code=23 len=192 off=0xba0/0xbc0`
  （第 5 套 Isoch 槽 13/14，与 v29s 完全相同的位置）。
- host 186816 B、覆盖 87.7%、满 3072 的 URB 58 个（比 3 在飞时的 45 多，
  数据更整）。
- 解读：**多一整套 TD 预取不放缓漏帧**。加上 host 预排 8/16 等价，
  可以判定漏服务既不是“控制器缺 TD 材料”，也不是“宿主排队不足”。
  剩下的解释只有宿主/VM 的周期调度本身，或设备侧这个形状的固有边界。
- 代价：4 在飞让恢复时 cancel 2 套（3 在飞是 1 套），所以段数 60 < 61、
  覆盖 87.7% < 88.9%——**v29t 仍是最佳配置**。
- 设备侧排查清单（全部负结果）：cave 空 ring 门（v29p）、memset 长度
  （v29o）、lead 16/24/40（v29j/v29l）、host 预排（h16）、在飞 4（v29u）。
- 下一步：长跑（v29v，256 posts）测稳态，而不是继续压单次 miss。

### 2026-11-03 20:1x v29v 长跑：4.45 s 稳态与长期 ring 复用

- 256 posts、`MAX_RECOVERIES=64`，host `--max-urbs 512 --timeout-ms 10000`。
- 设备：`posted=256 completed=256 **bytes=758784 misses=6 recoveries=3`；
  `pipe timing waits=253 timeouts=42 **span_ms=4449 max_gap_ms=80
  max_react_ms=34**`。host 762816 B、数据窗 33–4434 ms、覆盖 **90.3%**、
  185 个满 3072 的 URB。
- 三次事件，每次两条 code-23（一帧一条），各自 `recover cancelled=1`：

```text
miss [0] code=23 len=192 off=0x160   set 0 Isoch slot 11
miss [1] code=23 len=192 off=0x180   set 0 Isoch slot 12
miss [0] code=23 len=192 off=0x4a0   set 2 Isoch slot  5   ← 不在套尾
miss [1] code=23 len=192 off=0x4c0   set 2 Isoch slot  6
miss [0] code=23 len=192 off=0xb60   set 5 Isoch slot 11
miss [1] code=23 len=192 off=0xb80   set 5 Isoch slot 12
```

- 数字核对：256 posts × 16 ms = 4096 ms 下限；实际 4449 ms，差 353 ms
  ≈ 3 × (~80 ms 恢复 + 抖动) + 每套 ~0.9 ms 的漂移。交付 247 段
  （256 − 6 漏 − 3 cancel），247/256 = **88.8%**。
- **长期复用**：4.45 s 内环走 ~43 次六套 wrap、游标两次 2048 帧回卷，
  指针/cycle 没有卡死。这是项目第一次拿到 >4 s 的连续数据与环复用证据。
- **修正**：v29s/v29t/h16 的“漏帧总在套尾”是小样本错觉；长跑里第 2 套的
  槽 5/6 也漏。v29u 正是基于那个错觉做的 4 在飞实验，结果阴性，与此一致。
- 结论：设备侧形状稳定，剩下的 ~10% 缺口来自宿主每 ~1.5 s 一次的**两帧**
  漏服务；继续压它需要宿主侧证据，不是环形状。

## 里程碑

1. **v26A**：8 buffer、2 在飞、16 ms tick、lead 32、light log、`--keep-alt`；
   先离线构建 + 单测，再一次 boot。
2. v26B：16/32 buffer，测 gap/丢包；再谈 PCM、时钟与 UVC 共存。
3. 并行课题：`ISO_ENTRY=0x270`（应为 0x300）与 8 个 descriptor-parser NOP
   的隔离；收尾崩溃的 app 侧规避（alt0 先 cancel 再 ack）。

### 2026-11-03 22:1x v30e 长跑：8.9 s 稳态与 ~1.85 s 周期

v30e 与 v29v 的 payload 逐字节相同（header `929b4b3b…`），只把 app 的
`STREAM_POSTS` 256→512、`MAX_RECOVERIES` 64→128（NSP `1737eb35…`，
93050 B）。host 用 probe4（`MAX_URBS_TOTAL` 1024→4096，一行改动），因为
host 每套约消耗 2 个 URB：512 套需要 ~1024–1100 次提交，probe3 的 1024
上限会在 ~8.9 s 停住；`--max-urbs 2048 --timeout-ms 10000`。

设备侧：

```text
pipe end posted=512 completed=512 bytes=1529856 misses=10 recoveries=5
pipe timing waits=506 timeouts=64 span_ms=8885 max_gap_ms=92 max_react_ms=44
```

- 498 个完整套 = 1529856 B，512 posts 的 **97.3%**；`span_ms=8885` 对应
  512×16 = 8192 ms 下限，差 693 ms ≈ 5 × (92 ms 恢复 + 抖动) + 漂移。
- 5 次 code-23 事件，每次两条 miss（两帧），第 3 次 `recover cancelled=0`
  （cancel 时已无在飞）；其余 4 次 `cancelled=1`。
- host 625 transfers、1533696 B（499.25 套）、数据窗 33–8865 ms、
  覆盖 **90.4%**、384 个满 URB、4 条 `detail p0=1/0`。
- 事件时刻：**353 / 2209 / 4049 / 5905 / 7745 ms**，间隔
  **1856 / 1840 / 1856 / 1840 ms**。此前 4.5 s 轮次只有 2–3 次事件，
  看不出间隔；这一轮是第一次能说“漏服务有周期”。
- 与 v29v 对比：事件率 5/8.885 = **0.56/s**（v29v 0.67/s、v30d 0.67/s、
  v30a 0.23/s 是低异常）；交付率 97.3% vs 96.5%。**稳态随时长线性成立**，
  没有随 ring wrap 次数（本轮 ~92 次六套 wrap）退化的迹象。
- 结论：产品数字改为 **~90% 占空 + ~92 ms 空洞 / ~1.8 s**；下一步是复跑
  确认 1.85 s 周期，而不是继续调深度。

### 2026-11-03 22:5x v30e 复跑：1.85 s 周期不重现

同一 NSP、同一 probe4 参数再跑一次（一次 boot），专门回答“周期是不是真的”：

```text
pipe end posted=512 completed=512 bytes=1517568 misses=14 recoveries=7
pipe timing waits=502 timeouts=73 span_ms=8984 max_gap_ms=87 max_react_ms=40
```

- 494 套 = 1517568 B（512 posts 的 96.5%）；host 1523904 B（496.06 套）、
  数据窗 33–8962 ms、覆盖 **88.9%**。
- 7 次事件在 t=1986/4082/4545/5025/5714/6177/8514 ms，间隔
  **2096/463/480/689/463/2337 ms**：4 个 ~0.47 s 的密集间隔夹着长安静段，
  与 r1 的 1856/1840/1856/1840 形态完全不同。
- **结论：r1 的整齐间隔是单轮巧合，没有 ~1.85 s 周期源。** 两轮合计
  12 事件 / 17.87 s = **0.67/s**，交付 96.5–97.3%，与 v29v/v30d 同量级。
- 3 次恢复 `cancelled=0`（cancel 时已无在飞），说明密集事件里恢复有时
  赶在 halt 已自行释放之后。
- 产品数字最终按 **~90% 占空、~90 ms 空洞、0.6–0.8 次/s** 记；48 kHz 连续
  仍不成立，缺口在宿主 EHCI/VM 的漏服务，设备侧没有可再调的形状。

### 2026-11-03 23:4x macOS 裸机：标准宿主的开流路径是 alt1，不是 SET_CUR

同一 v30e 镜像插在 Mac 上（VM 挂起，`AppleUSBAudio` 绑定，系统识别
2ch/48000），`ffmpeg -f avfoundation -i ":2" -t 10` 返回 0，但 WAV
8.8267 s / 423680 帧全零。设备日志给出了原因：

```text
UAC u2 patch result=0 record=45 last-rc=0x0
UAC setup[3] type=01 req=0b val=0000 idx=0003 len=0 action=4 rate=48000
UAC setup[3] type=01 req=0b val=0001 idx=0003 len=0 action=3 rate=48000   (x13)
```

- **没有任何 class SET_CUR**（type 0x21/0x22），所以 `_postUacBurst()` 一次
  都没被调用：日志里没有 `train begin`、`pipe end`、`pipe miss`。
- macOS 只是反复 `SET_INTERFACE(alt0) → SET_INTERFACE(alt1)`（13 次）——
  这是宿主“开了流但收不到数据”时的重试。
- Linux probe 之所以能跑，是因为它**显式**发 3 字节 SET_CUR（
  `type=22 req=01 idx=0084`），恰好命中触发；标准宿主不需要发 SET_CUR
  （默认速率已经是 48000），只切 alt1。

**结论：U2 的 arm 条件必须同时接受 `SET_INTERFACE(alt=1)` on AS 接口**
（幂等，只在未 arm 时启动）。这是产品路径缺陷，不是数据路径问题；
payload/cave 不用动，app-only 改动即可（v30f）。

### 2026-11-04 00:1x–00:2x macOS 裸机：v30f/v30g 与 alt 抖动

**v30f（alt1 inline arm）**：`SET_INTERFACE(alt=1)` 里直接调 `_postUacBurst()`。
宿主在 status stage 完成前不提交 ISO 读，而处理函数被 9 s 训练占住：

```text
UAC U2 train begin count=8 pattern=0
UAC U2 pipe end posted=388 completed=385 bytes=0 misses=188 recoveries=128
UAC U2 pipe timing waits=257 timeouts=233 span_ms=10612 max_gap_ms=106 max_react_ms=72
```

`ffmpeg` 在设备打开处卡死 >2 min；之后 macOS 反复 alt0/alt1（317 条 teardown）。

**v30g（worker thread + 20 ms）**：EP0 立即返回，训练在线程里跑：

```text
UAC U2 arm thread create rc=0x0 / start rc=0x0
UAC U2 train begin count=8 pattern=0
UAC U2 pipe end posted=512 completed=512 bytes=1324032 misses=47 recoveries=23
UAC U2 pipe timing waits=476 timeouts=91 span_ms=9772 max_gap_ms=214 max_react_ms=161
```

- 数据真的到了：WAV 4.096 s / 196608 帧、值 ±16384（1 kHz 方波），但 PTS 已
  9.2 s，且 42 段 ≥1 ms 静音（前段每 ~10.5 ms 一个、约 3 ms）。
- 关键：`val=0001` 440 次、`val=0000` 441 次 —— **macOS 每 ~68 ms 切一次
  alt**。每次 alt0 都会 cancel 端点；`g_uacArmStarted` 又让后续 alt1 不能
  重新 arm，所以流只靠 23 次恢复硬撑，miss 的 code-23 全在 `off=0x0/0x20`
  （重新 arm 后的环头）。
- 对比 VM：VM 是 0.67 次/s 的稳态漏服务 + 87–92 ms 空洞；macOS 是持续
  alt 抖动、47 次 miss、214 ms 空洞、只拿到 4.096 s 样本（设备侧 431 套 =
  6.9 s）。**VM 数字不是虚拟 EHCI 伪影，原生更差。**

结论：一次性训练的形态不适合真实宿主。下一步 v30h 把 producer 改成
“alt1 开、alt0 停、每次 alt1 可重新 arm”的连续循环（不设固定 post 数），
让 alt 抖动只造成一次环复位，而不是杀死整条流。

### 2026-11-04 00:3x v30h 连续 producer：alt 抖动被压住

v30g 的 440 次 alt 切换说明一次性训练不能用在真实宿主上。v30h 改成：

- `g_uacCtx.streamRequested`：alt1 置位、alt0 清除；管道循环在清除时 break；
- `UAC_U2_CONTINUOUS`：post 计数变成回绕保护（0xFFFFFFFF），全部完成也继续投；
- arm 线程循环：等标志 → 20 ms → 跑训练 → 清 `burstPosted` → 再等，每个
  alt1 都能重新 arm。

macOS 实机（一次 boot，`ffmpeg -t 20` 正常结束 20.5 s）：

```text
alt1=15 alt0=11 trains=15
posted=1122 completed=1077 bytes=3115008 (1014 sets = 16.22 s)
misses=46 recoveries=16, per-train max_gap 28-67 ms
WAV 682088 frames = 14.21 s, +/-16384 square wave, 105 silence runs (0.42 s)
```

- **形态成立**：alt 切换 440→15，流不再被 alt0 杀死，每次 alt1 都能续上，
  1 kHz 相位跨训练连续（`pattern` 从 6912、15360… 递增）。
- **还剩两层损失**：设备投递 16.22 s / 20.5 s 墙钟（79%），宿主又只录到
  14.21 s（投递的 87.6%）；miss 46 次（~1.15 事件/s）仍高于 VM 的 0.67/s。
- 每段训练的首个 miss 常在 `off=0x0`，即重新 arm 后立刻发生——20 ms 的 arm
  前延迟可能太短；这是下一个最便宜的实验（20→40 ms），其次是连续流下把
  在飞 3→4（窗口 48→64 ms，`max_react` 实测 20–36 ms 已接近上限）。

### 2026-11-04 00:5x v30i：arm 延迟 40 ms 是负结果

只改一个常量（`_uacArmThreadFunc` 的等待 20→40 ms），一次 boot：

```text
trains=18  posted=1026 completed=972 bytes=2749440 (895 sets = 14.32 s)
misses=56 recoveries=18  alt1=18 alt0=13  per-train max_gap 23-70 ms
WAV 537088 frames = 11.19 s (wall 20.55 s = 54%), 145 silence runs 0.76 s
```

对比 v30h：15 段、1014 套 / 16.22 s、46 miss、宿主 14.21 s（69%）。

- 多等的 20 ms 让每次重新 arm 少投 ~1.5% 的音频，还多出 3 次重启；
- `off=0x0` 的 miss 没有消失，其余 miss 仍在环中段；
- 结论：**arm 时序不是杠杆**，回退 20 ms。下一单变量：`IN_FLIGHT` 3→4
  （64 ms 窗口，4 是 mailbox 上限）；若 miss 不降，改 `0x31274` 内联快速恢复，
  把每次 miss 的 23–70 ms 空洞压到几 ms。

### 2026-11-04 01:0x v30j：in-flight 4 是负结果

只加 `-DUAC_U2_IN_FLIGHT=4`（窗口 48→64 ms，4 是 4 个 mailbox 的上限）：

```text
trains=12 posted=953 completed=905 bytes=2457600 (800 sets = 12.8 s)
misses=59 code23=97 (~48 events) recoveries=23  alt1=12 alt0=6
per-train max_gap 68-115 ms
WAV 569344 frames = 11.86 s, but only 4 silence runs (0.17 s)
```

- 流内确实更干净（静音段 105 → 4），但**总投递反而少**（1014 → 800 套）、
  miss 更多（46 → 59）、每段空洞更大（28–67 → 68–115 ms）；少掉的时间落在
  训练之间。
- 原因与 v29u 一致：多一套在飞，每次 cancel 就多丢一套，环状态更差。
- 结论：**回退 3 在飞**。参数调优（arm 延迟、在飞深度）到此为止，下一个
  结构性杠杆是驱动侧 code-23 快速恢复：在 `0x31274` 内联 ring 复位 + 清 halt，
  省掉 app 的 cancel 往返，把每次 miss 的 23–115 ms 空洞压到几毫秒。

### 2026-11-04 01:3x v31 离线：驱动侧 code-23 快速恢复

只改驱动的一处错误分支，app 与 cave 不动（仍是 v30h 配置）：

```text
0x31274 原：halt-set + 0x5c ack 轮询 + fall-through 到 0x31118
             (20 条指令 / 0x50 B，最坏 2000 x 50 us)
0x31274 新：sub  x0, x21, #0x22, lsl #12   ; manager = x21 - 0x22000
             mov  x1, x19                   ; 事件里的端点对象
             bl   0x2feb0                   ; ring reset + context + commit + unhalt
             b    0x31118                   ; 原路径：status=5 完成 URB
             + 16 x nop                     ; 保持 0x50 B
```

`0x2feb0` 的动作（`UAC_U2_ENDPOINT_CONTEXT.md` §2）：memset ring、`prod/cons`
回 base、`regs+0x40` cycle=1、写 64 B context、`regs+0x58` commit、清
`regs+0x54/0x50` halt。它与 app 的 cancel + 下一次空 ring post 所做的事
完全相同，只是发生在 completion 之前；`0x312c4` 的 `b 0x31118` 不变，
所以 URB 仍以 status=5 报给 app。

- 动机：code 23 只置 halt、不复位 ring（`0x31274`），cave 的 `prod==cons`
  门永远不成立，app 必须 `usbDsEndpoint_Cancel` + 重投，代价是 20–40 ms
  往返 + 32 ms lead。
- 预期：halt 握手（两次轮询）从空洞里消失，app 的 cancel 看到 ring 已在
  base、halt 已清（`0x30470` 的 `0x54` 轮询直接跳过）。
- 风险：`0x2feb0` 在事件上下文里跑 context writer + DMA 转换；断言会以
  crash/fatal 出现。另两条在飞 URB 的 ring 内存被 memset 掉，仍由 app 紧随
  其后的 cancel 完成（与今天相同）。

| 观察（macOS 一次 boot） | 结论 |
| --- | --- |
| 每段 `max_gap` 明显小于 v30h 的 28–67 ms，miss 数同量级 | **halt 握手就是空洞成本**；保留 v31，继续压 miss 或宿主样本差 |
| 每段 `max_gap` 与 v30h 相同（28–67 ms） | 握手不是成本；剩下的只有 app round trip + 32 ms lead，下一轮改 app/cave（不再由驱动修） |
| 空洞更大 / miss 更多 | 事件上下文里 re-arm 有副作用（可能与 app cancel 竞争）；回退 v30h |
| 任一 crash/fatal/erpt | 立即停，读卡取报告，回退 v30h |

判据只看空洞与 crash，不看段数（单轮段数方差 ≈ 6 套）。

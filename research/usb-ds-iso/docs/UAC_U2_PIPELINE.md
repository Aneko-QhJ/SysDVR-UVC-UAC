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

## 里程碑

1. **v26A**：8 buffer、2 在飞、16 ms tick、lead 32、light log、`--keep-alt`；
   先离线构建 + 单测，再一次 boot。
2. v26B：16/32 buffer，测 gap/丢包；再谈 PCM、时钟与 UVC 共存。
3. 并行课题：`ISO_ENTRY=0x270`（应为 0x300）与 8 个 descriptor-parser NOP
   的隔离；收尾崩溃的 app 侧规避（alt0 先 cancel 再 ack）。

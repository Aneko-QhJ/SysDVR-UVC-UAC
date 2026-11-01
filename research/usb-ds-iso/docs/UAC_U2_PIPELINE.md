# UAC U2：连续 ring / 双 buffer 流水线（v26 设计，离线）

> 状态：**v26A 实机部分成功（8 post/8 report，只有偶数 buffer 上线）；v26B
> 帧游标已离线实现并构建（`116a1204…`，92342B），0 实机**。v23 证明
> “每 burst 重放 `0x2feb0`”能让 4 个顺序 burst 全部完成；v24 把 dmnt dump
> 去掉后 gap 96 ms；v25 把 TD 帧 lead 压到 4 ms 失败（1536B、`0x748c`），
> 回退 32 ms。本文件先设计、后实现连续 ring，不重复
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

## 里程碑

1. **v26A**：8 buffer、2 在飞、16 ms tick、lead 32、light log、`--keep-alt`；
   先离线构建 + 单测，再一次 boot。
2. v26B：16/32 buffer，测 gap/丢包；再谈 PCM、时钟与 UVC 共存。
3. 并行课题：`ISO_ENTRY=0x270`（应为 0x300）与 8 个 descriptor-parser NOP
   的隔离；收尾崩溃的 app 侧规避（alt0 先 cancel 再 ack）。

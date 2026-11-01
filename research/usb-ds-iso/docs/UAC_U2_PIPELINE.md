# UAC U2：连续 ring / 双 buffer 流水线（v26 设计，离线）

> 状态：**v26A 已离线实现并构建（`5e6c29af…`，92322B），0 实机**。v23 证明
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

## 里程碑

1. **v26A**：8 buffer、2 在飞、16 ms tick、lead 32、light log、`--keep-alt`；
   先离线构建 + 单测，再一次 boot。
2. v26B：16/32 buffer，测 gap/丢包；再谈 PCM、时钟与 UVC 共存。
3. 并行课题：`ISO_ENTRY=0x270`（应为 0x300）与 8 个 descriptor-parser NOP
   的隔离；收尾崩溃的 app 侧规避（alt0 先 cancel 再 ack）。

# 当前状态（2026-11-03 12:3x，Asia/Shanghai）

> 本文件是唯一“当前状态”，只写现在成立的事实、最佳配置、下一步与边界。
> 逐轮时间线见 [README_HISTORY.md](../README_HISTORY.md)，U2 数据路径细节见
> [UAC_U2_PIPELINE.md](UAC_U2_PIPELINE.md)，全部文档见 [INDEX.md](INDEX.md)、
> [ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)。[STATUS.md](STATUS.md)、
> [PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md) 等是旧快照，不再作为入口。

## 一分钟

- 目标：让 Switch `usb:ds` 输出标准 UAC 音频（48 kHz / 2ch / 16 bit = 192 B/ms）。
- **数据路径最好一轮（v29h，lead 32）**：64/64 posts、**62 个完整 3072 B
  片段（190464 B）**、host 与设备字节相等、2 次单套 miss、0 恢复。
- **lead 扫描收敛**：lead 16（v29j）54 段、lead 32（v29h）62 段、lead 40
  （v29l）**58 段 / 3 miss / 1 recover**——40 是负结果，32 附近最好，
  继续加大 lead 不再有用。
- **收尾/map 安全**：v29l 在枚举阶段经历了 4 次 `SET_INTERFACE(0)` 没有
  `svcBreak`（map-soft-2 起效），但新增 1 份非致命 erpt `2162-0004`
  （Data Abort，v16-r2 也出现过同类），需要继续观察。
- **已否掉的路线**：单次请求 >16 帧、两 buffer 流水线、4 在飞/4 套环
  （v29i）、lead 4/16/40。
- **候选 v29m 已构建并部署**：NSP `a1318cf0…`（92676 B），46 条 edits =
  v29h 数据路径（lead 32）+ `0x3fe0` map-soft + `0x3dac` map-soft-2；
  待一次 boot 确认 62 段、host==device、alt0 不崩。
- 限制：占空比约 47%，48 kHz 连续仍不成立；UAC 默认仍禁用（仅
  `UAC_HOST_PROBE`）。
- 下一步：v29m 一次 boot；之后做 **ring 复位诊断**——miss 前都出现
  `prod=cons=cur=0`（v29l seq 40 也看到 `prod` 回 base），要记录触发者是
  驱动 `0x30ff4` 还是 cave 的空 ring rearm。
- 未隔离：DCI-9 cave 的 `ISO_ENTRY=0x270`、8 个 descriptor-parser NOP。
- 卡：v29m 已部署（`a1318cf0…`）；v29l 日志与 1 份新 erpt 已归档并从卡
  删除，12:3x 弹出。

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
| v29d | link `+0xf70`→`+0xc00`，六套对齐 | 57024 B | 18×`3072/3`；两次 wrap 干净 | wrap 修好；ring 跑空 |
| v29e | 4 mailbox + 3 在飞 + status=5 恢复 | 180672 B | 56×`3072/3`、4 recover | 3 在飞成立 |
| v29f | miss 只释放槽并补投，stall 才 cancel | 187392 B | 61×`3072/3`、3 miss | 数据好；收尾仍崩 |
| v29g | alt0 STOP 先 cancel + 收 report | 193536 B | 63×`3072/3`、1 miss | 数据最好；崩溃仍在 |
| v29h | IOVA 节点耗尽返回错误（map-soft） | 190464 B | 62×`3072/3`、2 miss | **收尾不崩；当前最佳** |
| v29i | 4 套环（`+0x800`）+ 4 在飞 | 187392 B | 61×`3072/3`、3 miss | 负结果：4 套深度不够 |
| v29j | v29h + lead 32→16 | 170688 B | 54×`3072/3`、4 miss、2 stall | 负结果：lead 16 太小 |
| v29k | v29h + lead 32→40 | —（崩溃，无数据） | —（开机枚举 alt0 崩溃） | 0 数据；第二入口 `0x3dac` 崩溃，v29k 未测 |
| v29l | v29k + `0x3dac`→`0x409c`（map-soft-2） | 179712 B | 58×`3072/3`、3 miss、1 recover | lead 40 负结果；host 比设备多 1536 |
| v29m | 回退 lead 32 + 双 map-soft | —（0 实机） | —（0 实机） | 离线 `a1318cf0…`（92676 B），已部署待 boot |

## 当前最佳配置（v29h 数据路径 + v29m 安全补丁）

| 项 | 值 |
| --- | --- |
| NSP / NSO | v29m `a1318cf0…`（92676 B）/ `7bd8bf08…`；v29h 结果来自 `9610b3a0…` |
| cave | `patches/iso_burst_uac84_dci9_pipe_quad.S`（680/684 B，lead 32） |
| ring | link `+0xc00`（六套对齐）；mailbox `+0xf00/+0xf40/+0xf80/+0xfc0`，`set=(offset>>9)&3`；游标 `+0xfb8` |
| 在飞 | 3；miss 容忍（status=5 只释放槽并补投）；100 ms stall 才 cancel + 重投；alt0 STOP 先 cancel + 收 report |
| 驱动 | 3 处队列补丁 + 12 处 link `0xff0→0xc00` + map-soft `0x3fe0` + map-soft-2 `0x3dac`（46 条 edits） |
| app | `-DUAC_U2_BURSTS=8 -DUAC_U2_STREAM_POSTS=64 -DUAC_U2_LIGHT_LOG -DUAC_U2_PIPELINE -DUAC_U2_CURSOR_DIAG` |
| host | `uac-raw-probe --trigger-first --delay-ms 30 --packets 16 --transfers 8 --rearm --max-urbs 512 --timeout-ms 5000 --keep-alt` |
| 结果 | v29h：62×3072（190464 B）、host==device、misses=2、recoveries=0、无 crash/fatal；v29m 待 boot |

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

1. **v29m 实机（一次 boot）**：卡上已是 `a1318cf0…`；Switch 开机前
   suspend/detach VM，主界面后再 attach，确认 guest 只在 attach 后看到
   `1209:ca57`，然后跑一次 probe；
2. 判定：62 段、host==device（190464）、alt0 不崩（0x19a8c 算通过）；
   若回归，先回 v29h 再查；
3. 之后做 **ring 复位诊断**：miss 前 `prod=cons=cur=0`（v29l seq 40 也看到
   `prod` 回 base），要在 cave/驱动记录触发者；0 miss 之后再做占空比与
   48 kHz 连续。

判定：先不倒退（≥62 段），目标是 0 `status=5`、device bytes = host bytes
（196608）。

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

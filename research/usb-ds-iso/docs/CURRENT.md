# 当前状态（2026-11-03 08:5x，Asia/Shanghai）

> 本文件是唯一“当前状态”，只写现在成立的事实、最佳配置、下一步与边界。
> 逐轮时间线见 [README_HISTORY.md](../README_HISTORY.md)，U2 数据路径细节见
> [UAC_U2_PIPELINE.md](UAC_U2_PIPELINE.md)，全部文档见 [INDEX.md](INDEX.md)、
> [ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)。[STATUS.md](STATUS.md)、
> [PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md) 等是旧快照，不再作为入口。

## 一分钟

- 目标：让 Switch `usb:ds` 输出标准 UAC 音频（48 kHz / 2ch / 16 bit = 192 B/ms）。
- **数据路径最好一轮（v29h）**：64/64 posts、**62 个完整 3072 B 片段
  （190464 B）**、host 与设备字节相等、2 次单套 miss、收尾不崩。
- **收尾崩溃已关闭**：`SET_INTERFACE(0)` 重装端点时的 IOVA 节点耗尽不再
  `svcBreak`，而是返回错误码（v29h map-soft）；从 v16 起的老问题结束。
- **已否掉的路线**：单次请求 >16 帧（17–19 帧处挂死）、两 buffer 流水线
  （驱动单 transfer）、4 在飞/4 套环（v29i，miss 2→3）、lead 4（v25）与
  lead 16（v29j，miss 2→4）。
- **新候选 v29k（lead 40）已离线构建**：NSP `f05f72a1…`（92589 B），
  cave 680/684 B、45 条 edits；只把 TD 帧 lead 32→40，其余与 v29h 相同，待一次 boot。
- 限制：占空比约 47%，48 kHz 连续仍不成立；UAC 默认仍禁用（仅
  `UAC_HOST_PROBE`）。
- 下一步：先跑 v29k（lead 40）；若 40 不改善，试 48 或给驱动 ring 复位加诊断；
  目标 0 miss。
- 未隔离：DCI-9 cave 的 `ISO_ENTRY=0x270`、8 个 descriptor-parser NOP。
- 卡：安全 `52069a44…`，已弹出；实机按 START_HERE 的常设授权执行。

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
| v29b | per-set mailbox（A/B）+ 只认 status=3 | 24576 B | 8/8 `3072/3` | 账本修好 |
| v29c | 64 post 滚动 + 8 槽复用（≤2 在飞） | 187968 B | 61×`3072/3`、2×status=5 | 稳态成立；wrap 失败 |
| v29d | link `+0xf70`→`+0xc00`，六套对齐 | 57024 B | 18×`3072/3`；两次 wrap 干净 | wrap 修好；ring 跑空 |
| v29e | 4 mailbox + 3 在飞 + status=5 恢复 | 180672 B | 56×`3072/3`、4 recover | 3 在飞成立 |
| v29f | miss 只释放槽并补投，stall 才 cancel | 187392 B | 61×`3072/3`、3 miss | 数据好；收尾仍崩 |
| v29g | alt0 STOP 先 cancel + 收 report | 193536 B | 63×`3072/3`、1 miss | 数据最好；崩溃仍在 |
| v29h | IOVA 节点耗尽返回错误（map-soft） | 190464 B | 62×`3072/3`、2 miss | **收尾不崩；当前最佳** |
| v29i | 4 套环（`+0x800`）+ 4 在飞 | 187392 B | 61×`3072/3`、3 miss | 负结果：4 套深度不够 |
| v29j | v29h + lead 32→16 | 170688 B | 54×`3072/3`、4 miss、2 stall | 负结果：lead 16 太小 |
| v29k | v29h + lead 32→40 | —（0 实机） | —（0 实机） | 离线构建 `f05f72a1…`，待一次 boot |

## 当前最佳配置（v29h）

| 项 | 值 |
| --- | --- |
| NSP / NSO | `9610b3a0…`（92589 B）/ `b136b181…` |
| cave | `patches/iso_burst_uac84_dci9_pipe_quad.S`（680/684 B） |
| ring | link `+0xc00`（六套对齐）；mailbox `+0xf00/+0xf40/+0xf80/+0xfc0`，`set=(offset>>9)&3`；游标 `+0xfb8` |
| 在飞 | 3；miss 容忍（status=5 只释放槽并补投）；100 ms stall 才 cancel + 重投；alt0 STOP 先 cancel + 收 report |
| 驱动 | 3 处队列补丁 + 12 处 link `0xff0→0xc00` + 1 处 map-soft（45 条 edits） |
| app | `-DUAC_U2_BURSTS=8 -DUAC_U2_STREAM_POSTS=64 -DUAC_U2_LIGHT_LOG -DUAC_U2_PIPELINE -DUAC_U2_CURSOR_DIAG` |
| host | `uac-raw-probe --trigger-first --delay-ms 30 --packets 16 --transfers 8 --rearm --max-urbs 512 --timeout-ms 5000 --keep-alt` |
| 结果 | 62×3072（190464 B）、host==device、misses=2、recoveries=0、无 crash/fatal |

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
  `add`/`clear`）、map-soft 1 处（`0x3fe0` 的 `cbz x0, 0x40d0` → `0x409c`）。
- **payload**：45 条 = cave + 2 分支 + 18 描述符 + 8 NOP + 3 队列 + 12 link
  + 1 map-soft。
- **接口预算**：`usb:ds`/libnx 最多 4 个接口，UVC 2 + UAC 2 = 4，因此 UAC 不能与
  `ISO_PROBE` 的 vendor 接口同 build。

## 下一步

1. **v29k lead 40**（已离线构建，NSP `f05f72a1…`）：一次 boot 确认 40 是否
   降 miss；底线是不倒退（≥62 段）、不产生 crash/fatal；
2. 若 40 不变或变差：试 **lead 48**，或直接做 **ring 复位诊断**——miss 前都
   出现 `prod=cons=cur=0` 的复位，需要在 cave/app 记录触发者（driver 的
   `0x30ff4` 还是 cave 的空 ring rearm），再决定阻止或绕开；
3. 0 miss 之后再做占空比与 48 kHz 连续评估。

判定：先不倒退（≥62 段），目标是 0 `status=5`、device bytes = host bytes
（196608）。

## 边界与纪律

- 实机授权：2026-11-01 16:19 起常设授权——部署/测试不再逐轮申请，插卡与开机前
  通知用户即可；一次 boot、失败即停、不重试。
- “部署”只等于把文件拷到卡上；插卡、开机、关机由用户执行。
- VM 纪律：开机前 suspend；主界面后 resume + attach；必要时一次 VM
  suspend/resume 让 guest 枚举；probe 一次。
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

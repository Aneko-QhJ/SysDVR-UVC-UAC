# 当前状态（2026-11-03 16:2x，Asia/Shanghai）

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
- 下一步：回退 v29m（63 段 / 1 miss，最好）；不要再改 cave 门；下一个
  杠杆是驱动在 drain 时重写 ring 的复位（`0x30ff4` 类路径），或者接受
  1 miss 先转向占空比。
- 未隔离：DCI-9 cave 的 `ISO_ENTRY=0x270`、8 个 descriptor-parser NOP。
- 卡：安全 `52069a44…` 已恢复并弹出（13:0x）；两轮日志均已归档。

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

## 当前最佳配置（v29m）

| 项 | 值 |
| --- | --- |
| NSP / NSO | v29m `a1318cf0…`（92676 B）/ `7bd8bf08…` |
| cave | `patches/iso_burst_uac84_dci9_pipe_quad.S`（680/684 B，lead 32） |
| ring | link `+0xc00`（六套对齐）；mailbox `+0xf00/+0xf40/+0xf80/+0xfc0`，`set=(offset>>9)&3`；游标 `+0xfb8` |
| 在飞 | 3；miss 容忍（status=5 只释放槽并补投）；100 ms stall 才 cancel + 重投；alt0 STOP 先 cancel + 收 report |
| 驱动 | 3 处队列补丁 + 12 处 link `0xff0→0xc00` + map-soft `0x3fe0` + map-soft-2 `0x3dac`（46 条 edits） |
| app | `-DUAC_U2_BURSTS=8 -DUAC_U2_STREAM_POSTS=64 -DUAC_U2_LIGHT_LOG -DUAC_U2_PIPELINE -DUAC_U2_CURSOR_DIAG` |
| host | `uac-raw-probe --trigger-first --delay-ms 30 --packets 16 --transfers 8 --rearm --max-urbs 512 --timeout-ms 5000 --keep-alt` |
| 结果 | 最好：63×3072（193536 B）、host==device、misses=1、recoveries=0、无 crash/fatal；同一 NSP 另一轮 58 段（方差） |

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

1. **回退 v29m**（`a1318cf0…`，63 段 / 1 miss，仍然最好）作为后续基线；
   v29p 的 cave 门改动不再使用；
2. **驱动 drain reset**：日志显示 drain 时驱动把 ring 复位到 base
   （pre 非 base、post base），cave 只是跟着 rearm。下一个候选应查
   `0x30ff4` 类复位在正常 drain 时为何运行，能否只跳过 ring/memset 而
   保留 commit/halt clear；
3. 若复位路径风险太大，接受 1 miss，转占空比与 48 kHz 连续评估；
4. 0 miss 仍是最终目标，但不再是唯一前进条件。

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

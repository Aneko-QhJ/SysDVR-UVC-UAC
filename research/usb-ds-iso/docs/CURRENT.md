# 当前状态（2026-11-02 21:0x，Asia/Shanghai）

> 本文件是唯一“当前状态”，只写现在成立的事实、下一步与边界。
> 逐轮时间线见 [README_HISTORY.md](../README_HISTORY.md)，U2 数据路径细节见
> [UAC_U2_PIPELINE.md](UAC_U2_PIPELINE.md)，全部文档见 [INDEX.md](INDEX.md)、
> [ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)。[STATUS.md](STATUS.md)、
> [PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md) 等是旧快照，不再作为入口。

## 一分钟

- 目标：让 Switch `usb:ds` 输出标准 UAC 音频（48 kHz / 2ch / 16 bit = 192 B/ms）。
- 现状：2 个请求在飞 + 8 槽缓冲复用的滚动流成立（v29c：61 段 / 2.1 s）；
  **v29d 的 link 对齐也成立**——两次 wrap 都是 `+0xa00 → +0x000`、cycle 翻转，
  一套 TD 不再被拆开，A/B mailbox 相位保持。
- 最后实机 v29f（21:00）：**posted=64 / completed=64 / bytes=187392
  （61×3072）/ misses=3 / recoveries=0**；host bytes 与设备**完全相等**，
  3 次 miss 都只丢一套、没有 cancel 连锁。**miss 容忍成立，数据路径最好一轮**。
- **但收尾崩溃了**：`pipe end` 之后 host 断开/重连、重复 `SET_INTERFACE(0)`，
  usb sysmodule User Break（base+0x19280，fatal PC +0x19254），与 v16/v24/v26A
  同签名。这是当前**第一优先**要解决的问题。
- 下一步 **v29g 已离线构建**（NSP `a599149a…`，92541 B）：`SET_INTERFACE(0)`
  （`UAC_ACT_STOP`）在 ACK 前先 `usbDsEndpoint_Cancel` + 收一份 report，日志
  `UAC U2 teardown cancel`；数据路径同 v29f。待一次 boot 看收尾是否不再崩。
- 限制：占空比约 47%，48 kHz 连续仍不成立；UAC 默认仍禁用（仅 `UAC_HOST_PROBE`）。

## 阶段进度

| 阶段 | 状态 | 关键结果 | 证据 |
| --- | --- | --- | --- |
| U0 枚举 | 通过 | 257 B / 4 接口，macOS 绑定 `AppleUSBAudio`，2ch/48k | `UAC-u0d-20261030` |
| U1a 控制 | 通过 | 13/13；`SET_CUR(48000)` ACK 并回读 | `UAC-u1a-r7-20261030` |
| U1b alt | 通过 | alt 0→1→0 均 ACK，无 NOP | `UAC-u1b-20261030` |
| U2 单 burst | 通过 | v14：3072 B / status=3，2/2 可重复 | `UAC-u2-v14-trigger-success-20261031`、`…-repeat-20261101` |
| U2 顺序 4-burst | 通过 | v23：12288 B；缺失步骤是重放 `0x2feb0` 的 commit + 清 halt | `UAC-u2-v23-rearm-20261101` |
| U2 2 在飞 | 通过 | v29b：8/8 全 `3072/3`，host = 设备 = 24576 B | `UAC-u2-v29b-sets-20261102` |
| U2 滚动流 | 部分 | v29c：2.1 s、61 个完整段，收尾在 wrap 失败 | `UAC-u2-v29c-stream-20261102` |
| U2 wrap 对齐 | 通过 | v29d：两次 `+0xa00→+0x000` wrap，cycle 翻转，set 不拆 | `UAC-u2-v29d-wrap-20261102` |
| U2 3 在飞 + 恢复 | 通过 | v29e：64 posts、56×`3072/3`、4×status=5 均 recover | `UAC-u2-v29e-quad-20261102` |
| U2 miss 容忍 | 通过 | v29f：64 posts、61×`3072/3`、host==device、3 miss 无连锁 | `UAC-u2-v29f-miss-20261102` |

单次请求上限仍是 **3072 B / 16 帧**：20 帧（3840 B）、32 帧（6144 B）都会挂死
`usb:ds`，上限落在 17–19 帧，“加大单次 transfer”路线已关闭。

## 最近几轮（数据路径主线）

| 轮次 | 做法 | host | 设备 | 判定 |
| --- | --- | --- | --- | --- |
| v29a | 驱动队列补丁：每个追加请求立即提交 | 21504 B（7×3072） | 2 个 post 进 cave，完成返回 status=2/5 | 队列补丁 + 2 在飞成立；共享 mailbox 账本错 |
| v29b | per-set mailbox（A/B）+ 只认 status=3 | 24576 B | 8/8 全 `3072/3`，两套之间无复位 | 账本修好，2 在飞稳定 |
| v29c | 64 post 滚动 + 8 槽复用（在飞 ≤2） | 187968 B，t=33–2097 ms | posted=64、61×`3072/3`、2×status=5、1×cancel | 稳态成立；收尾在 TD 环 wrap |
| v29d | link 槽 `+0xf70`→`+0xc00`：六套对齐 TD，驱动 4 处 link 常量 | 57024 B，t=33–801 ms | posted=22、18×`3072/3`、2×status=5；两次 wrap 干净 | wrap 修好；ring 跑空/underrun 提前停 |
| v29e | 4 mailbox（`+0xf00` 起，`&3`）+ 3 在飞 + status=5 恢复 | 180672 B，t=33–2673 ms | posted=64、56×`3072/3`、4×status=5 + 4×recover | 3 在飞成立；miss 与空 ring rearm 对齐 |
| v29f | status=5 只记 miss 并补投，stall 才 cancel+重投 | 187392 B（=设备） | posted=64、61×`3072/3`、3×status=5、0 recover | 数据最好；收尾 `SET_INTERFACE(0)` 崩溃 |
| v29g | alt0 STOP 在 ACK 前 cancel 端点 + 收 report | —（0 实机） | —（0 实机） | 离线构建 `a599149a…`，待一次 boot |

v29c 的故障点：第一次 wrap（`+0xf70`）就把一套 TD 拆开，之后每次 wrap 让写
游标漂移 0x90；到 post 63 时 `prod=+0xddf0`，一套跨过 0x200 边界，ED 分属
两个 mailbox，两个都凑不满 3072 B → status=5，随后 post 被 cancel。缓冲复用
没有崩（8 槽、复用间隔约 4 个 post）。本次运行本身无崩溃；16:52 的
crash/fatal/erpt 属于“VM 未 suspend 就开机”的那次，已归档。

## 构件与关键事实

- **端点**：AS `EP 0x84`，端点字 `0x00C00584`（不是 `0x00C00184`），DCI 9、
  MPS 192、interval 4。安装对象在 `base+0x17b038`，`installed` 在 `+0x1610`，
  表项指针在 `+0x1608`。
- **Ring**：0x1000；一套 = 16 帧 × 192 B = 3072 B，16 对 Isoch + ED TRB，
  `prod` 每次前进 `+0x200`。v29c 的 link 槽在 `+0xf70`（驱动在 `+0xff0`），
  0xf70 落在第 8 套 TD 内、导致 split + 每次 wrap 漂移 0x90；v29d 把两边都
  改到 `+0xc00`（六套对齐，偶数保 mailbox 交替）。mailbox A `+0xf80`、B
  `+0xfc0`（B 的 `+0x3c` 字段已去掉），全局帧游标在 `+0xfb8`，都在 link 之后。
- **驱动队列补丁**（usb.elf，3 处）：`0x0c4` 放提交 stub（`sub w9,w12,#1` /
  `and w9,w9,#7` / `b 0x2c62c`）、`0x2c628` 改为 `b 0x0c4`（总是提交刚追加的
  entry）、`0x2c80c` 改为 `b 0x2c84c`（跳过完成后的自动提交，由 app 保持
  2 在飞）。
- **Cave**：`patches/iso_burst_uac84_dci9_pipe_sets.S`，680/684 B（区段
  `0x68d54..0x69000`）；per-set mailbox、全局游标、空 ring 时重放 `0x2feb0`。
- **App**：`-DUAC_U2_BURSTS=8 -DUAC_U2_STREAM_POSTS=64 -DUAC_U2_LIGHT_LOG
  -DUAC_U2_PIPELINE -DUAC_U2_CURSOR_DIAG`；每次完成等 100 ms，超时先
  `usbDsEndpoint_Cancel`；只有 `status=3` 算完成；8 槽池、在飞 ≤2。
- **Host**：`host/uac-raw-probe`（claim → alt1 → `SET_CUR`），v29c 用
  `--packets 16 --transfers 8 --rearm --max-urbs 256 --timeout-ms 3000
  --keep-alt`；另有 `uac-control`（`--set-rate`/`--alt-only`）与 `uac-burst`。
- **payload**：v29c 32 条 = cave + 2 分支 + 18 描述符 + 8 NOP + 3 驱动队列；
  v29d 44 条 = 上述 32 条 + 12 条驱动 link 编辑（4 处 setup/error）。
- **接口预算**：`usb:ds`/libnx 最多 4 个接口，UVC 2 + UAC 2 = 4，因此 UAC 不能与
  `ISO_PROBE` 的 vendor 接口同 build；`_setupAudioInterfaces5x` 已加拒绝。

| 候选 | NSP | 大小 | NSO | cave / app |
| --- | --- | --- | --- | --- |
| v29a | `feaa2d55…` | 92899 B | `2c74777a…` | v26B cursor 672/684 B；BURSTS=8 + PIPELINE + CURSOR_DIAG |
| v29b | `203519a7…` | 92812 B | `8faede4c…` | per-set 680/684 B；同上 |
| v29c | `b1f812e4…` | 92483 B | `0aa4f494…` | per-set 680/684 B；+ `STREAM_POSTS=64` |
| v29d | `287907b8…` | 92628 B | `36b801d7…` | v29d wrap cave 680/684 B；+ 12 条 link 编辑 |

## 下一步：v29g（已离线构建，待一次实机）

v29f 的数据路径最好（64/64、61 段、host==device），但 `pipe end` 之后
host 断开/重连、重复 `SET_INTERFACE(0)`，usb sysmodule 在 DMA map/submit 路径
断言（+0x1927c；栈 `0x2c584 → 0x2a3f4 → 0x2a464`）。怀疑 alt0 重装端点时仍有
排队/映射的请求。

v29g 只在 app 收尾动手，数据路径不变：

1. `UAC_ACT_STOP`（alt0）在 `_ctrlAck` 前调用 `usbDsEndpoint_Cancel`，并
   `eventWait` + `GetReportData` 收掉一份 report；
2. 日志 `UAC U2 teardown cancel rc=0x%x wait=0x%x`，用于确认 alt0 前队列已空。

候选 NSP `a599149a…`（92541 B，44 条 edits，cave 680/684 B），host 命令同
v29f。判定：数据仍 64/64、host==device；收尾**无 crash/fatal**。若仍崩，
下一步隔离 `SET_INTERFACE(0)` 路径或 patch 断言点。

## 仍未隔离

- 收尾 `SET_INTERFACE(0)` 的 usb `svcBreak`（`+0x1927c`，v16/v24/v26A 同栈）；
  `--keep-alt` 只去掉 probe 自己的 restore，内核重绑仍会发 alt0。
- DCI-9 cave 的 `ISO_ENTRY=0x270`（应为 `0x300`）；v14–v29c 的 `iso_event`
  因此一直落到 `event_original`。
- payload 里 8 个 descriptor-parser NOP（A23 alt1 覆盖）尚未收窄。
- A23 线（short24 复测、标准宿主 10s PCM）已挂起，需单独安排。

## 边界与纪律

- 实机授权：2026-11-01 16:19 起常设授权——部署/测试不再逐轮申请，插卡与开机前
  通知用户即可；一次 boot、失败即停、不重试。用户撤销时以当次指示为准。
- “部署”只等于把文件拷到卡上；插卡、开机、关机由用户执行，代理不自行开机。
- VM 纪律：开机前 VM suspend；主界面后 resume + attach；必要时一次 VM
  suspend/resume 让 guest 枚举；probe 一次。v29c 第一次开机就是漏了 suspend。
- 收尾：恢复安全卡 `52069a44…`、删日志/新报告、安全弹出；设备现场状态不推定。
- `private/` 是原始证据，只读；不覆盖、不移动、不清理。失败即停，不自动重试。

## 不证明

48 kHz 连续 PCM、标准宿主（Linux `snd-usb-audio`）互操作、>2.1 s 稳态与长期
ring/缓冲复用、wrap 修复后的行为、收尾无崩溃、时钟同步/反馈、A23 10 s 连续、
旧超时根因、未来无事件。

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

# UAC U2 连续 producer（v15 失败；v16 r2 排除 cave 门）

> 状态：三轮相关实机。v15（2026-11-01 01:05）：只完成第 1 个 burst
> （3072/3），第 2 个 post `rc=0` 后 100 ms 无 completion，被取消。
> v16 r1（01:41）：**boot 崩溃**（usb fatal 2162-0002），probe 未运行。
> v16 r2（01:49，VM 开机前 suspend）：host 仍只有 3072B，但设备 `pre/post`
> 日志证明**两次 post 都进了 cave、都写了完整 TD 集**，只有第 1 套被服务——
> **`prod == cons` 门被排除**，问题在 ring 复位/控制器 dequeue。
> 2026-11-01 16:0x **v23** 用“每 burst 重放驱动 setup `0x2feb0`”拿到 4/4
> burst（12288B），“只有第一个 TD 集”的墙已打破；但 host 的 wire gap 是
> 160/162/142 ms，而每个 burst 只有 16 ms。2026-11-01 16:2x 离线准备 **v24
> gap probe**（`-DUAC_U2_LIGHT_LOG` + 相位 timing），下一轮一次 boot 判定
> gap 来自每 burst 的 dmnt dump 还是 cave 的 `0x2feb0`。
> 硬件授权已用尽（`remaining=0`），下一次上机需要新的明确授权
> （见 [RESEARCH_RULES.md](RESEARCH_RULES.md)）。当前事实以
> [CURRENT.md](CURRENT.md) 为准。

## 问题卡

- **问题**：v14 的 16 ms one-shot 已 2/2 收到完整 3072B；设备能否**顺序**
  提交 4 个 3072B burst（每个各自 +32 frame 窗口），而不回到 v11 train 的
  pending-request 崩溃？
- **变化**：设备侧 `-DUAC_U2_BURSTS=4`（只改 post 次数，payload 与 v14
  逐字节相同）；host 侧 `uac-raw-probe --rearm` 滚动窗口，始终保留在飞 URB。
- **判别条件**：设备日志 `train end posted=4 completed=k` 且每个成功
  `seq` 都是 `complete rc=0 requested=3072 transferred=3072`；host 至少两个
  不同时刻的 `urb[...] bytes>0`，总字节 ≥ 6144；无 `cancel`/timeout、无新
  crash/fatal。
- **上限**：一次 boot、一次 alt1、host `--max-urbs 64 --timeout-ms 1000`。
- **停止条件**：任一 post 失败、100 ms 无 completion（已 cancel）、fatal /
  crash / 断连；**失败不重试**。

## 为什么不是 v11 train

| 轮次 | post 次数 | 超时处理 | 实机结果 |
| --- | --- | --- | --- |
| v11 | 32 | 直接 `break`，**request 留在驱动里** | 第 1 个 3072/3，第 2 个无 completion；随后 alt0 teardown 触发 usb 崩溃 |
| v14 | 1 | `usbDsEndpoint_Cancel` | 3072B，2/2 可重复，无 crash |

v15 保留 v14 的**单请求不变量**，只把“1 次”扩成“顺序 4 次”：只有上一个
请求完成后才 post 下一个；任何超时先 cancel 再退出循环。因此任何时刻驱动里
最多只有一个 ISO request，v11 的 teardown 崩溃条件不成立。

代价是 burst 之间有“完成 → 再提交”的间隙，**这不是无间隙音频**；本轮只验证
数据路径的连续性，PCM/时钟/产品级持续流仍未定义（见
[RESEARCH_RULES.md](RESEARCH_RULES.md) 的“探索与验收分开”）。

## 设备侧设计

源码 `source/uvc/uvc_device.c`，改动只在 app 侧：

- `UAC_U2_BURSTS`（1..4）选择顺序 post 次数，默认 **1**（安全默认，等于
  v14）；`UAC_U2_ONE_SHOT` 仍作为 1 的别名保留。`#error` 拒绝 0 或 >4，
  防止误建 32-post train。
- 缓冲区 `g_u2BurstBuffers[UAC_U2_BURSTS][0x1000]` 每个 burst 独立，不重用。
- 1 kHz 方波相位跨 burst 连续：新增 `patternFrame` 计数器，
  `frame = base + i/2`，每 16 ms 前进 768 个立体声帧；host 可以据此判断
  4 个 burst 是同一段连续波形。
- 诊断日志（新增/扩展）：
  - `UAC U2 train begin count=%u pattern=%u`
  - `UAC U2 post begin seq=%u/%u pattern=%u`
  - `UAC U2 short seq=%u requested=%u transferred=%u`（完成但字节不足）
  - `UAC U2 train end posted=%u completed=%u pattern=%u`
- 结构不变量（离线测试逐条断言）：`_postUacBurst` 内只有 1 个
  `usbDsEndpoint_PostBufferAsync` 调用；`eventWait` 在其后；唯一的超时
  `break` 之前先 `usbDsEndpoint_Cancel`。

## host 侧设计

`host/uac-raw-probe.c` 新增两个选项（默认关闭，v14 的并发模式不变）：

```text
--rearm            滚动窗口：每个完成立即补一个新 URB
--max-urbs N       总提交上限（默认 64，1..1024；必须 >= --transfers）
```

- 旧并发模式一次提交 8 个 16×192B URB（约 128 帧），只覆盖第一个 cave TD；
  这些 URB 全部完成/取消后，设备第 2 个 post 就没有 host 窗口了。
- `--rearm` 把 `--transfers` 当作窗口大小：初始提交 `window` 个，之后每完成
  一个就把同一个 transfer 重新填好提交（`resubmit[i]`），直到用完
  `--max-urbs` 或 `--timeout-ms`；超时统一 cancel 并排空事件。
- 每个完成打印 `urb[n] t=<ms> status=... valid=... bad=... bytes=...`，
  `t` 相对首次提交，便于和设备日志的 `seq` 对齐。
- 该工具在 macOS 上只做编译检查；实机走 Debian raw host（macOS 无法从
  AppleUSBAudio 取回 AS 接口，见 [UAC_U2_BURST.md](UAC_U2_BURST.md)）。

实机命令（v15 用过一次，授权已用尽）：

```sh
./uac-raw-probe --trigger-first --delay-ms 30 --transfers 8 \
    --rearm --max-urbs 64 --timeout-ms 1000
```

> 2026-11-01 01:05 的实机暴露出 rearm 循环的一个计数 bug：`--max-urbs`
> 用完后，已完成的 transfer 仍带着 `done=1` 被下一轮重复计数，
> `in_flight` 无符号下溢，日志出现 `cancel remaining=4294967241/64`。
> 数据总量不受影响（`bytes=3072` 只计一次），但 `bad/valid` 计数被放大。
> **已修复**：处理完成时先清 `done`、`in_flight` 递减加保护、取消数量重新
> 计数；`tests/test_uac_u2_continuous.py` 已加断言。

## 2026-11-01 01:05 实机结果（一次 boot，失败）

命令同上。host：claim/detach/alt1/SET_CUR 全成功；设备日志见
`private/runs/UAC-u2-v15-continuous-20261101`。

| 项 | 结果 |
| --- | --- |
| 设备 seq=1 | `post rc=0x0 urb=388`；`report req=3072 xfer=3072 status=3`；`complete rc=0 3072/3072` |
| 设备 seq=2 | `post rc=0x0 urb=404`；**`no completion within 100ms seq=2 cancel=0x0`** |
| 设备摘要 | **`train end posted=2 completed=1 pattern=1536`** |
| host | `urb[3] t=50ms 2496B` + `urb[4] t=66ms 576B` = **3072B**；`urb[5..64]` 全部 `bad=16 bytes=0` |
| host 总计 | 64 个真实 URB，`valid=57 bad=967 bytes=3072`（日志里的 1847 是上述计数 bug 放大后的值） |
| ring | seq=1 后 box `ISO2`、`trb0 ctl=0x00a01411`（frame 10）、prod=ring+0x200；seq=2 超时后 box/trb 全 0、prod=cons=ring |
| crash | **无**：无新 crash/erpt，设备全程在线，日志无 fatal |
| 结论 | **只有第 1 个 burst 送达**；第 2 个请求没有被 host 服务，100 ms 超时后取消。 |

关键判断：本轮 host 在整段时间里**持续有 URB 在飞**（窗口 8，共提交 64 个），
所以“host 没窗口/没 re-arm”不再是解释。第 2 个请求在驱动里 `rc=0`，但
没有任何 completion，host 侧对应时段全是 transaction error（没有 TD 被服务）。

## v16 状态仪器化（已构建；实机一次 boot 崩溃，未验证）

最可能的失败点是 cave 的接受门（`iso_enter` 开头）：

```asm
ldp x8, x9, [x1, #0x18]   ; prod, cons
cmp x8, x9
b.ne fail_accept          ; 环非空 -> 返回 0，不建 TRB、不响铃
```

`fail_accept` 返回 0，调用方把它当成功（`PostBufferAsync rc=0`），随后没有
TD、没有 completion——与 v15 观察一致。缺的是“第 2 次 post 那一刻
prod/cons 到底是什么”。

v16 只改 app，payload/cave 与 v14/v15 逐字节相同：

| 项 | 值 |
| --- | --- |
| 构建 | `941646e8…`（91955B），`-DUAC_U2_BURSTS=4`；cave `806f54cb…` / 592B |
| 新增日志 | 每次 post 前后 `UAC U2 state {pre,post,done,timeout} seq=… word=… int=… dci=… cycle=… speed=… ring=… prod=… cons=… copy=… empty=…` |
| ring 证据 | 每个 seq 的 post 后都 dump box/trb + 请求表项（不再只 seq=1） |
| 工作目录 | `private/analysis/UAC-u2-v16-submit-state-20261101` |

一次 boot 的判定：

| 观察 | 结论 | 下一步 |
| --- | --- | --- |
| `pre` 行 `prod != cons`（`empty=0`） | cave 门拒绝第 2 次提交 | 修 app：post 前等环空（有界等待，不重试），或让 cave 支持非空环 |
| `pre` 行 `prod == cons`（`empty=1`）但 post 后 box 仍 0 | `iso_enter` 没被调用，问题在驱动提交/门铃路径 | 静态分析 `0x2c520`→`0x302e0` 在第二次提交时的分支，再定 v17 |
| post 后 box `ISO2`/trb 非零，但无 completion | cave 写了 TD，问题在控制器/doorbell | **r2 命中**：两套 TD 都写入，seq2 不被服务；对比 ring base/cycle 与控制器 dequeue |

命令与 v15 相同（`--trigger-first --delay-ms 30 --transfers 8 --rearm
--max-urbs 64 --timeout-ms 1000`），**需要新的授权**；不部署、不重试。

## 2026-11-01 01:41 v16 实机：boot 崩溃（v16 未验证）

- 部署 `941646e8…`（91955B），回读一致；**probe 没有运行**（设备日志无
  `UAC U2 precheck/post/state` 任何一行）。
- 设备日志只有：启动、`UAC u2 patch result=0 record=28`、
  `USB host connected`、一次 alt0 `SET_INTERFACE(0)`（iface 3）。
- 崩溃：usb sysmodule fatal `2162-0002`（Result `0x4A2`），PC `0x19254`；
  creport User Break PC `0x1927c`、LR `0x9668`，栈
  `0x944c/0x9514/0x9534/0x9560/0x40d0/0x3ce0/0x2c584/0x2a3f4/0x2a464`——
  与 2026-10-31 Debian raw 的 usb fatal 签名一致，`0x1927c` 也出现在
  早先 safecave/breaker 轮。
- 环境：开机时设备仍处于上一轮 Debian VM 的 attach 状态；Linux 侧在 probe
  之前已经枚举并做了一次 alt0 `SET_INTERFACE(0)`。
- 判定：**v16 的问题未回答**（仪器化从未执行）；崩溃触发的精确条件未隔离
  （EP0 控制路径 + host 枚举时序）。一次授权消耗，**无重试**。
- 证据：`private/runs/UAC-u2-v16-submit-state-20261101`（`device-log-v16.txt`
  `621ab821…`、`crash/` 两份报告）、
  `private/card-cycles/20261101-u2-v16-submit-state`。
- 运行纪律（下一次）：开机前 Detach/Suspend Debian VM，确保设备不被占用；
  主界面出现后再 attach，并**立即**运行 probe，缩短 Linux 驱动接管窗口。

## 2026-11-01 01:49 v16 r2 实机：cave 门被排除

按新纪律：VM 在开机前 suspend，主界面后 resume，attach `1209:ca57` 并立即
probe。第一次 probe 因枚举未完成报 “not accessible”（无设备交互），随后这次
是唯一一次真实设备交互。

| seq | `pre` | `post` | 结果 |
| --- | --- | --- | --- |
| 1 | prod=cons=ring、copy=`…dff0`、`empty=1` | prod=ring+0x200、box `ISO2`、trb0 ctl=`0x64e01411`（frame 0x64E） | `complete 3072/3`；`done` 行 prod=cons=ring（驱动复位） |
| 2 | prod=cons=ring、`empty=1` | prod=ring+0x200、box `ISO2`、trb0 ctl=`0x72801411`（frame 0x728） | **100 ms 无 completion → cancel=0** |

host：`urb[2] 768B` + `urb[3] 2304B` = 3072B，之后全 bad；
`valid=49 bad=943 bytes=3072`，`cancel remaining=8/64`。

结论：

- **门不是原因**：两次 `pre` 都 `empty=1`，两次 `post` 都出现 `ISO2` box 和
  推进的 prod，cave 确实为第 2 个请求写了 16 Isoch + 16 ED TRB。
- 两套 TD 结构相同（同一 ring base、同一 cycle=1、新 frame），但只有第 1 套
  被控制器服务；host 侧对应时段全是 transaction error。
- 第 1 个完成后，驱动把 prod/cons 复位到 ring base、copy 复位到 `…dff0`
  （`done` 行）；此时控制器已经消费了 0x200 字节。第 2 套 TD 写在 base，
  很可能落在控制器 dequeue 之后，或 `doorbell_tail` 没有让控制器回到 base。
- 下一步（离线）：读 `doorbell_tail`（`0x31c74`）与完成路径，确认 dequeue
  是否被复位、doorbell 目标；候选修法是让 cave 跨请求维护 ring 写入位置，
  或完成时复位控制器 dequeue。**任何时候只允许一个 pending 请求的约束不变。**
- 本轮还出现一个新 erpt `2162-0004`（Data Abort，01:49），无 creport/fatal，
  设备全程在线、日志无 crash 标记；暂未归属，保留为开放项。

## 离线证据（2026-11-01 00:52）

| 项 | 值 |
| --- | --- |
| 工作目录 | `private/analysis/UAC-u2-v15-continuous-20261101` |
| payload | 29 条 / cave 592B；cave `806f54cb…`，与 v14 **逐字节相同** |
| defines | `-DUAC_HOST_PROBE -DUAC_U2_PATCH -DFILE_LOGGING -DUAC_U2_BURSTS=4` |
| NSP | `1c9c6004…`（91352B）；NSO `c45a8d0a…` |
| 结构证据 | ELF `g_u2BurstBuffers` 大小 **0x4000**（v14 为 0x1000），即 4 个独立缓冲 |
| 边界证据 | `-DUAC_U2_BURSTS=5` 在 `uvc_device.c` 的 `#error` 处编译失败 |
| host | `make -C host uac-raw-probe` 以 `-Wall -Wextra -Werror` 通过；参数校验负例 2 个 |
| 测试 | `tests/test_uac_u2_continuous.py`（10 项）+ 既有 `make check` 全绿 |
| 硬件操作 | 0（无 USB/SD/实机） |

`make check` 与 `make links` 的结果记录在 `README_HISTORY.md` 的同一轮条目里。

## 实机结果怎么读

| 现象 | 解释 | 下一步 |
| --- | --- | --- |
| `posted=4 completed=4`，host 总字节 ≥ 6144 | 连续数据路径成立 | 再提高 burst 数/加长窗口；随后才谈 PCM |
| `posted=2 completed=1`，第 2 个 `no completion ... cancel=0` | **本轮实测**；host 全程有 URB，排除 host 窗口 | v16 记录 post 前的 prod/cons，判断 cave 门是否拒绝 |
| 第 1 个就 `complete ... transferred=0` | host 端无数据（旧 0 字节现象） | 停，回到 timing/usbmon 分析 |
| `post skipped: ...` | 门未通过（端点/安装对象/DCI） | 停，对照 precheck 字段 |
| 任一 crash/fatal | 停止，取 crash 报告，不重试 | 交回离线分析 |

## 未证明 / 风险

- 8 个 descriptor-parser NOP 的全局风险仍未隔离（与 v14 相同）。
- 相位连续只保证 buffer 内容连续，不证明 host 侧无丢包、无时钟漂移。
- 4 个 burst 只有 64 ms；不是持续音频，也不是产品验收。
- 未跑 PCM/WAV 检测，未评估与 UVC 视频共存。

## 2026-11-01 16:2x v24 gap probe（离线，0 实机）

v23 的 4 个 burst 都成功，但 wire gap 是 160/162/142 ms（burst 本身 16 ms）：
音频是“16 ms 有数据、~145 ms 空白”，还不是连续流。首要嫌疑是 app 的每-burst
诊断：`_uacLogSubmitState`/`_uacLogRingState`/`_uacLogInstallState` 每次都是
一次 `svcDebugActiveProcess` + 多次读，一个 burst 约 5 次 attach。

v24 只改 app，payload 与 v23 逐字节相同（29 条 / cave 620B：

- `-DUAC_U2_LIGHT_LOG`：跳过成功的 `pre/post/done` state dump、ring dump 和
  install dump；失败/超时路径的 dump 保留；train 结束后的两次 dump 保留。
- 每个 burst 记录相位（`svcGetSystemTick`，19.2 MHz）：
  `loop_ms`（上次 report → 本次 post）、`post_ms`（`PostBufferAsync`，含 cave
  的重放 setup）、`wait_ms`（post → completion）、`report_ms`（completion →
  report 解析）、`online_ms`（两次 report 之间）。
  下一 burst 的 wire gap ≈ `report_ms + loop_ms + post_ms`。

| 项 | 值 |
| --- | --- |
| 构建 | `2b7680ef…`（91996B），NSO `33f2efe9…` |
| defines | `-DUAC_HOST_PROBE -DUAC_U2_PATCH -DFILE_LOGGING -DUAC_U2_BURSTS=4 -DUAC_U2_LIGHT_LOG` |
| payload | 与 v23 相同：29 条 edits / cave `00f38aa9…` 620/684B / header `f4749804…` |
| 工作目录 | `private/analysis/UAC-u2-v24-light-20261101` |
| 测试 | `tests/test_uac_u2_light_log.py`（5 项）+ 既有 continuous 测试更新 |

一次 boot 的判定：

| 观察 | 结论 | 下一步 |
| --- | --- | --- |
| `wait_ms≈16`，`loop_ms`/`post_ms` 小（gap ≈16–25 ms） | dmnt dump 就是 gap | 流水线/连续 post，再验证 8/16 burst 与时钟 |
| `post_ms` 大（>50 ms） | `0x2feb0` 的 memset/清 halt 轮询占主导 | 下一轮 commit-only cave（`regs+0x58` + 清 halt，不 memset） |
| gap 仍 ≈150 ms | 驱动/宿主调度占主导 | cave 侧 tick 探针或改 host 窗口 |
| 任一 crash/fatal | 停 | 读卡取报告，不重试 |

停止条件与以往相同：一次 boot、失败即停、读卡恢复 `52069a44…`。

### 2026-11-01 16:2x 实机结果：gap 96 ms，主项是 cave 的 32 ms 帧 lead

一次部署、一次 boot、一次 probe；4/4 burst 再次成功：

| 项 | v23（重 dump） | v24（light） |
| --- | --- | --- |
| host | 12288B，gap 160/162/142 ms | 12288B，gap **96/96/96 ms** |
| wait_ms | — | 59/59/60/61 |
| post_ms | — | 0/0/0/0 |
| report_ms | — | 20/20/20/19 |
| loop_ms | — | 3/13/14/12 |
| online_ms | — | 84/93/95/94 |

`post_ms=0` 说明重放 `0x2feb0` 在本次状态下几乎不花时间（halt 已清、无
sleep 轮询）。`wait_ms≈60` 的最大项是 cave 的 `frame = MFI/8 + 32`：
TD 的帧号比当前 MFI 晚 32 ms，加 16 ms burst 和 ~12 ms 事件/驱动，正好
≈60 ms。`report_ms≈20` 是 `GetReportData` + `ParseReportData` 的固定开销，
`loop_ms≈12` 是 pattern 填充/日志/flush。下一候选把 cave 的 `+32` 改成
`+4`（一行），期望 `wait_ms→~32`、gap→~66 ms。

**收尾崩溃**：host 收尾（`USB host disconnected` → `USB host connected`）后
`SET_INTERFACE(0) iface=3` 触发 usb sysmodule `svcBreak`（PC +0x1927c，栈
`0x2c584/0x2a3f4/0x2a464`），与 2026-11-01 01:41 v16 r1 boot 崩溃同签名；
发生在 `train end` 之后，数据路径不受影响。已复制 1 份新 crash 报告
（`20d493b5…`），erpt 27 不变。

#### 崩溃的静态定位

崩溃报告（`01793521640_0100000000000006.log`，`20d493b5…`）的 PC 是
`[ad8d36f2]+0x1927c`（`svc #0x26`），LR `+0x9668`——即空消息的通用
`svcBreak` 路径（`0x9650`：`mov w0,wzr; w2=4; bl 0x1927c`）。栈从内到外：

| 帧 | 位置 | 含义 |
| --- | --- | --- |
| `0x40d0` | `bl 0x9540` 的断言点（固定空消息） | 状态机/内存管理断言 |
| `0x3ce0` | `0x3c50` 内 `cbz x0,0x3d1c` 的返回点 | DMA/地址空间映射（`0x3d40`）失败路径 |
| `0x2c584` | `0x2c520` 内 `bl 0x3c50` 的返回点 | 端点 buffer 提交（映射 buffer） |
| `0x2a3f4` | `bl 0x2c520` 的返回点 | 提交包装 |
| `0x2a464` | `0x2a330` 的调用点 | 上层提交/teardown |

`0x3c50` 先检查 `(size|addr) & 0xfff`，不对就返回 `0x1ce8c`，不会断言；
断言发生在 `0x3d40` 的 DMA/IOMMU 映射内部（rodata 附近是
`EndpointTerminateComplete`/`ResettingPort`/`CtrlTransferBuffer` 等状态名）。
因此这是一条**提交/DMA 映射路径的断言**，触发点在 host 重枚举后的
`SET_INTERFACE(0) iface=3`，与 cave 的 lead/日志改动无直接关系；与 v16 r1
boot 崩溃同栈，说明它属于 U2 patch 的 alt0/控制路径遗留风险。

可评估的规避方向（下一轮只选一个）：

1. **host 侧**：收尾时不触发重枚举（probe 保持接口占用/延迟关闭，或先关机
   再释放），避免 host 再发 `SET_INTERFACE(0)`；
2. **app 侧**：alt0 的 `SET_INTERFACE(0)` 不再走 `_ctrlAck`，改为先 cancel/
   停止端点（或直接 stall），看断言是否消失；
3. **接受已知风险**：数据完成后立即关机，接受“数据成功 + 收尾崩溃”，
   把该崩溃留作独立课题。

## v25 lead-4 候选（离线，0 实机）

v24 的 `wait_ms≈60` 里 32 ms 是 cave 的 TD 帧 lead（`frame = MFI/8 + 32`）。
v25 只把这一条改成 `+4`：

- assembly `patches/iso_burst_uac84_dci9_lead4.S`；与 v23/v24 的 cave 只差
  **1 个字节 / 1 条指令**（`0x11008129 add #32` → `0x11001129 add #4`）；
- app 与 v24 相同：`-DUAC_U2_BURSTS=4 -DUAC_U2_LIGHT_LOG`；
- NSP `c27e9103…`（91996B）、NSO `994e7c05…`、cave 620/684B、29 条 edits；
- host 侧同时加 `--keep-alt`（`host/uac-raw-probe.c`，源 `8435e7ed…`）：
  收尾不再发 `SET_INTERFACE(0)`，并在 release 前关掉 libusb 的
  auto-detach，避免内核驱动重新绑定后再设 alt0——这正是 v24 收尾
  `svcBreak` 的触发点。guest 已用 `-std=c11 -Wall -Wextra -Werror` 重建通过
  （新增 `_DEFAULT_SOURCE` 修复 Linux 严格 c11 下的 `useconds_t`）；
- 运行命令：`uac-raw-probe --trigger-first --delay-ms 30 --transfers 8
  --rearm --max-urbs 64 --timeout-ms 1000 --keep-alt`；
- 期望：`wait_ms 60→~32`、gap 96→~66 ms，4/4 burst 不变，收尾不再崩；
- 判定：gap ~66 且 4/4 → lead 是有效杠杆，下一步压 report/loop 或流水线；
  无数据/部分 → 4 ms lead 没落进 host 窗口，停，回退 32 再查 host 提交时序；
  收尾仍崩 → `--keep-alt` 不足，alt0 触发点在别处（回到崩溃的静态定位）。

一次 boot 仍按 v24 的纪律：VM 开机前 suspend、主界面后 attach、probe 一次；
出现 v24 同款收尾崩溃时数据仍有效，但按规则停止并读卡。

### 2026-11-01 22:5x 实机结果：lead-4 太短，v25 否掉

一次部署、一次 boot、一次 probe（`--keep-alt`）：

- host：`claim/alt1/SET_CUR` ok；`done ... bytes=1536`，只有
  `urb[1] t=18ms` 收到 1536B（9/16 包），之后无数据；
- 设备：`train begin count=4`，seq1 `post rc=0`、report
  `req=3072 xfer=0 status=5`、`complete rc=0x748c`，
  `train end posted=1 completed=1 pattern=768`（parse 失败后循环 break）；
  timing `loop=10 post=0 wait=16 report=18 online=45`；
  ring `prod=+0x200 cons=+0x140`、box `ISO2`、TD frame `0x1f0/0x1fa`；
- 判定：**4 ms 帧 lead 太小**。TD 帧几乎与当前 MFI 同步，控制器在取指时
  已经错过前几帧，10/16 ED 完成即报错；回退 32 ms（v24 cave）；
- 收尾：无新 crash/erpt（27/21）；`--keep-alt` 打印了跳过
  `SET_INTERFACE(0)` 的行，收尾崩溃规避被执行，但本轮 train 提前失败，
  不能单独判定规避有效。

下一轮：v24 cave（lead 32）+ `--keep-alt` 复验 4/4 与收尾无崩溃；之后进入
“ring 连续 / 双 buffer 在飞”的流水线设计。

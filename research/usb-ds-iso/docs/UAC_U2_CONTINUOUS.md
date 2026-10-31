# UAC U2 连续 producer（v15 失败；v16 r2 排除 cave 门）

> 状态：三轮相关实机。v15（2026-11-01 01:05）：只完成第 1 个 burst
> （3072/3），第 2 个 post `rc=0` 后 100 ms 无 completion，被取消。
> v16 r1（01:41）：**boot 崩溃**（usb fatal 2162-0002），probe 未运行。
> v16 r2（01:49，VM 开机前 suspend）：host 仍只有 3072B，但设备 `pre/post`
> 日志证明**两次 post 都进了 cave、都写了完整 TD 集**，只有第 1 套被服务——
> **`prod == cons` 门被排除**，问题在 ring 复位/控制器 dequeue。
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

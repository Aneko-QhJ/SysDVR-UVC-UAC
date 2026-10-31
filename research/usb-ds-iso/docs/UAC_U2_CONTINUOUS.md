# UAC U2 连续 producer（v15，实机一次失败）

> 状态：**实机一次（2026-11-01 01:05）**：第 1 个 burst 完成 3072/3，
> 第 2 个 post `rc=0` 后 100 ms 无 completion，被 `usbDsEndpoint_Cancel`
> 取消，`train end posted=2 completed=1`；host 只收到一个 3072B burst，
> 后 3 个没有数据。无 crash。硬件授权已用尽（`remaining=0`），下一次上机
> 需要新的明确授权（见 [RESEARCH_RULES.md](RESEARCH_RULES.md)）。
> 当前事实以 [CURRENT.md](CURRENT.md) 为准。

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

## 下一步候选：v16 状态仪器化（离线，需新授权）

最可能的失败点是 cave 的接受门（`iso_enter` 开头）：

```asm
ldp x8, x9, [x1, #0x18]   ; prod, cons
cmp x8, x9
b.ne fail_accept          ; 环非空 -> 返回 0，不建 TRB、不响铃
```

`fail_accept` 返回 0，调用方把它当成功（`PostBufferAsync rc=0`），随后没有
TD、没有 completion——与本次观察完全一致。现在缺的是“第 2 次 post 那一刻
prod/cons 到底是什么”。

v16（只改 app，不动 payload）：
1. 每次 post **之前**记录 `ring prod cons copy=state[0x28] cycle=state[0x40]`；
2. 每次 post **之后**（不只 seq=1）立即 dump box/trb 与请求表项；
3. 用一次 boot 判断：若 `prod != cons` → 门因环非空拒绝；若 `prod == cons`
   但 ring 仍空 → 问题在驱动提交/门铃路径，再考虑 v17 在 cave 里加
   进入/拒绝码计数器。

这一步只需要新的构建 + 一次授权 boot，不改 payload、不改 host 命令。

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

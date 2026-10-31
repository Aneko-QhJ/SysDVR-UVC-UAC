# UAC U2 连续 producer（v15，离线候选）

> 状态：**离线已构建，0 实机**。硬件授权仍是 `remaining=0`、
> `acquisition_enabled=false`、`next_hardware_authorized=false`；
> 下一次上机需要新的明确授权（见 [RESEARCH_RULES.md](RESEARCH_RULES.md)）。
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

实机命令（**需新授权**）：

```sh
./uac-raw-probe --trigger-first --delay-ms 30 --transfers 8 \
    --rearm --max-urbs 64 --timeout-ms 1000
```

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
| `posted=2 completed=1`，第 2 个 `no completion ... cancel=0` | 与 v11 相同的“第二个请求没有 host 窗口” | 检查 host 是否真的 re-arm（`resubmit` 行）；调窗口/延迟 |
| 第 1 个就 `complete ... transferred=0` | host 端无数据（旧 0 字节现象） | 停，回到 timing/usbmon 分析 |
| `post skipped: ...` | 门未通过（端点/安装对象/DCI） | 停，对照 precheck 字段 |
| 任一 crash/fatal | 停止，取 crash 报告，不重试 | 交回离线分析 |

## 未证明 / 风险

- 8 个 descriptor-parser NOP 的全局风险仍未隔离（与 v14 相同）。
- 相位连续只保证 buffer 内容连续，不证明 host 侧无丢包、无时钟漂移。
- 4 个 burst 只有 64 ms；不是持续音频，也不是产品验收。
- 未跑 PCM/WAV 检测，未评估与 UVC 视频共存。

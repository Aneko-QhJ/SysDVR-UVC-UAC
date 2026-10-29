# A23 serial640 复测方案（2026-10-29 准备）

## 问题

原始 serial640（NSP `c129dce7…`）在 host 80 包后触发 usb `User Break`
（fatal `0x4A2`，栈 `+0x2c584` DMA map），当时结论是 one-in-flight 也只能到
约 5 个 URB。2026-10-29 的 v5 320 包在同一类构建（30 条 runtime edits、alt1
NOP、640 缓冲、`posts == completes` 单飞）下做到 `posts=8 completes=7`、
两页 IOVA 复用、无 fatal。两次结果的差异必须单独定位，不能再用“5 页墙”
直接解释。

## 候选与变量

| 项 | 原始 serial640 | 本次复测 |
| --- | --- | --- |
| NSP | `c129dce7…` | v5 `11d5e9eb…`（trace 只改 `iso_report`） |
| runtime edits | 30（record=29） | 30（record=29） |
| 单飞 | `posts == completes` | 同 |
| 缓冲 | 640 个不同、各一次 | 同 |
| host 窗口 | 10000 包 / 约 10s | 同 |
| host 电源 | 未显式固定 | `caffeinate -dimsu` |
| trace | 无 v5 条目 | v5 ISO9 8 条目 |

主要假设：

1. **10000 包单次 host transfer 的压力**与 320 包不同，5 URB 后触发
   DMA map/fatal；
2. 原始 run 受主机休眠/USB 调度影响，`caffeinate` 可消除；
3. v5 trace 只写 `iso_report` 诊断，理论上不改变 producer，但要用同窗口复测
   排除。

## 主机与读取

```sh
caffeinate -dimsu research/usb-ds-iso/host/iso-stream --transfers 1 --packets 10000
research/usb-ds-iso/host/iso-probe --log status.jsonl --status
PYTHONPATH=research/usb-ds-iso/tools python3 research/usb-ds-iso/tools/decode_a23_trace.py status.jsonl
```

## 判别

| 结果 | 解释 | 下一步 |
| --- | --- | --- |
| 稳定到 ~200 post/completes，errors=0，无 fatal | 旧崩溃不是固有 5 页墙；优先查 10000 包 host transfer/旧构建 | 进入 10s 连续流和 UAC |
| 仍在约 5 post 崩，栈同 `+0x2c584` | 10000 包窗口下仍有设备侧 map/记账边界 | 抓 5/6 post 的 endpoint/URB 字段，查 free tree/in-flight |
| host 大量 zero/bad 但设备不崩 | host/调度问题 | 固定电源、缩短窗口或改 host 传输 |

## 限制

- 一次 boot、一个 10s 窗口、一次 status；失败不重试、不补轮。
- 设备可能再次 usb fatal；失败后只读卡，不取消/不重投。
- 只准备方案，尚未授权部署或开机。

## 实机结果（2026-10-29 18:01）

- 主机：`caffeinate -dimsu iso-stream --transfers 1 --packets 10000` →
  `transfers=1 packets=3392 bad=0 zero=6608`；
- 设备：`ISO runtime patch result=0 record=29`，
  `posts=214 completes=213 errors=0 late=212 attempts=214`；
- status：`config_length=185`、magic ISO9，8 条目仍只在
  `0x80030000`/`0x80040000` 两页间交替；
- **没有 usb fatal，原始 serial640 的 5 URB 崩溃没有复现**。

第一次 preflight 在 USB 枚举后过早执行，`iso-probe` 没拿到 session/status；
同一 boot 内等待设备就绪后重做 preflight（`config_length=185`）才发 stream。
这不消耗数据路径，但说明 host 等待脚本需要把“枚举出现”与“接口就绪”分开。

结论：在 `caffeinate` + 明确 one-in-flight + 640 缓冲下，同一类构建可以稳定
跑满 10s 窗口的 214 个 post；旧 serial640 崩溃更可能是主机休眠/USB 调度或
当时运行状态，而不是 A23 的固有 5 页墙。下一步才是 10s 连续 PCM 与标准 UAC。

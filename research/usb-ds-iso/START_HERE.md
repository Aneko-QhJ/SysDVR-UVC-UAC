# 从这里开始

## 60 秒

1. 读 [docs/CURRENT.md](docs/CURRENT.md)（事实与下一步）。
2. 读 [WORKFLOW.md](WORKFLOW.md)（一轮怎么走）。
3. 从 CURRENT 的“开放问题”里选一个，写 5 行问题卡。
4. 离线准备，跑 `make -C research/usb-ds-iso check`。
5. 实机按“当前边界”里的授权执行；插卡/开机前通知用户，失败即停。

## 不要做

- 不要把 [docs/STATUS.md](docs/STATUS.md) / [docs/PROGRESS_HANDOFF.md](docs/PROGRESS_HANDOFF.md)
  里的旧“下一项仅……”当成当前指令。
- 不要覆盖、移动或清理 `private/` 里的原始证据。
- 不要用模型通过、保存成功、超时或安静采样推断 I/O 已交还。
- 不要越过“当前边界”的授权范围部署、写卡、启动接收器或开机测试。
- 用户说“部署”只等于把文件拷贝到卡上；插卡与开机由用户执行，代理只提前通知，不自行开机。
- 不要把“主机 raw 正确”单独当成严格传输通过，也不要把它改判成失败。

## 存储与继续研究

2026-10-29 已完成一次性精简；后续研究不设容量门禁。
当前源码、输入、原始实机证据与票据均保留。过时离线审计和恢复包已按用户要求精简，
不保证复现任意旧版本。旧路径缺失时先查 [STORAGE.md](STORAGE.md) 的处置清单，
不要为重放历史流程补回整套旧树。常规测试产物使用临时目录，结束后清理。

## 当前边界（2026-11-03 22:1x）

- 实机授权：2026-11-01 16:19 起常设授权“部署测试不再需要授权；通知插卡/
  开机即可”（一次 boot、失败即停、不重试）。
- **当前最佳配置**：
  - 设备镜像 **v30e `1737eb35…`**（93050 B，= v29v payload 逐字节相同）：
    cave `pipe_quad_log.S` 548/684 B、`ISO_ENTRY=0x300`、3 在飞、miss 立即
    cancel + 重投、`STREAM_POSTS=512`、`MAX_RECOVERIES=128`、quiet + evlog。
  - host：`uac-raw-probe4 --trigger-first --delay-ms 30 --packets 16
    --transfers 32 --rearm --max-urbs 2048 --timeout-ms 10000 --keep-alt`
    （probe4 = probe3 把 `MAX_URBS_TOTAL` 1024→4096；每套约消耗 2 个 URB）。
- **长跑（v30e，8.885 s）**：512/512 posts → **498 段 / 1529856 B**、host
  1533696 B、覆盖 **89.7%**（host 90.4%）、**5 次 code-23**（0.56/s）、
  `max_gap_ms=92`、无 crash/fatal。事件在 353/2209/4049/5905/7745 ms，
  **间隔 ~1.85 s —— 新线索**。
- **短跑最好一轮（v30a，32 在飞）**：253 段 / 777216 B / 94.1% / 1 次 /
  `max_gap 78`；同配置复跑 v30d 247 段 / 3 次 / 89.4% → 单轮不能排序
  16/32/64，**8 深明显更差**站得住。
- **已定论**：
  - miss = 控制器的 **code 23（Missed Service）**；驱动 `0x31274` 对 23
    只置 halt、**不复位 ring**，所以 cave 无法 rearm，只能靠 app 收到
    `status=5` 立刻 cancel + 重投 → ~80–92 ms 内恢复、丢 1 套。
  - 设备侧其它假设全部否掉：lead 16/24/40、在飞 4、空 ring 门、memset
    长度、host 预排 8/16。
- **宿主侧事实**：设备在 **Bus 001 / `ehci-pci`**（不是 xHCI），内核没有
  ehci tracepoint；可用 **usbmon bus 1** 或 probe 的 per-packet detail
  （`urb[N] detail p<idx>=<status>/<len>`）。
- **下一步**：同配置复跑一次，确认 5 次事件的 ~1.85 s 间隔是否重现；若要
  >10 s 样本，需把 probe 的 `--timeout-ms` 上限与 run deadline 拆开。
- **已知小缺口**：USB 字符串描述符未实现（宿主只显示 VID/PID）；
  8 个 descriptor-parser NOP 仍未隔离。
- 卡：安全 `52069a44…` 已恢复并弹出（22:1x）；VM 挂起；v30e 证据已归档。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [docs/CURRENT.md](docs/CURRENT.md) | 唯一当前状态；每轮更新 |
| [WORKFLOW.md](WORKFLOW.md) | 最小流程；怎么开一轮 |
| [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) | 安全边界与验收定义 |
| `docs/A23_*.md` | 专题细节；完成后只读 |
| [README_HISTORY.md](README_HISTORY.md) | 时间线；只追加 |
| `private/` | 原始字节；只读 |

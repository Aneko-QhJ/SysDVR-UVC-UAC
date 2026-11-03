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

## 当前边界（2026-11-03 12:2x）

- 实机授权：2026-11-01 16:19 起常设授权“部署测试不再需要授权；通知插卡/
  开机即可”（一次 boot、失败即停、不重试）。旧 A23 票据的
  `remaining=0`/`next_hardware_authorized=false` 是 eMMC 采集额度字段，不是
  UAC 回合的授权状态。
- **当前最佳 v29h（22:16）**：64/64 posts、**62×3072（190464 B）**、
  host==device、**misses=2 / recoveries=0**；v29h/i/j 的 alt0 收尾未崩，
  但 map-soft 只覆盖 `0x3fe0`，另一入口 `0x3dac` 仍会崩（11-03 已复现）。
- 最近否定：v29i（4 在飞/4 套环）miss 2→3；v29j（lead 16）miss 2→4、54 段。
- **v29k（lead 40）实机无效**：12:06 第一次开机时 VM 未 suspend 就 attach，
  host 枚举在 probe 前触发 alt0 崩溃（0 数据）；lead 40 仍未验证。
- **候选 v29l（lead 40 + map-soft-2）已离线构建**：NSP `49956ad1…`
  （92676 B），46 条 edits；`0x3dac` 也改成 `0x409c` 错误收尾，待一次 boot。
- 下一步：部署 v29l，按严格 VM 纪律（开机前 suspend/detach、主界面后
  attach、确认 guest 只在 attach 后看到 `1209:ca57`）跑一次。目标 0 miss，
  再谈占空比与 48 kHz 连续。
- 仍未隔离：DCI-9 cave `ISO_ENTRY=0x270`、8 个 descriptor NOP；A23 线挂起。
- 卡：安全 `52069a44…`，已弹出；设备现场状态不推定。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [docs/CURRENT.md](docs/CURRENT.md) | 唯一当前状态；每轮更新 |
| [WORKFLOW.md](WORKFLOW.md) | 最小流程；怎么开一轮 |
| [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) | 安全边界与验收定义 |
| `docs/A23_*.md` | 专题细节；完成后只读 |
| [README_HISTORY.md](README_HISTORY.md) | 时间线；只追加 |
| `private/` | 原始字节；只读 |

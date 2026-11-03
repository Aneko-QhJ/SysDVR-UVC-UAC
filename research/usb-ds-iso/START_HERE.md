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

## 当前边界（2026-11-03 13:1x）

- 实机授权：2026-11-01 16:19 起常设授权“部署测试不再需要授权；通知插卡/
  开机即可”（一次 boot、失败即停、不重试）。旧 A23 票据的
  `remaining=0`/`next_hardware_authorized=false` 是 eMMC 采集额度字段，不是
  UAC 回合的授权状态。
- **当前最佳 v29m 重复轮**：64/64 posts、**63×3072（193536 B）**、
  host==device、**misses=1 / recoveries=0**、无 crash/fatal。
- **方差**：同一 NSP 首跑 58 段 / 3 miss / 1 recover，重复轮 63 / 1 / 0；
  单轮结果要至少两次重复才能下结论。
- 最近否定：v29i（4 在飞/4 套环）miss 2→3；v29j（lead 16）54 段；v29k
  （开机纪律违规）0 数据；v29l（lead 40）58 段。
- 收尾安全：v29m 两轮枚举 5 次 alt0 都无 `svcBreak`、无新 crash/fatal；
  v29l 的 `2162-0004` 未复现。
- **诊断候选 v29n 已离线构建**：NSP `5421884e…`（92960 B），payload 与
  v29m 相同，只在 app 加 `UAC U2 rearm race` 日志，用来区分 cave 空 ring
  rearm 与驱动 `0x30ff4`；待一次 boot。
- 下一步：部署 v29n 跑一次，检查 rearm-race 行是否与 miss 对齐；若对齐，
  修 cave rearm 竞态，否则查 `0x30ff4`。目标 0 miss。
- 仍未隔离：DCI-9 cave `ISO_ENTRY=0x270`、8 个 descriptor NOP；A23 线挂起。
- 卡：安全 `52069a44…` 已恢复并弹出；设备现场状态不推定。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [docs/CURRENT.md](docs/CURRENT.md) | 唯一当前状态；每轮更新 |
| [WORKFLOW.md](WORKFLOW.md) | 最小流程；怎么开一轮 |
| [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) | 安全边界与验收定义 |
| `docs/A23_*.md` | 专题细节；完成后只读 |
| [README_HISTORY.md](README_HISTORY.md) | 时间线；只追加 |
| `private/` | 原始字节；只读 |

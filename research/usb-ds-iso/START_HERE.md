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

## 当前边界（2026-11-03 19:0x）

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
- **v29n 确认了 rearm race**：4 条 `UAC U2 rearm race` 与 4 次 miss
  一一对应（60 段、184320 B、host==device）；是 cave 空 ring rearm 的
  `0x2feb0` memset wipe 了 pending completion，不是 `0x30ff4`。
- **v29o 未消除 miss**：memset 缩到 0xf00 后仍是 62 段 / 2 miss / 2 条
  rearm race（1:1）；丢的是 rearm 本身与刚发出的 set 的竞争，不是 mailbox。
- **v29p 是退步**：57 段 / 4 miss / 1 stall；跳过非 base 的 rearm 后
  控制器停住（cons 冻结）。base 门判据不成立，回退 v29m（63/1，最好）。
- **v29q 实机：测量开销就是空档来源**。payload 与 v29m 逐字节相同，只去掉
  逐 post 日志与 dmnt dump：span **1201 ms**（v29p 2609）、host 覆盖
  **81.7%**（v29p 35.3%）、59 段、misses=2、recoveries=1、无 crash/fatal。
  扣掉唯一一次 181 ms 空档后，64 post / 1024 ms = **16.0 ms/套**，节奏已对。
- **当前最佳配置 = v29q**（NSP `8e81d119…`，92350 B；payload 同 v29m，
  app 加 `-DUAC_U2_QUIET_PIPE`，不要再用 `CURSOR_DIAG` 做节奏实验）。
- **下一个杠杆**：那一次 miss 的恢复（驱动 `0x30ff4` 置 halt → app 100 ms
  阈值才发现 → cancel → +32 ms lead，共 ~176 ms 无数据）。
- **候选 v29r 已建**：NSP `00c516cb…`（92339 B），payload 同 v29q，
  `-DUAC_U2_STALL_MS=32`（默认 100，范围 16..1000）。看 `max_gap_ms`
  能否从 181 降到 ~70–90；若不变，时间是驱动 `regs+0x78` 轮询占的。
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

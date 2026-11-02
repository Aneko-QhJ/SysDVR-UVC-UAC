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

## 当前边界（2026-11-02 22:2x）

- 实机授权：2026-11-01 16:19 起用户常设授权“部署测试不再需要授权；通知插卡/
  开机即可”（v24–v29c 依此执行：一次 boot、失败即停、不重试）。旧 A23 票据的
  `remaining=0`/`next_hardware_authorized=false` 是 eMMC 采集额度字段，不是
  UAC 回合的授权状态。
- 最后实机：2026-11-02 21:00 **v29f miss 容忍，数据最好一轮**。host
  **187392 B**（t=34–2610ms），设备 **posted=64 / completed=64 /
  61×`3072/3` / misses=3 / recoveries=0**；3 次 miss 只丢一套、无 cancel
  连锁，**host bytes 与设备完全相等**。
- **收尾崩溃**：`pipe end` 之后 host 断开/重连、重复 `SET_INTERFACE(0)`，
  usb sysmodule User Break（base+0x19280，fatal PC +0x19254），与
  v16/v24/v26A 同签名。
- 最后实机 **v29g（21:10）**：数据 **193536 B（63×3072）、misses=1**，host 与
  设备相等；但 alt0 的 `teardown cancel rc=0x0 wait=0xea01` 执行后仍崩
  （+0x1927c）——**app 侧 cancel 不够**。
- 最后实机 **v29h（22:16）**：数据 **190464 B（62×3072）、misses=2**，
  host==device；**收尾 alt0 只返回错误，控制台没有崩**，crash/fatal 基线
  不变——**v16 起的收尾崩溃已关闭**。
- 下一步：把 miss 降到 0（4 在飞或 lead 32→16），再测 ~47% 占空比与 48 kHz
  连续。详见 [docs/CURRENT.md](docs/CURRENT.md)、
  [docs/UAC_U2_PIPELINE.md](docs/UAC_U2_PIPELINE.md)。
- 仍未隔离：收尾 `SET_INTERFACE(0)` 的 usb `svcBreak`（`--keep-alt` 不够）、
  DCI-9 cave `ISO_ENTRY=0x270`、8 个 descriptor-parser NOP。
- 占空比仍约 47%（16 ms 音频 / ~34 ms 墙钟），48 kHz 连续不成立；UAC 保持禁用。
- v29h 卡已恢复 `52069a44…`、删日志与新 erpt、安全弹出；设备现场状态不推定。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [docs/CURRENT.md](docs/CURRENT.md) | 唯一当前状态；每轮更新 |
| [WORKFLOW.md](WORKFLOW.md) | 最小流程；怎么开一轮 |
| [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) | 安全边界与验收定义 |
| `docs/A23_*.md` | 专题细节；完成后只读 |
| [README_HISTORY.md](README_HISTORY.md) | 时间线；只追加 |
| `private/` | 原始字节；只读 |

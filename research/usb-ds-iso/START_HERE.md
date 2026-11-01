# 从这里开始

## 60 秒

1. 读 [docs/CURRENT.md](docs/CURRENT.md)（事实与下一步）。
2. 读 [WORKFLOW.md](WORKFLOW.md)（一轮怎么走）。
3. 从 CURRENT 的“开放问题”里选一个，写 5 行问题卡。
4. 离线准备，跑 `make -C research/usb-ds-iso check`。
5. 需要实机时，先取得明确授权；用户说“继续”不等于授权开机或部署。

## 不要做

- 不要把 [docs/STATUS.md](docs/STATUS.md) / [docs/PROGRESS_HANDOFF.md](docs/PROGRESS_HANDOFF.md)
  里的旧“下一项仅……”当成当前指令。
- 不要覆盖、移动或清理 `private/` 里的原始证据。
- 不要用模型通过、保存成功、超时或安静采样推断 I/O 已交还。
- 不要在未授权时部署、写卡、启动接收器或开机测试。
- 用户说“部署”只等于把文件拷贝到卡上；开机/运行仍需单独的明确信号。
- 不要把“主机 raw 正确”单独当成严格传输通过，也不要把它改判成失败。

## 存储与继续研究

2026-10-29 已完成一次性精简；后续研究不设容量门禁。
当前源码、输入、原始实机证据与票据均保留。过时离线审计和恢复包已按用户要求精简，
不保证复现任意旧版本。旧路径缺失时先查 [STORAGE.md](STORAGE.md) 的处置清单，
不要为重放历史流程补回整套旧树。常规测试产物使用临时目录，结束后清理。

## 当前边界（2026-11-01 16:10）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`
  （v23 的单次授权已用完；下一次需新的明确授权）。
- 最后实机：2026-11-01 16:0x **v23 re-arm，成功**。host `bytes=12288`
  （4 个 3072B burst，t=34/194/356/498 ms）；设备 `posted=4 completed=4`，
  seq1..4 每个 `complete 3072/3`，无 crash；卡 erpt 27 / crash 21 与部署前
  相同。
- 结论：**缺失步骤是端点上下文 commit（`regs+0x58`）+ 清 halt
  （`regs+0x54/0x50`）**。每 burst 重放驱动端点 setup `0x2feb0` 后，v22 之前
  “只有第一个 TD 集被取指”的墙被打破（第一次 >1 burst，12288B）。
- 附带发现：DCI-9 cave 的 `ISO_ENTRY=0x270` 仍指向 DCI 7 对象，cave 事件
  路径自 v14 起未执行；本轮未修，需单独一轮。
- 下一阶段：把“每 burst 重放 `0x2feb0`”收敛为“首 burst 后只做 commit/清
  halt”或让 ring 跨 burst 连续，验证 8/16 burst 与更短间隔，再做持续流/
  时钟；**上机需新授权**；详见
  [docs/UAC_U2_ENDPOINT_CONTEXT.md](docs/UAC_U2_ENDPOINT_CONTEXT.md)。
- 8 个 descriptor-parser NOP 的全局风险仍未隔离。
- 卡恢复 `52069a44…`、删日志、安全弹出；设备现场状态不推定。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [docs/CURRENT.md](docs/CURRENT.md) | 唯一当前状态；每轮更新 |
| [WORKFLOW.md](WORKFLOW.md) | 最小流程；怎么开一轮 |
| [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) | 安全边界与验收定义 |
| `docs/A23_*.md` | 专题细节；完成后只读 |
| [README_HISTORY.md](README_HISTORY.md) | 时间线；只追加 |
| `private/` | 原始字节；只读 |

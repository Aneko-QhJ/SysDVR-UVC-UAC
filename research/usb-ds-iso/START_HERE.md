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

## 当前边界（2026-11-01 15:05）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-11-01 14:4x **v22 alt-cycle**。host `cycle0` 3072B、
  `cycle1..3` 全 0；设备有 4 次 post（alt0 清 `burstPosted` 生效），但只有
  seq1 完成；每周期 precheck 的 install object/table 相同、installed=1。
- 结论：**alt0→alt1 不重装端点**，v22 否掉“每个 burst 用新端点”。
- **v23 离线（15:0x）**：安装器 `0x295d0` 只遍历描述符；装点的是
  `0x2fd30 → 0x2feb0`（写 64B 端点上下文 + `regs+0x58` commit + 清
  `regs+0x54/0x50` halt）。完成错误路径 `0x30ff4` 重写 ring/上下文却
  **不 commit**（候选机制：第二个 TD 集因此不再被取指）。附带发现 DCI-9 cave 的
  `ISO_ENTRY=0x270` 指向 DCI 7 对象（cave 事件路径自 v14 起未执行），本轮不修。
- 下一阶段：**v23 候选已离线构建**（`d984f729…`，91927B，cave 620B，
  每 burst 重放 `0x2feb0`）；用 v16 r2 的 host 命令 + `-DUAC_U2_BURSTS=4`
  一次 boot；4 个 burst 都成功 → commit 是缺失步骤；仍只有 seq1 → 下一轮
  做只读上下文诊断。**上机需新授权**；详见
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

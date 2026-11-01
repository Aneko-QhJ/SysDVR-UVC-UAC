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

## 当前边界（2026-11-01 14:30）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-11-01 03:0x **v20 per-ED**（VM 开机前 suspend，attach 后
  立即 probe）。host 仍只有 3072B；seq1 的 per-ED 完成正常，但 `done` 仍然
  **prod=cons=ring**，seq2 仍 100 ms 无 completion。
- 结论：**per-ED 完成不是差异点**；驱动的 ring 复位与“第 2 套 TD 不被取指”
  没变。
- 下一阶段：**v21 `ed52a9d7…`（91954B）已离线构建**（0 实机）：burst 2..N
  之前、无在飞请求时调用一次 `usbDsEndpoint_Cancel`，记录 rc 与
  `after-cancel` 状态，验证它是否复位端点/控制器 dequeue。**需新授权**；
  详见 [docs/UAC_U2_RING_RESET.md](docs/UAC_U2_RING_RESET.md)。
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

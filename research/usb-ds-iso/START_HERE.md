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
- 不要把“主机 raw 正确”单独当成严格传输通过，也不要把它改判成失败。

## 存储与继续研究

2026-10-29 已完成一次性精简；后续研究不设容量门禁。
当前源码、输入、原始实机证据与票据均保留。过时离线审计和恢复包已按用户要求精简，
不保证复现任意旧版本。旧路径缺失时先查 [STORAGE.md](STORAGE.md) 的处置清单，
不要为重放历史流程补回整套旧树。常规测试产物使用临时目录，结束后清理。

## 当前边界（2026-10-31 02:24）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-10-31 02:19–02:21 U2 v7（一次 boot）：
  `SET_INTERFACE(0)→(1)` 后 alt1，2 次 SET_CUR；precheck
  `obj=0x13f737b038`（manager `0x13f736d000` + `0xa1038`）、`installed=1`、
  `table=0x13f73796f0`，门通过；report count=1/id=388/3072/3072/status=3，
  complete `rc=0 3072/3072`；但 WAV 全零、无 crash。已恢复 `52069a44…`
  并安全弹出。
- **已确认**：安装对象 `[manager+0x229b8] = base+0x17b038` 和
  `installed==1 && table!=0` 门成立；设备侧 completion 已在 v3/v7 两次
  通过，v6 的空报告未复现（v7 仅多日志）。门/对象/report 生成**不是**
  剩余阻塞。
- 当前工作：U0、U1a、U1b 通过；U2 的 host 16/16 与 PCM 未测，WAV 仍全零。
  主机内核显示 143 个 EP `0x84` IsochronousRequest 以 `0xe00002ed`
  完成，但 **host engine 到 02:20:07.788 才 `starting`，触发在 02:20:04–05，
  16 ms burst 早于真正的流启动**；WAV 只有 0.86 s。错误包含启动期失败，
  不能先断定端点已死。下一步是 **host 时序实验**：ffmpeg 录 8 s，等
  engine `starting`/约 6 s 后再 SET_CUR；若 WAV 出现 1 kHz 段，根因是
  时序；若仍零，再查 EP `0x84` 端点/ED/TRB。下一次实机需新的明确授权。
- 最近一次短包实机：2026-10-27 513..528，主机收到 384B 正确短包；设备
  `capture`/`EXE3` 保存失败 `0xD401`，非严格通过，不补试。路径修正版已
  打包并绑定新 recipe 入口、通过包/入口审计，短包复测同样需要新授权。
- 设备日志已回收，SD 已安全弹出；当前设备现场状态不推定。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [docs/CURRENT.md](docs/CURRENT.md) | 唯一当前状态；每轮更新 |
| [WORKFLOW.md](WORKFLOW.md) | 最小流程；怎么开一轮 |
| [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) | 安全边界与验收定义 |
| `docs/A23_*.md` | 专题细节；完成后只读 |
| [README_HISTORY.md](README_HISTORY.md) | 时间线；只追加 |
| `private/` | 原始字节；只读 |

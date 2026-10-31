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

## 当前边界（2026-10-31 17:52）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-10-31 17:45 v7 时序实验（一次 boot）：
  `--hold-alt1` 后 ffmpeg 打开，engine 于 17:45:09.774 `starting`；
  17:45:15.429 `--trigger-only` 发 1 次 SET_CUR。设备侧
  `obj=0x71b297b038`、`installed=1 table=0x71b29796f0`、post rc=0、
  report count=1、complete `3072/3072`；但 host 内核从 17:45:15.609
  起出现 EP `0x84` transaction error，到 17:45:29.994 共 **1394 个**；
  ffmpeg 挂起、无 WAV。已恢复 `52069a44…` 并安全弹出。
- **时序假设被排除**：engine 比 trigger 早 5.7 s，错误与 cave post 强相关；
  设备侧 3072 仍是 cave 16×192 记账，不是 host 收数证据。
- 当前工作：U0、U1a、U1b 通过；U2 host 16/16 与 PCM 未测。下一步离线查
  **post/TRB/doorbell**：endpoint `+0x42` DCI、`+0x40` cycle、doorbell
  目标（应为 9）、Isoch/ED 运行值；对比 A23 已工作的 EP `0x83`。
  下一次实机需新的明确授权。
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

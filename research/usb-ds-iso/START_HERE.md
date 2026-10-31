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

## 当前边界（2026-10-31 18:05）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-10-31 18:00 v8（一次 boot）：precheck `dci=9 cycle=1`、
  `obj=0x1a88f7b038`、`installed=1 table=0x1a88f796f0`，门通过；post rc=0、
  report count=1、complete `3072/3072`。host engine 18:00:10.309 `starting`，
  18:00:15.992 trigger；18:00:16.194 起 EP `0x84` transaction error，到
  18:00:39.999 共 **2255 个**；ffmpeg 再次挂起、无 WAV。completion 后的
  ring box/trb 全零（可能已被 driver 清理）。已恢复 `52069a44…` 并安全弹出。
- **DCI 已确认正确**（9）；completion 后的空 ring 不能证明 cave 未写。
  v9 `0c339a15…`（90741B）在 post 返回后、eventWait 前立即 dump ring/box/
  trb；未部署、0 实机。下一次实机需新的明确授权。
- 当前工作：U0、U1a、U1b 通过；U2 host 16/16 与 PCM 未测。下一步是
  **v9 一次授权 boot**：只需 hold alt1 → trigger-only → 1 s → `--alt=0`，
  不启动 ffmpeg（避免再次挂起）；post 返回后立即 dump ring/box/trb。
  若仍全零，查 ring 地址/cave 写入；若有数据但 ctl/frame 异常，再改 cave。
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

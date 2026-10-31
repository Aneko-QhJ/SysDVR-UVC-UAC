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

## 当前边界（2026-10-31 22:55）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-10-31 22:40，Debian 13 VM + v11。Linux claim AS 成功
  （`auto_detach=0`、`detach[3]=0`、`claim[3]=0`）；raw 16×192
  `valid=16 bad=0 bytes=0`。首次尝试消耗 one-shot；`--trigger-first
  --delay-ms 30` 只得到 packet0 0 字节、其余 bad。
- **启动游戏后系统 `usb` sysmodule fatal 2162-0002**（PC 0x19254，stack
  含 0x2c584/0x2a3f4/0x2a464）。已复制 crash/fatal/erpt 报告，卡恢复
  `52069a44…`、删日志、安全弹出。
- **U2 硬件线暂停**：最可疑 crash 根因是 v11 train 第二个 post 在 100 ms
  超时后未取消；host 恢复 alt0 时 usb 模块在 teardown 遇到 pending ISO
  request（stack `0x2c584` 在 `0x2c520` unmap 路径）。另发现 UAC cave
  的 `iso_event` 仍过滤 A23 的 DCI 7，UAC DCI 是 9。离线已构建 **v14
  `4ba21107…`**（单 post + 超时 cancel + DCI9，91101B）；下一轮 raw host
  用 fresh boot + `--trigger-first --delay-ms 30`/`--transfers` 匹配
  +32 frame。仍未解释前不上机。
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

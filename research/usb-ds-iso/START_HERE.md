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

## 当前边界（2026-11-01 02:15）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-11-01 02:10 **v17 ring-advance**（VM 开机前 suspend，attach
  后立即 probe）。host 仍只有 3072B；设备 `ring advance seq=2 … to=ring+0x200
  rc=0`、seq2 `post` prod=`ring+0x400`、box `ISO2`——第 2 套 TD 正好写在控制器
  dequeue 的下一槽，仍然 100 ms 无 completion。
- 结论：**位置假设被否**；ring 位置不是阻塞点。新首要假设是 cave 对 DCI 9
  事件不调用 `event_original`，跳过了 driver 的事件确认/端点重启（相关代码在
  `0x31324`/`0x311a8`，掩码在 `[manager+0x22A5C]`）。
- 下一阶段：**v18 仪器化**（只改 app）：读 `[module+0xFCA5C]` pending 掩码与
  endpoint `+0x0A`，post 后 dump prod 处 TRB；若 `bit9=1`，在 cave 里复刻
  清位/轮询/门铃序列。**需新授权**；详见
  [docs/UAC_U2_RING_RESET.md](docs/UAC_U2_RING_RESET.md)。
- 8 个 descriptor-parser NOP 的全局风险仍未隔离。
- 卡恢复 `52069a44…`、删日志、安全弹出；硬件线暂停，下一次需新授权。
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

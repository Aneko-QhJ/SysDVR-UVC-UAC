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

## 当前边界（2026-11-01 02:05）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-11-01 01:49 **v16 r2**（VM 开机前 suspend，attach 后立即
  probe）。host 仍只有 3072B（urb2/urb3），但设备 `pre/post/done` 日志显示
  **两次 post 都进了 cave 并写了完整 TD 集**（`prod=ring+0x200`、box `ISO2`、
  frame 0x64E→0x728）；seq1 `complete 3072/3`，seq2 100 ms 无 completion。
- 离线结论：**cave `prod == cons` 门被排除**，doorbell 也确实响了（`rc=0`）；
  驱动在完成时把 prod/cons/copy 复位回 base，控制器 dequeue 已过 0x200，
  第 2 套 TD 落在 dequeue 之后——见
  [docs/UAC_U2_RING_RESET.md](docs/UAC_U2_RING_RESET.md)。
- 下一阶段：v17 `ef1e63c0…`（92472B）诊断已构建：post 2..N 前用 dmnt 把
  prod/cons 推到 `ring+(seq-1)*0x200`，验证 dequeue 位置假设。**0 实机，
  需新授权**；若成立，后续做 cave 自维护/流水线版本。新 erpt `2162-0004`
  （无 creport/fatal）仍未归属。
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

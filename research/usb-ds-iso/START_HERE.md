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

## 当前边界（2026-10-30）

- 硬件授权：`remaining=0`、`acquisition_enabled=false`、`next_hardware_authorized=false`。
- 最后实机：2026-10-30 20:26–20:29 U2 no-report 诊断（一次 boot）：首次
  completion `rc=0 requested=3072 transferred=3072`（report 修复成立）；随后
  第二次 SET_CUR/alt 路径 usb 崩溃（同一 map 断言）；已恢复 `52069a44…` 并
  安全弹出。此前 15:36 安全接受版空报告后断言、14:39 retrigger 崩溃
  （`db97b6e7…` dangerous）、14:18 第一次 U2 未 post；更早的 U1b/U1a/U0d
  均通过；全部未测 PCM。
- 最近一次短包实机：2026-10-27 513..528，主机收到 384B 正确短包；设备
  `capture`/`EXE3` 保存失败 `0xD401`，非严格通过，不补试。
- 当前工作：U0、U1a、U1b 通过；U2 producer 实机六次均未通过（未触发 / 崩溃 /
  安全跳过 / post 后崩溃 / breaker 断言 / 安全接受后完成+断言），no-report
  诊断第七次 completion 3072 通过但随后控制/alt 路径崩溃。离线已解码：fake-accept
  让请求未真正入队，清理时区间映射重复插入 → `0x40cc` 断言，**返回 0 的绕过
  不可行**；空报告 `0x748c` 指向无匹配/空条目。U2 实机线已暂停，继续的前提是
  先完成 report/unmap/一次性 post 的设计与离线验证；设计草案见
  [docs/UAC_U2_QUEUE_COMPAT_DESIGN.md](docs/UAC_U2_QUEUE_COMPAT_DESIGN.md)
  （实机一次：completion 3072 通过，随后控制/alt 路径崩溃；dangerous，不再部署）；
  queue-object 修正版 `56b7f8ee…` 实机一次：1 次 SET_CUR 未崩溃，但端点未安装
  （`installed=0 table=0`）、completion 为空。带 installed/table 门的 v3
  `c80fa717…` 实机一次：`--require-alt1` 拦截 alt0；`--force-alt1` 后
  installed/table 非零，门通过，completion `3072/3072`，无崩溃；host 16/16
  与 PCM 未测。v4 `c33d0d07…` 实机一次：host alt1 但未发 `SET_INTERFACE(1)`，
  installed=0、门跳过、WAV 全零；host 已改为总是发 `SET_INTERFACE(1)`。
  路径修正版已打包并绑定新 recipe 入口、通过包/入口审计，短包复测同样需要
  新授权。
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

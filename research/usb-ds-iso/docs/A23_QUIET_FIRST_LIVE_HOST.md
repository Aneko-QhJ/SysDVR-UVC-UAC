# quiet 候选首次实测：主机结果与待回收材料（2026-10-16）

用户在说明一次诊断及“先主机预等待，再提示开机”后回复“开始”，据此签发并消费
唯一一次新记录。Mac 成功记录 begin/注册/初始排空/WAITING，随后提示用户开机。
唯一 HS 新接口出现，完成一次交接，等待器关闭后执行固定 SDK 请求链。没有重试。

用户在运行中询问“开机要等 SysDVR 启动完成吗”，已说明无需等显示提示，保持数据线
连接并正常进入 CFW 即可，由主机等待新接口。此后主机流程正常退出，但内容验收失败。

## 已取得的主机证据

| 项目 | 本次观察 |
| --- | --- |
| 新接口 | 唯一新 HS 到达，一次 handoff；初始没有匹配，等待日志 13 行顺序通过 |
| 控制 | 一次目标触发，完成状态 0；主机调用开始至回调约 0.3565ms，未超时 |
| ISO | 一次提交、一次回调，overall=0，约 183.294ms 完成，无超时、无 abort |
| 960 个 transaction | 状态均为 0，但实际长度全部为 0，没有 active transaction |
| 原始缓冲 | 184320 字节，全零；不满足期望的 16 包载荷 |
| STATUS_before | IDLE/state0、sequence0 |
| STATUS_after | sequence1、state4、post_result0、URB/report ID387、requested3072、transferred0、urb_status2、report_count1/report_result0 |
| 主机结束 | 接收器退出码 0，closed=true、storage_retained=false、unresolved=false，原流程已封存 |
| 验收 | payload_matches=false、host_observation_complete=false、hardware_verified=false；新记录 failed_no_retry/remaining0 |

这些耗时均来自同一主机时基，未与设备 tick 直接相减。主机完成状态 0、接收器退出码
0 不等于收到有效载荷；设备 STATUS 的值按原始协议保留，不由主机状态覆盖。

与 10-13 旧失败相比，本次没有重现控制 16ms 超时/一次 abort，且 STATUS 的 sequence
已从 0 更新为 1。这是不同候选、不同启动/等待条件下的新观察，不能直接认定 quiet
消除了原问题，更不能把文本日志成本、共享 SETUP 覆盖或主机帧单位判为已确认根因。
设备 EXE3/trace 尚未回收，物理同 run 及完整软件证据链还不能认证。

## 材料与当前状态

新可变记录：`private/analysis/A23-quiet-once-20261016-interface2.json`，已消费，
当前 `failed_no_retry/remaining=0/acquisition_enabled=false`。它与旧三票据、旧三份
offline-record 分离；不补次、不再次启动同一工作流。

| 材料 | 位置 |
| --- | --- |
| 授权/签发快照 | `private/analysis/A23-quiet-live-issuance-20261016-021040` |
| 主机 run（18 条） | `private/runs/A-A23-quiet-waiting-20261015-181041-296e6e8c`，manifest `be74363d548e84ad4655ea892715415d3053ec99d77b2c3e12fa94a527022fdf` |
| 独立只读分析（6 条） | `private/analysis/A23-quiet-first-live-host-20261016`，manifest `58d46003d944a9e7c35cff156c6640e50290ddc187d2a38899652724c5cdc4d2` |

run 名使用工作流原有 UTC 时间，实际开始为客户端 **10-16 02:10:41 +08:00**，不能
因目录的 10-15 字样混入前一天证据。原始 run/工作流结果保持，不回写成功标记。
单独核验了当前/冻结构建和消费回执一致性；原通用分析保留其 source-closure/
device-evidence 未认证字段，不因局部匹配而提升整链结论。

## 下一步是设备材料回收

已经提示用户用现有方法完全关机，确认断电后再取 SD 插入 Mac。本步骤属于受控恢复，
不是以固定倒数、主机退出或日志缺失证明设备正常保存/退出。诊断分支本就可能保存
后继续保留；完整 EXE3 自身也不能认证自己的最终 commit。

下一次读卡优先保留同 nonce 的 `.execution.bin` 和 `.capture.bin` / `.diagnostic.bin`、
日志及错误报告的原字节，包括部分文件；核对本次部署四文件，使用 quiet 运行 recipe
`ae65e703…` 解码，连同本次 run、消费记录/回执、进程与 SDK claim 建立独立收集。
不再发 USB 请求。根据实际 trace 区分 SETUP/准入/sequence/post/ACK 及后续失败，
本次 ISO 零长度和设备 URB 状态也应保留，不能只关注旧控制超时方向。

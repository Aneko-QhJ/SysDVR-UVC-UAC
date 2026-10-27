# Q1 首次实测与只读回收结果（2026-10-26）

本次 672 来源候选的单次 Q1 实测完成：465/481/497 三轮各 3072 个正确字节，共 9216；主机服务窗口和终结事实通过，独立消费者复算一致，设备 trace、STATUS、序号和 URB 唯一对应，关联生命周期正常返回。465..512 整段已耗尽，不重试、不补轮。

SD 已只读回收并安全弹出，138 件原始材料封存，设备日志不再待回收。本次支持新增有界历史合同；持续流、SDK drain、缓冲复用、未来无事件和旧错误根因仍未证明。

## 人类授权与唯一运行

用户先明确回复“授权本次 Q1 单次实测”，随后在本次启动前回复“三项均已就绪，保持关机”。据此记录新人工回执并执行已审查 [r1 启动计划](A23_LIVE132_Q1_LAUNCH_PLAN.md) 一次。启动前绑定 672 来源、132 件归档、49..464 历史及新范围；整段消费在原生接收器启动前完成。

- job：`15ae75b2-2833-49ad-a320-44366bf02c0d`。
- run：`private/runs/A-q1-three-epoch-15ae75b2-2833-49ad-a320-44366bf02c0d`。
- receiver PID81355；前台直接创建者 exec session17544，原生及外层 exit0，创建者已直接 wait。
- 观察原生 stdout 实际 `WAITING` 后才提示 CFW emuMMC 默认项开机；用户回复“已进入 CFW／HOME”。不补造入口或启动来源认证。
- 主机结束后，用户明确回复“继续读卡，已完全关机并将卡插入 Mac”。未启动第二个接收器、切换入口补试或写卡。

实际回执为 `private/analysis/A23-live132-q1-once-20261026-r1.json`。候选 build 仍是软件准备 r4，build manifest `dc0373e727426069db1bf7d084da69a38b11c7a8207f56b5bf2be126dc2c7035`，来源和二进制未改动。

## 主机与新增末轮合同

新消费者在采集器内验收、launcher 独立复算，读卡后再次以 `simulation=false` 从封存主机原件验收，三个结果逐项相同。正式 job、非模拟 native claim、直接 child PID/context 和消费记录一致。

| 项目 | 本次结果 |
| --- | --- |
| 三轮 | 首序号 465/481/497；URB387/403/419；共 9216 正确字节 |
| 原始材料 | 每轮 24576 字节 raw、128 项 transaction；六份完整 STATUS |
| 回调与停止 | ISO/control 回调各 [1,1,1]；abort0；interest 为空前缀、无 pending/overflow |
| 轮间交还 | worker 返回 / job 复核 / 恢复 poll 各 2；verifier 回到串行队列 |
| 末轮 worker | 返回、复核、完整检查各 1；耗时 295.506ms；无 busy 残留 |
| 服务窗口 | 253 个记录点；250.843375ms；最大间隔 1.186500ms，满足固定 250ms / 32ms / 512 点合同 |
| 窗口后检查 | `terminal_final` 完整检查 315.306292ms，随后继续原 finalize 与双边导出检查 |
| 终结事实 | 一次 owner queue 续接；采样 4.418666ms；健康/快照/磁盘绑定一致，accepted=true |
| 退出门 | completion pending=false、accepted=true；无退出请求、强退或人工关机 ack |

253 个记录点不是 SDK 回调次数。消费者的 `actual_sdk_poll_verified` 和生产者历史认证仍为 false；验收重算的是已提供、与本次来源和 job 绑定的记录。采样之后或其他队列的事件没有被排除，不能把本次历史通过作为实时健康或排空证明。

服务窗口只覆盖首末服务点之间的区间，不覆盖之后的 315ms 完整检查及导出收尾。

| 时间（ms） | 第一轮 | 第二轮 | 第三轮 |
| --- | ---: | ---: | ---: |
| ISO 提交至回调 | 47.383 | 47.220 | 47.391 |
| BURST 至 control 回调 | 2.978 | 0.363 | 3.187 |
| BURST 至保存 | 51.616 | 50.473 | 51.272 |
| 保存至下一轮 before 意图 | 297.234 | 296.539 | — |

未做随机化性能对照；轮间耗时未消失，不宣布提速。

## 设备链与只读回收

回收前核对外置物理 disk4 / disk4s1、FAT32、卷 UUID `37614F76-3E12-3470-B5C8-52B5A449C213`；工具将其重挂为只读，复制前后核对身份与内容，电脑副本逐字节回读后安全弹出。回收脚本 16 个磁盘命令均 exit0 并由创建者 wait；原失败 volume owner 保留，未重试修复。

设备 execution `ep0-4ac0b6761b94134db02a313ef8c57178739b549c5b198cf97dbfc85342eabe33.execution.bin` 为唯一新增匹配：9 组 before/BURST/after setup、六个 STATUS、三组序号、三次 3072 字节 ISO post 与 URB 均对应。216 条 trace，无 dropped/invalid；外部 primary 与 execution 嵌入内容逐字节相同。

关联生命周期 `ep0-life-bb9c3ea8d3c74281e7705e15b404ce5c.bin` 唯一且新增，27 条记录，末条 `main_return/result0`，正常结束窗口 30.000326 秒、stop reason `expired`。主机和设备时钟没有绝对校准，不将设备窗口与主机窗口直接拼接。

相对 132 件基线，新增 6 件；旧 131 件非 logfile 内容不变，仅 `logfile.txt` 改写，无删除或新增 ERPT，9 份旧 ERPT 保持。四项部署匹配，配置、缺失项与 boot2 flag 清单保持。

另一个新增零 trace execution 与自己的 27 条生命周期对应，30.205337 秒正常返回；没有序号或 ISO URB，具体启动/入口归属未知，不分配给本次三轮。旧两个 recipe 不匹配生命周期原件保留，不用于本次关联。

## 封存与后续边界

| 证据 | SHA256SUMS 摘要 |
| --- | --- |
| 原始 run | `9f0b5ad5cf94f8cb6a99d42680176086d7bcd1a56956819e55259737c50b0271` |
| 独立主机分析 | `c18b19559c7f30f64415fd28e9d70f61a4691c61bcda979d60f1f9c432c7f3f6` |
| 设备关联分析 | `b878e4b56e4745edb71dcc2b0759ba82e41a7c1a0f88aeee3c4e92acc9055a79` |
| 只读回收 | `378969174bde55648ed24c0b656b9c25aa9c1d54c7757a04d5bad951493f9744` |
| 138 件快照 | `67ec828848131eea44d864ea5d5cd5282ec52a0d98e1304e087b186fe22e530f` |
| 补充上下文分析 | `ae9de2b7d0f4284e1d0958aa787dfe014abb127097bdc7a387bc6c9ea5283688` |

最终交接位于 `private/analysis/A23-live132-q1-first-recovered-closeout-20261026`。旧 actual417 与九个旧 namespace 保持；新 namespace465 的 17 件文件及整段消费记录留证。

138 件快照成为最新回收基线后，原 132 件候选只能归档验证；当前 freshness 检查按 `current132 required` 拒绝，不能重启原 launcher。`remaining=0`、`acquisition_enabled=false`，现场不推定仍就绪。

Q1 本次有界证据问题已回答。下一项先离线建立 Q2 的资源所有权、完成/取消交还、generation 复用、背压、停止恢复及证据容量合同；不能直接加第四轮，也不因 Q1 通过而获得新的实测许可。

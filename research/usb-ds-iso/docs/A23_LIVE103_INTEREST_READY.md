# 当前103件基线的interest诊断候选（2026-10-24）

消息留证已接入新的固定三轮入口并编译封存。最终版本绑定当前103件原件、632来源、49..224完整消费历史及81/113/145/177四个旧namespace，只允许新范围225..272。27个原生注入场景与9项专项检查通过，沙箱外只读环境核对通过；没有新授权、正式namespace、actual record或范围保留，没有启动USB/SD实测。

本候选用于区分“实际是哪类interest、何时进入provider”，仍将任何interest视为资源故障，不预先忽略消息。它没有修复或解释上次177..224失败，也没有延长设备30秒窗口。

新增4来源，总632，旧628保持：`tools/build_a23_live103_interest.py`、`tools/a23_live103_interest_workflow.py`、`tools/audit_a23_live103_interest.py`、`tests/test_a23_live103_interest.py`。

## 绑定范围与留证路径

基线为`private/card-cycles/20261024-live97-three-first-read`，103原件及只读回收/弹出回执重新核验，四项部署与原device binding/recipe一致。新历史继承177..224整段，包括上次未提交的209..224；不将未提交序号恢复为可用次数。新的shared48 scope、原生许可、SDK provider/driver、entry及独立分析器均绑定225..272，拒绝旧177 scope及32宽度/计数许可。

provider保持先置故障标志，再将原始uint32消息与provider入口mach tick写入固定8条缓冲，最后派发原异步pin。原始零值、未知值都不改成termination；pending、故障先于槽、overflow仍明确报告。原SDK messageArgument及发送方尚未采集，消息标签不认证物理来源。

正常三轮必须仍通过完整SDK/STATUS/ISO7/entry链、checked export双边复核和接受回执；新收集器还要求interest记录为空、无故障、无pending/overflow。模型正常路径为225..240、241..256、257..272，共9216正确字节；它是注入结果，不是真实SDK或设备成功。

首次失败快照保留当时的lease记录。用户明确确认完全关机后，controller另存`interest-after-power-off`，记录新的entry/driver元数据和观察边界；独立失败收集器要求此前已提交行逐字保持，允许后续追加或pending提交，不允许旧行被覆盖、count回退或清除既有overflow。补充记录保存冲突会明确报告失败，不能认证为完整诊断。

本次收尾另外补齐准备期分支：若interest在SDK open/准备阶段到达，driver尚未建立，entry现在保存`provider_failure`，收集器区分`provider_preparation`与`driver`阶段。注入的准备期通知99在零ISO情况下仍能从首次失败及关机确认后的副本读回。准备期记录保留原始mach tick，本次不从无driver的记录计算时间间隔。

关机确认后的记录仍不是SDK排空或最后事件证明；不复制活跃SDK缓冲区、不destroy或reset设备，也不从磁盘PID恢复控制权。原创建者继续持有实际child并直接wait。消息prefix可关联，但最后检查后的新事件仍可能未纳入，`future_events_excluded=false`保持。

## 验证结果

| 场景 | 结果 |
| --- | --- |
| 正常/排队延迟 | 三轮9216字节及双边接受回执通过，记录为空；模拟时钟不能按真实时钟接受 |
| termination、请求关闭、配置、未知、零值 | 均在第三轮前停止，首次及补充证据保留原值 |
| SDK准备期interest | 无driver、零ISO；provider保留的原值99及补充记录均通过独立解析 |
| 10个通知 | 最多8条、显式overflow，保持停止；不称消息流完整 |
| 补充保存冲突 | attempted=true/saved=false；要求补充证据的收集器拒绝 |
| 重新封存后改写补充副本旧行 | 首次/补充prefix比较拒绝 |
| spent177改写、增加、缺失或来源/基线变化 | 提交前拒绝；两轮间来源变化不提交第三轮 |
| 旧scope、32范围/计数、坏封存源码/历史/生成物/binary | 对应原生门禁拒绝，坏归档及许可未打开SDK |
| 重复consume、其他job接管、缺授权issue | 拒绝，不改变已经烧段的模型namespace |
| 接受回执后再改载荷 | controller已有历史成功，独立收集器仍拒绝 |
| trace字段 | boolean计数拒绝；未知uint32原值保留；不完整prefix只能用于诊断，不能作为成功 |

最终27个fixture均exit0，由创建者直接wait；ASan/UBSan stderr为空，9项专项检查通过。原生CLI只执行describe、归档/当前文件校验和不存在job的拒绝。未执行真实SDK调用，实际IOUSBHost对象/USB/SD操作为0。

r1的26场景/8检查及环境核对在中断前已通过，恢复时复核已有结果，没有为恢复而重跑；之后因发现准备期消息导出缺口而形成r2。r2增加该分支并完成27场景/9检查。两版共4编译作业、53个fixture进程均由创建者wait；8个原生文件检查按0/2预期退出。r1材料保留，正式选择r2，其构建与来源摘要不同，旧r1不再作为当前候选。

## 环境与一次启动计划

r2的沙箱外只读`--inspect-context`通过：arm64、OS26A434及指定IOUSBHost框架UUID匹配，sandbox查询0。原始stdout/stderr已封存。这不证明USB打开权限或采集成功，正式启动仍会重新核对当前上下文。

一次计划为`private/analysis/A23-live103-interest-launch-plan-20261024-r2`，固定r2 build/receiver摘要。无参数仅显示计划；缺授权execute返回2，未创建actual record或namespace。授权文件、actual record、`sequence-reservations48-225`目前均不存在，remaining0。

若进行实测，需新的明确授权：一次最多三轮225..272、失败即停、不补次，并确认本次完全关机、SD装回、USB已连接。接收器实际WAITING后才提示开机CFW。未决资源按原保留/关机确认/正常失败退出/创建者wait流程处理；测试后另行只读回收设备日志。当前SD最后记录为已弹出，现场状态未确认，不自动启动。

设备trace/owner仍是256/32，三轮同形预算及30秒窗口边界沿用已审查方案；额外请求、实际时间和日志容量仍可能改变结果。新原生消息、参数、发送方、真实SDK节奏、第三轮能力、跨时钟、quiet drain与旧故障根因均未新增实机结论。

## 封存索引

以下相对`private/analysis`，摘要为SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| `A23-live103-interest-review-20261024-r2` | `0542650ed7298be8c5cea9c185ba604efeabc962e1415a0a89604b31ba2258a0` |
| `A23-live103-interest-validation-20261024-r2` | `2758248b569dd6d896edf19759c71f52fc275673a06016ff9df4efbc0fdb1d2b` |
| `A23-live103-interest-context-20261024-r2` | `764b42dfd49f5ee55a7da1416a42ca3bd6c67874d922823f7f780ddd49f6d6db` |
| `A23-live103-interest-launch-plan-20261024-r2` | `a5fac9571719169fa1821ee15a80ba5cc6172214b2e86331ff5e10d47ed98464` |

r1历史、632来源、25旧保护项、四个旧namespace、actual177、票据及交接文档副本在`A23-live103-interest-closeout-20261024`。上次实测失败保持不变，见[177..224结果](A23_LIVE97_THREE_FIRST_RESULT.md)。

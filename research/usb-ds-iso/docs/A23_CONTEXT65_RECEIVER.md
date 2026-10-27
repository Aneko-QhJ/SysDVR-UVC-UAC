# 序号65与执行环境证据候选（2026-10-17，Asia/Shanghai）

2026-10-18续接：[独立一次流程与最新基线](A23_CONTEXT65_READINESS.md)已完成离线验证；下方“尚未绑定工作流”为2026-10-17历史状态。当前基线仍缺boot2.flag，65..80未正式保留或发行。

已构建新的第8代离线接收器，将起始序号65和执行环境检查绑定到独立计划、回执及判读器。**65..80仅为经本地历史审核的候选，尚未正式保留、发行或实测。** 设备包、lead32窗口和全部时间预算保持。

本轮接收器仅运行describe、check-build及execution-context等无设备访问模式；协调器、等待和领取权限场景全部使用注入模型。没有调用真实采集入口、创建真实SDK设备对象、访问USB/SD或修复启动标记。

## 历史范围与版本绑定

新历史范围包含378份文件：原A-A23范围364份、序号49失败run的12份文件、block-00049.json及其已消费正式记录。所有JSON解析和已有ISO1载荷扫描通过，观察值0..31及49；正式49..64保留完整。按已有保守隔离政策，下一可用候选为65..80。

范围包括A-A23-*、A-sequence-waiting-*和未来A-context*-waiting-*；不声称覆盖未保存或范围外的历史，也不提供物理来源认证。构建及验证重新核对了当前run清单、保留文件和关联记录，没有只依赖旧364文件快照。

新范围位于private/analysis/A23-context65-history-20261017，379文件；摘要fc5d580c4411f0718a6c22fc4d8097f328fbb3b9dcaa5f99a89e316e749255cf。新schema为：

| 材料 | 新绑定 |
| --- | --- |
| build / record / description / consumed receipt | 第8代 |
| waiting plan / SDK plan | 第4版 |
| 起始序号 | 65，16包至80 |
| process claim | 第2版，增加execution_context_sha256 |
| 主机配置 | host-sequence65-context-1 |

实际BURST请求的wValue、控制日志、STATUS、原始载荷与EXE3比较均绑定65。旧49及lead32判读器拒绝新计划，新收集器也拒绝旧49模型和两份序号1成功原件。原始五份初始化源码及设备材料继续复用；独立生成新源码和接收器，不编辑旧49绑定、签发工具或已消费记录。

## 进程环境的只读观察与入口顺序

新增[a23_execution_context.m](../host/a23_execution_context.m)保存UID/EUID、GID/EGID、PID/PPID、系统版本和build、机器类型、执行文件路径及SHA256、已加载IOUSBHost UUID、自身沙箱查询的原始返回值和errno，以及采样前后Mach ticks。它不枚举注册表、打开用户客户端、发送USB请求或改变权限。

当前候选要求OS build26A434、framework UUID B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B，以及sandbox_check(self,NULL,0)返回0。查询不可用、负值、返回1、布尔值代替数值、错误码非零及身份不符均拒绝；系统更新后应重新审查绑定。

该私有查询的空操作用法参考Chromium官方实现；没有把它当作Apple公开的USB权限契约。当前机器的两种执行方式另有实际只读对照。[Chromium Seatbelt实现](https://github.com/chromium/chromium/blob/main/sandbox/mac/seatbelt.cc)

| 同一候选的自检方式 | 查询返回 | UID/EUID | 系统、framework、接收器SHA |
| --- | ---: | --- | --- |
| 默认沙箱 | 1 | 501/501 | 相同 |
| 明确沙箱外执行，仅自检 | 0 | 501/501 | 相同 |

两份原始JSON均保留，query_available为真正布尔值。返回0只满足本候选的自身沙箱前提，**不证明IOServiceOpen会成功，也不证明上次失败由沙箱导致**。外部启动模式和原始查询值应同时保存，不能用自填环境变量冒充实际观察。

真实入口的顺序为：文件与已消费回执核验→读取并排他保存execution-context.json→检查环境条件→排他process claim→创建通知端口及开始被动等待。上下文拒绝发生在领取process claim与任何IOKit等待之前；未来一次工作流若已消费次数，也不得因该拒绝补次。

process claim记录原上下文文件摘要，SDK领取权限时重新核对该文件及摘要；更换PID等字段也会失败。此观察采于WAITING之前，没有声称在整个等待期持续监控所有权限变化。收集器另外要求采样结束不晚于wait.begin。文件比较仅说明所供材料自洽，不认证真实进程、操作系统权限或物理同次会话。

新增--execution-context模式只输出观察；即使查询返回1也可能正常退出0，**该模式的退出码不是采集许可**。本轮没有运行--acquire-once。

## 模型与判读验证

最终以receiver-review-r3和receiver-validation-r2为准：

- 12个注入等待场景、34个SDK协调器场景和11个预算边界断言保持；native模型使用ASan/UBSan。
- 9个回执/领取权限场景，以及9个上下文门禁场景，包括缺件、沙箱活跃/未知、数值被布尔替代、系统/代码身份不符和领取process claim后篡改。
- 原生上下文模型检查1个有效模板、13种故障、20个逐字段缺失，并用实际自检结果归一化沙箱值后验证序列化类型。另补原生重复JSON字段拒绝。
- 6个初始收集场景与10个补充静态收集场景通过预期判读；部分或缺失上下文、时间顺序错误、旧49原件、缺执行材料及多LCP1均保留失败或歧义。移动后的正向集合仍可独立重分析。
- 8个新专项测试及10个旧序号测试通过，共18项。272既有来源哈希保持，新增15项后287来源；设备生产源、旧票据、正式49记录及保留文件保持。

旧sequence工作流38项另作原样回归：37项通过，1项失败。具体为test_preview_does_not_create_formal_ledger_or_record仍断言sequence_reserved=false；当前49已经永久保留，因此返回true。目录是否新增和目标是否写入的检查本身通过。没有编辑该冻结测试或声称原套件全过。

补充的当前状态检查确认：预览报告sequence_reserved=true、issuance_available=false，未写目标记录，正式保留目录文件清单和全部字节前后相同。完整原始失败日志、精确断言及这项补查均随validation封存。

初版r1在严格编译的缩进检查停止；r2构建和注入模型完成后，实际自检暴露query_available被序列化为整数1。r3修正为BOOL，并补实际观察的类型检查；前两版保留，不能用其旧通过字段替代最终验证。validation-r1在旧测试尚未结束时停止于结果检查，所有静态收集原件保留；r2等待原始结果完成后显式登记上述历史状态断言失败。

## 材料与下一步

| private/analysis下的材料 | 条目/用途 | SHA256SUMS摘要 |
| --- | --- | --- |
| A23-context65-receiver-review-20261017-r3 | 构建、46个native模型、领取权限、序列化及初始收集 | fcb3cf50b2fe770c22f707ac9ebdf8195d73b01817dae0a4772539f3428ef7ce |
| A23-context65-receiver-validation-20261017-r2 | 355文件、补充收集、自检对照和原始测试结果 | 85c8a73fa7ed36077682144f6b05ebd6cd6d5d915bffecae33f5cccc6d2338b1 |

独立工具为build_a23_context65_receiver.py、analyze_*context65*及collect_a23_context65_*。正式一次工作流、动态最新读卡基线和恢复/弹出入口**尚未绑定第8代材料**；旧49签发器不接受本候选，不能直接复用或修改旧次数。

下一项离线工作是准备独立一次预览、发行和恢复流程：正式发行前重新核对历史，先持久保留新块，再排他创建新记录；记录实际执行方式与新上下文证据，失败不补次。当前没有创建65的正式保留文件或一次记录。

现场前提仍是15:49快照缺boot2.flag、部署核验失败。新流程必须使用独立处理标记后取得的真实四文件基线及弹出回执，不能回退到13:41旧成功快照来宣称最新部署匹配。本轮未修复或写卡，未来现场修复和新实测另待明确指令。

恢复入口为private/analysis/A23-context65-pending.json；旧序号49记录仍failed_no_retry/remaining0，card_snapshot_saved=true、device_log_pending=false、recovered=false和recovery_receipt_accepted=false保持。根因、物理同次来源及持续流仍未认证。

# Q1：新末轮合同的真实入口软件准备（2026-10-26）

已完成[Q1问题卡](A23_EVIDENCE_CONCLUSIONS.md)的真实入口、工作流、独立消费者与失败回收软件接线。最终选r4：10个原生场景、13项模式/许可拒绝及8项坏失败材料语义拒绝通过。正常及较密服务点模型均验收9216正确字节。

本轮没有真实SDK采集、USB/SD访问、新授权、正式范围保留或实测记录。672来源候选已具备受一次性许可约束的采集软件路径；descriptor中的hardware_entry_enabled/formal_issuance_available/acquisition_mode_implemented=true表示路径已实现，不表示人类授权、执行上下文通过或设备已可打开。实际票据acquisition_enabled=false、remaining=0，正式465 namespace仍不存在。

新增4来源：tools/build_a23_live132_q1.py、tools/a23_live132_q1_workflow.py、tools/a23_live132_q1_consumer.py和tools/audit_a23_live132_q1.py，总672；旧668字节保持。新build绑定当前132件归档、完整49..464消耗历史和九个旧namespace。旧666离线候选、668视图及651来源真实运行均保持，不互相回填结论。

## 实际入口与生命周期

新native main从已封存651真实入口派生，范围改为未发行的465..512，run前缀独立为A-q1-three-epoch-。完整保留build/source/最新归档复核、实际进程上下文、正式已消费job、native process/selection claim、实际IOKit等待和SDK资源路径。

入口在begin前配置completion queue，并使用组合退出门同时等待轮间worker、末轮worker和completion pending结束。信号和operator-off仍按旧的一次性保留合同处理。最终输出明确success_scope=historical_completion_sample、current_device_state=unverified，不把loop success显示成实时健康。

专用外层workflow只加载与新builder匹配的冻结generated workflow，旧builder/scope拒绝。正式issue要求新的显式授权；capture要求明确require_escalated执行模式、正式job路径和fresh scope/context。消费整段范围发生在Popen之前，创建者在前台主线程直接wait；不后台丢弃、不重试。真实WAITING之后才可通知用户启动的流程要求保持，但本轮从未进入等待分支。

无授权issue拒绝；无执行模式capture拒绝；native --acquire-once传入不存在的job/run返回2，未打开SDK。preview只做文件检查，明确remaining=0、未创建记录/范围。没有调用authorized=True、capture、实际collect或operator-off确认。

## 模型与SDK材料不能互相替换

Q1候选可执行两类提供材料的解析，但调用者必须显式传真正boolean模式。原验收规则不放宽：

- native在verifier归还前固定保存q1_mode_model，busy失败边界也能输出该稳定值，不读取worker独占的可变verifier。
- 服务记录binding的model_only与请求模式一致；scope、job、session、source及132件基线摘要一致。独立服务消费者仍重算所有点、间隔、计数和终态。
- export cadence的sdk_clock_is_synthetic、verifier.model_roots及前后q1_mode_model均须同模式。
- 原SDK消费者保留injected_fixture标签全有/全无的一致性检查；Q1额外要求模型来源为injected_sdk_model，SDK模式为unverified_sdk_observation。
- completion事实仍精确绑定payload/接受回执/entry/final摘要，并保留historical_cut_only和所有未证明项。

SDK模式只是提供材料的路径分类，名字unverified_sdk_observation不能解释为物理来源已认证。本轮只有模型正向材料；SDK模式正向链仍待新实测，不能用修改一个model_only或simulation字段替代。正常、较密模型按SDK模式验收均拒绝，失败模型按SDK模式回收也拒绝。

真实成功collector要求创建者exit0/wait、正式已消费job、直接子PID与native context一致、process/selection claims均simulation=false，并绑定原生与host选择身份。提供材料还必须通过新终结/服务合同和原SDK/entry/export全部验收；不能复用旧collector而漏掉终结事实。

## 失败材料

新增非零退出回收路径。它要求实际parent wait和正式消耗链，随后对提供的失败材料做独立检查：

- SDK准备期provider失败、末轮worker失败、completion取消/失败或写入碰撞分别保留，不把较早成功payload当作整个运行成功。
- mode、candidate、序号和job绑定必须匹配；若末轮worker已启动，最终返回记录必须归还verifier、busy=false。
- accepted=false的completion事实必须完整绑定原payload清单、接受清单、接受回执与entry/final摘要，不只检查candidate或entry。
- operator-off补充材料中的停止状态、边界与原始interest行前缀必须一致，不能删除或改写原消息；确认来自人类陈述，device_power_observed_by_software仍false。
- 若native在host产生前拒绝，或导出残缺/损坏而无法完整语义验收，保留raw_failure与明确错误，不声称完整失败链、SDK已打开或资源已释放；仍不重试。

本轮5种模型失败独立回收通过。另对临时副本重新计算SHA256SUMS/COMMITTED后，检查改写原interest前缀、虚称软件观察到关机、缺少off材料、mode错误、payload/接受回执摘要错误、把拒绝fact改为接受以及伪造worker返回，共8项均因语义拒绝。原封存材料未改写。

## 较密服务点暴露的16KB缺口

r1的较密场景记录260点，终态文件18247字节；本地窗口已经passed，但driver沿用通用frozenJSON的16384字节上限，终态复制失败，entry出现terminal_completion_failed。本轮没有把这个失败当作USB故障或旧零包超时根因。

新Q1只为终态证据增加独立编码路径：samples须2..512、sample_count相等、events数量为samples+8，JSON最多262144字节；其他通用identity/status等frozenJSON仍保留16KB上限。终态编码失败有明确terminal_evidence_encoding原因。entry消费者相应的driver/entry快照读取上限有界提升，所有协议/计数/摘要校验保留。

同一18247字节失败原件在原生fixture中确定性回放：旧通用编码拒绝，新终态编码接受，错误样本计数拒绝。最终r4较密模型257点、result.json为19549字节，完整SDK/entry/export/服务/终结验收通过；普通模型186点、result.json为14999字节。它们不证明实际SDK调度或512点所有交错已实机覆盖。

## 最终检查与开发版本

| r4原生场景 | 结果 |
| --- | --- |
| normal / dense-window | 两个模型正向链各9216正确字节，新旧全部消费者通过；按SDK模式接受均拒绝 |
| terminal-stop | worker忙时停止，等待归还并保留失败材料 |
| pending-exit | completion pending时模型关机确认不越过退出门，写拒绝事实 |
| payload-queued | 接受前排队入口在终结采样中拒绝，失败fact与原回执完整绑定 |
| interest-open | SDK准备期interest失败，provider及off补充原始前缀保留 |
| completion-collision | 终结目录碰撞，不补次，较早payload不升级成功 |
| new-source-pre / spent417-pre / old666-scope | 新来源变化、旧消耗记录变化、旧离线scope在SDK打开前拒绝 |

13项额外拒绝覆盖无授权、无执行模式、旧builder、正常/较密/五类失败按真实模式冒充、整数mode、单改服务model标记及临时claims冒充真实失败回收。8项重新封存坏副本的拒绝另计，没有放宽checksum来做反例。

r1/r2/r3/r4均保留。r1暴露上述16KB编码缺口；r2修补编码后正常/较密及两类退出通过，但payload-queued未注入事件，fixture仍期待失败而断言退出。r3修正fixture配置，10场景/13拒绝通过；r4加强拒绝completion事实的完整摘要绑定，再完成10/13及额外8项语义检查。r2到r3没有用阈值放宽或硬件重试解决问题。

四版合计8个编译作业、27个原生fixture（含两个开发断言失败进程）、16个显式文件模式及4个preview内部文件检查，均创建者直接wait。较密/排队问题原件和各版本来源保持。正式新namespace、授权、范围、实测actual记录、真实SDK对象及USB/SD访问均0。

## 仍未就绪的执行层

软件接线验证不等于一次性计划已经审查。目前没有Q1 launcher/plan、新人工回执、新actual槽占用、当前沙箱外进程上下文或USB打开权限证明。模型故障交错和结构校验也不替代真实SDK正向链。

下一项仅离线准备一次性计划，审查launcher→外层workflow→generated workflow→native scope与新consumer绑定，并按需只读检查自身执行上下文；不签发或消费465..512、不启动接收器、不写卡。实际执行仍须单独收到新授权及当前完全关机/装卡/USB就绪确认，唯一接收器实际WAITING后再提示启动，任意失败即停不补次。

最后采样后的事件、SDK drain、复用、持续流、生产者/物理来源认证和旧故障根因仍未证明。最后真实运行仍为651来源417..464；132件归档已回收，日志pending=false，SD最后已弹出，当前现场未刷新。

## 封存

| 材料（相对private/analysis） | SHA256SUMS摘要 |
| --- | --- |
| A23-live132-q1-review-20261026-r1 | ab2ae2e3c9a51f17ab8b43650c9b0d8b270a584e9ec4621f06fee86451d54670 |
| A23-live132-q1-review-20261026-r2 | d0b0a54e8e4189ef29dabd0f5fb85b21ec00eef1564dc14b675cb86f49d973cd |
| A23-live132-q1-review-20261026-r3 | 3a1cfa238ff91979d0cfa11609d2a8aca57142b9b59de1aa61c37a7fa8efe3ae |
| A23-live132-q1-review-20261026-r4 | 7da7834b923b672b9da8588e4b5a929c54c517015f2b7df5126be27ea253427c |
| A23-live132-q1-failure-validation-20261026 | 8725e54319f355d6da5e206d0598a3103c15fef2adb7e44e71874d0274069671 |

最终672来源、未改actual417、九namespace、票据与交接见private/analysis/A23-live132-q1-preparation-closeout-20261026。实际采集仍未开启，acquisition_enabled=false、remaining=0。

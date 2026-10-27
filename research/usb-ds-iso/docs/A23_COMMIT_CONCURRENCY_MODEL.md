# A23 提交期间并发发布与缓存诊断关联（2026-10-20）

后续：[独立worker失败与材料完整性](A23_WORKER_FAILURE_MODEL.md)补13种独立C安排及纯字节拒绝规则；483来源、60测试与搬移重编译通过，本阶段故障尚未接入完整driver。以下保留原阶段。

接续[版本快照主机隔离模型](A23_VERSIONED_DRIVER_MODEL.md)，本阶段保持driver、桥和纯C候选逐字节相同，新增13种指定pthread交错并重放原59场景。72场景在优化、UBSan和479来源搬移重建中一致；新增20、旧driver21及旧C20项，共61测试无跳过通过。

## 指定线程交错

每种新安排先让worker在条件变量屏障前就绪，再由持票据的串行driver队列释放屏障并join。线程只尝试注入profile发布或调用既有mock callback；callback的观察处理异步排回driver队列，worker不等待该队列。两个发布者均就绪后才放行，但不声明其实际CPU执行顺序。

| 指定安排 | 观察 |
| --- | --- |
| 持票据期间单次发布、ABA发布尝试、no-op发布 | 均Busy；版本在worker前后保持3，提交后释放为4 |
| 两名就绪发布者 | 两者Busy，成功写入0，driver正常完成 |
| 旧ISO/control callback在发布前或发布后到达 | 4种顺序均使完成资格撤销；发布仍Busy，原票据释放 |
| 线程发布尝试之后journal拒绝append | 不保存observation_complete，不settled，票据释放 |
| 结束Capture返回前的线程ABA | worker将版本2变6，提交拿票据时发现不匹配，拒绝；失败票据Abort后为8 |
| 释放后、receipt之前的线程ABA | guard终止，随后保存失败状态receipt；不是已保存receipt的stale |
| receipt之后的线程ABA或no-op | 版本4变8或6，guard撤销完成，原receipt变stale/saved=false |

13种安排每个有效fixture创建14个worker，其中两发布者场景创建2个。原位置与搬移共4份模型、12个compiler jobs、4次有效模型进程、4次无参数拒绝、56个worker线程。均首轮通过，未运行TSan或覆盖所有线程交错；`specified_schedules_cover_all_interleavings=false`。

## 完整诊断字段与receipt链

新增 `a23_concurrent_diagnostics.py` 消费已提供的case字节缓存。外层场景核验器先检查driver行为，消费者再对全部72场景关联17个version字段、18个facts字段及两个owner各4项声明，包括构造/起止/释放/当前版本、成功/Busy计数、profile比例、变更次数、read/submission计数和ack/timeout状态。

消费者核对prepared与quiet端点、原始payload/STATUS、epoch metadata注入标签及bundle摘要，并区分失败receipt与保存后失效receipt。后者必须保留原complete快照，当前状态已停止且出现版本故障，两个快照同属一session。它检查内部声明关系，不认证状态来源或任意真实硬件运行。

测试将变更同步写回row和缓存sidecar，以排除只靠副本不一致拒绝：17种version字段、18种facts字段、4种owner字段、1种worker trace及1种重算receipt封存，共41次内存坏件尝试均被拒绝。将stale snapshot换为当前失败状态并重算receipt SHA/manifest/COMMITTED，也不能通过。

消费者函数本身只访问字节map；测试同时拦截builtins.open与io.open，观察打开0。外层封存校验和cache收集仍读取指定review文件。任何字段、worker就绪数量、对象绑定、SDK-shaped标签都不认证真实clock或设备来源，`diagnostic_provenance_authenticated=false`。

## 隔离与封存

新renderer只更换生成的model_main.m，注入线程helper；其他生成文件及driver diff与父review相同。原非参与写入ABA负对照仍通过，所有profile写入方遵守契约的前提保持。

每版执行前检查otool/nm，继续只链接Foundation及系统运行库。真实SDK factory、Mach clock、实际context、生产broker/receiver和Switch固件均未构建或执行。搬移回放的Python审计钩子记录原checkout与/Volumes打开0；编译器和原生子进程不继承钩子，命令使用搬移来源。三种只读CLI返回0/2/2，不执行原生程序。这不是OS能力隔离证明。

review：`private/analysis/A23-commit-concurrency-model-review-20261020-r1`，3188成员，摘要 `7b55c6051c56d1ee9c1979bb4ae77bde50682e21b72ea1bc3335facaa8e23cb4`。

验证：`private/analysis/A23-commit-concurrency-model-validation-20261020-r1`。收口：`private/analysis/A23-commit-concurrency-model-closeout-20261020`。

原474来源、23保护项、真实49/65、账本和失败修复owner保持；只新增5份fixture/renderer/字节消费者/audit/测试来源。65已回收、remaining0，81..112未正式保留或发行。本轮USB/SD/真实SDK对象/实际context刷新/设备包改动均0，生产采集关闭。

下一步继续离线补worker异常、未完成写入、票据耗尽及对象替换等失败安排，明确收集器如何接收或拒绝不完整并发材料。现场时钟来源、owner/driver域映射、真实SDK runtime、quiet/drain与生产permit仍未认证。

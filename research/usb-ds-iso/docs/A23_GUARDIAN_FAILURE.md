# A23 guardian 自身中断与管道失效对照（2026-10-21）

后续：[状态管道显式失败候选](A23_STATUS_TRANSPORT.md)完成541来源、53安排及70测试。新增原始失败frame说明最早窗口也可能在request或ready发送时触发EPIPE；并非每次都到rejected/end。候选记录91不增加wait证据，原BrokenPipeError基线保持。以下保留原阶段。

本阶段把上一阶段“guardian保持存活”的前提变成可观察的失败场景。新增5个来源（固定guardian仪器、actor观察包装、纯消费者、审计与测试），总计537，原532来源逐字节保持。冻结requester、worker包装、内部fixture、guardian audit与发布IO没有改动；没有新SDK或原生执行。

外层witness直接Popen guardian并持有实际句柄。guardian继续直接拥有requester与worker。新仪器在固定检查点暂停guardian，witness趁actor仍存活注册macOS kqueue NOTE_EXIT后放行；到目标故障点时只通过实际Popen句柄SIGKILL guardian并wait。witness不保留requester/worker的控制或状态管道端，避免自己延长管道寿命；不向actor或journal PID发信号，不根据记录重建清理权。

actor观察包装先核对固定脚本摘要，在原进程中runpy执行冻结actor。它只在原actor返回或异常后独占写局部终态，保存job/nonce/failure-plan摘要、PID、退出码与异常类型，然后按该码退出；不创建、wait或signal其他进程。局部文件fsync不等于目录持久性或断电恢复。

33种安排：13种进程场景和20种缓存坏件，仅normal允许guardian_failure_model_complete。

| guardian场景 | actor观察结果 | 原guardian已wait数量 |
| --- | --- | --- |
| normal | requester/worker均0，内层报告与发布协议通过 | 2 |
| before-requester | 没有actor，保留guardian-use，拒绝重启 | 0 |
| after-requester | requester断管回报失败，退出1；没有worker | 0 |
| after-worker-unrecorded | 两actor已存在，owner尚未发布；均断管退出1 | 0 |
| owner-partial / owner-synced | owner半写或已同步仍保留；均断管退出1 | 0 |
| before-worker-release | worker尚未放行，guardian死亡关闭gate/status；均断管退出1 | 0 |
| child-payload.begin / receipt.partial / receipt.link / stdout.emit | 固定worker检查点中断guardian；保留部分或完整结果，均断管退出1 | 0 |
| after-worker-wait | worker已0并被wait；requester断管退出1 | 1 |
| after-requester-wait | 两actor已0并被wait，guardian尚未返回最终报告；任务仍拒绝 | 2 |

发现的具体路径：冻结worker在gate EOF之后尝试向已无读端的status pipe发送end，触发BrokenPipeError；冻结requester检测到command EOF后尝试发送rejected，也触发BrokenPipeError。观察包装记录异常并退出1，没有修复冻结actor的原失败路径，也不能把这些记录当作guardian收到的报告。完整receipt、stdout或此前已wait均不能替代已死亡guardian的最终结果。

两次回放共26个guardian、24个requester、22个worker，即72个真实Python进程。witness直接wait全部26个guardian（24次SIGKILL、2次0）；46个actor都有预注册NOTE_EXIT。witness对actor的waitpid均ECHILD，actor waits=0。其中10个actor在guardian死亡前已经由创建者完成wait（requester4、worker6）；另外36个只确认终止，回收没有认证。actor局部报告为10次0和36次1/BrokenPipeError。旧阶段14个孤儿回收状态也保持未认证，orphan_reaping_verified始终false。

新22项、guardian-owned回归22项、父中断回归20项，共64测试无跳过通过。纯消费者在open/io.open/waitpid阻断下分析缓存；只读verify在Popen阻断下完成。537来源搬移使用独立UUID/nonce/PID，33安排的确定性语义一致；正确/错误/缺pin的只读CLI返回0/2/2。witness只在真实运行查询进程，封存重验不查询进程。

20坏件覆盖guardian未wait、BOOL/信号返回码、actor信号声明、checkpoint pin/事件/BOOL guardian或actor PID/跨检查点PID变化、提前升级creator wait、未注册watch/缺NOTE_EXIT/错误ident、冒认witness wait/错误ECHILD、局部终态PID/nonce/pin/BOOL退出码和缺内层报告；保持外部plan pin后均拒绝。

26份guardian-use、22份attempt保持；重试/恢复各拒绝26次，证据字节不变；16份accept各一次。10对实际receipt/part核对同inode、nlink=2与相同字节，封存复制为独立普通文件。无额外单元进程，无actor/journal PID信号。

信任边界：

- 本轮证明固定检查点的guardian死亡会失去其直接wait能力，未实现通用OS supervisor、所有后代进程清理、任意指令崩溃或witness自身中断；外层witness仍假定存活。NOTE_EXIT仅确认终止，不能推断init/系统代为回收。
- 外部review/plan pin是调用方信任输入，不是签名。负对照只协调修改缓存outer和checkpoint的witness所报guardian PID，即可保持模型完成；它没有认证该PID与内层guardian观察的真实来源，相关来源/物理/生产授权标志始终false。
- Python源码摘要不是校验到exec/child读取的原子绑定；搬移审计hook只覆盖Python父回放，不继承到guardian/actor/CLI，不证明OS能力隔离。
- 使用历史SDK模型材料；没有真实SDK、clock/timebase、callback quiet drain或生产permit认证。单目录独占标记不证明全局nonce防重放、文件系统断电持久性或自动修复资格。
- 固定gate和小报告期限是离线仪器；同步文件IO无独立中断期限，生产collector/receiver/broker/permit均未接入。

证据：

- review：`private/analysis/A23-guardian-failure-review-20261021-r1`
- review SHA256SUMS：`58a5802c63de29baedb15746e6960d7465c3051abee02743f376208477742457`
- validation：`private/analysis/A23-guardian-failure-validation-20261021-r1`
- closeout：`private/analysis/A23-guardian-failure-closeout-20261021`

只读入口：`tools/audit_a23_guardian_failure.py --check <review> --expected-sha256 <review_pin>`。纯入口：`assess(failure_plan_bytes, plan_pin, job_byte_cache, witness_observation, guardian_checkpoints, actor_exit_notes)`。failure-plan/owned-plan/integrated-plan/launch摘要有不同含义，owned-plan仍提供同字节crash-plan兼容别名，沿用既有字节、路径、节点与普通文件封存限制。

23项保护文件、实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/permit claim均0，生产采集关闭。

下一步离线设计断管回报的显式失败路径，对比原始BrokenPipeError证据与候选本地终态；本地终态或NOTE_EXIT仍不能代替wait。不按journal PID清理，不自动重启、不接生产或硬件入口。

前序：[guardian直接拥有worker](A23_GUARDIAN_OWNED.md)。

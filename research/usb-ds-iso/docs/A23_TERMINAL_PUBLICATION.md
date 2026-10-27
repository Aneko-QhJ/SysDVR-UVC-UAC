# A23 局部终态发布中断对照（2026-10-21）

后续：[目录同步与最终commit候选](A23_TERMINAL_COMMIT.md)完成551来源、82安排及82测试。新协议记录先part/file fsync，再不可覆盖link和目录同步，最后发布commit；4次commit目录同步后仍中断，未认证actor回收不升级。旧基线保持。以下保留原阶段。

本阶段验证上一轮候选的三个局部文件可能缺失、为空、半写或已同步后仍中断。新增固定actor仪器、guardian仪器、纯消费者、审计与测试共5来源，总计546，原541来源字节保持。原状态候选、requester、worker、guardian audit与此前仪器、发布IO、生产collector/permit均未改。

新actor仪器沿用上一版write_status的相同AST，只把局部put拆成四个显式窗口：before（创建前）、created（独占打开后的空文件）、half（写入前半）、synced（写完并fsync文件）。它在选定角色的每个窗口通过独立事件管道记录job/nonce/plan/PID、文件名、目标摘要/长度及已写长度；仅before事件附目标字节。到目标窗口发送exit_requested=73后直接os._exit(73)。没有向actor PID发信号，也不根据journal恢复清理权。

新guardian仪器增加这根事件管道和外部terminal-plan pin传递，仍使用冻结guardian audit创建两actor。临时stage的两个固定文件名槽位分别映射到新actor和guardian仪器，failure-plan包含实际新字节摘要；冻结source目录保留原文件。witness只持有独立事件管道读端，不持有actor控制/状态管道端，避免延长原控制管道寿命。角色仍是guardian的直接子进程；witness不能wait它们。

50种安排：26个进程场景及24种缓存坏件。normal不杀guardian；guardian-loss在放行worker前杀guardian，但不额外中断局部发布；其余24种为requester/worker×原始frame/transport/exit×四窗口。所有故障都在冻结guardian的before-worker-release检查点后，通过真正断管触发局部报告，只有normal允许任务完成。

纯消费者独立核对guardian直接wait、固定checkpoint、NOTE_EXIT/ECHILD、事件次序和绑定，以及磁盘实际保留的精确前缀。事件里的目标字节用于检验意图与实际前缀，不会写回磁盘或补进缓存。此前状态消费者只接收实际缓存，它对缺失/半写终态的拒绝保持；本轮将“预期的不完整证据形态核对通过”和“任务完成”分别表示。

两次完整回放结果：

| 观察 | 数量及含义 |
| --- | --- |
| 实际进程 | 52 guardian、52 requester、52 worker，共156 |
| guardian被witness直接wait | 52；50次SIGKILL、2次0 |
| actor NOTE_EXIT与ECHILD | 104；witness actor waits=0 |
| actor由创建者已wait | 4，来自两次normal |
| actor终止但回收未认证 | 100 |
| 发布中断 / 独立事件 | 48 / 344 |
| 选中exit文件状态 | 36缺失、4空、4半写、8完整 |
| 完整exit文件fsync后仍中断 | 4；均拒绝任务完成 |

关键反例是exit-synced：局部exit JSON已完整保存91/StatusTransportFailure声明并fsync，随后仪器仍报告exit_requested=73并中断。此前消费者可认为actor元数据内部一致，但这不证明实际OS退出状态；本轮witness只有NOTE_EXIT，没有wait该actor，不能把73或91认定为认证后的实际wait码。未中断的guardian-loss也保存完整终态，但仍因guardian死亡拒绝。局部终态描述的是记录时的意图或观察，不能反向证明进程此后的生命周期。

24种坏件覆盖guardian未wait、提前冒认creator wait、witness冒认actor wait、事件尾部重复/缺前导/缺同步事件、pin/BOOL写长度/超界长度、exit提升为0或缺失/空/半写、缺transport/篡改frame/BOOL大小、另一个actor退出码提升、cut码或cut声明丢失、phase/BOOL actor PID/job/目标字节缺失，以及frame job修改后重算事件摘要。保持外部plan pin后均拒绝。

新增26项、状态候选回归26项和guardian-failure回归22项，共74测试无跳过通过。纯消费者在open/io.open/waitpid阻断下完成；只读verify在Popen阻断下完成。546来源搬移使用独立UUID/nonce/PID，50安排确定性语义一致；正确/错误/缺pin的只读CLI返回0/2/2。两次成功回放52份use/attempt/单次accept保持，重试/恢复各拒绝52次，证据不变；2对实际receipt/part同inode、nlink=2、字节相同，封存为普通独立文件。

失败尝试也计入本轮：

- r1在第一个normal结束后，事件解析把bytearray传给只接受bytes的解析器而失败。guardian已经过communicate并退出0，内层文件记录两个actor均已wait；事件流未保存，actor退出通知尚未形成保存记录。
- r2修正转换后，又将publication事件列表覆盖为kqueue事件，保存JSON时报错。normal的outer和两份退出观察已保存，内层两个actor已wait；publication事件流仍未保存。
- 两份失败包保持封存，原临时normal文件快照另存validation。r3修复两处harness问题后才完成全套安排；不把r1/r2算作全套通过。r2按冻结控制路径已执行重试/恢复拒绝，但未到保存recovery记录；保留这一证据缺口，不补写旧包。
- 因此本轮含失败运行共162个Python进程：54个guardian、54个requester、54个worker。54个guardian完成wait；8个actor有创建者wait记录，100个回收仍未认证。保存的actor退出观察共106份（完整回放104、r2另2），r1没有保存这部分事件。失败normal另有2对实际receipt/part硬链接。没有额外单元进程或actor PID信号。

边界：本轮只是固定进程退出后文件视图与调用顺序，不证明断电持久性。局部文件没有目录fsync或最后提交标记；同步文件IO仍无独立中断期限。独立事件管道也依赖witness存活，没有witness故障、所有后代回收或通用OS supervisor证明。旧14个孤儿回收状态仍未认证，orphan_reaping_verified始终false。

外部pin为调用方信任输入；协调修改outer和checkpoint的guardian PID声明仍能在normal获得模型完成，来源与物理授权保持false。摘要校验不是校验到exec输入的原子绑定；搬移hook仅覆盖Python父回放，不继承到guardian/actor/CLI，不证明OS能力隔离。单目录use不等于全局nonce防重放。SDK材料来自历史缓存，没有新SDK、driver clock/timebase、quiet drain或生产permit认证。

证据：

- review：`private/analysis/A23-terminal-publication-review-20261021-r3`
- review SHA256SUMS：`6f275dbd024dc8ff30c9c070919d9683b6c968f37e5375070253d02c04ad4ad5`
- validation：`private/analysis/A23-terminal-publication-validation-20261021-r3`
- closeout：`private/analysis/A23-terminal-publication-closeout-20261021`
- 失败包：`private/analysis/A23-terminal-publication-review-20261021-r1`、`private/analysis/A23-terminal-publication-review-20261021-r2`

只读入口：`tools/audit_a23_terminal_publication.py --check <review> --expected-sha256 <review_pin>`。纯入口为`assess(terminal_plan_bytes, plan_pin, job_byte_cache, witness_observation, guardian_checkpoints, actor_exit_notes, publication_events)`。terminal-plan/transport-plan/failure-plan/owned-plan/integrated-plan/launch摘要层级不同；沿用既有路径、节点、字节与普通文件封存限制。

23项保护文件、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。

下一步离线设计局部终态发布协议候选，补充目录同步和最后提交标记的失败窗口。完整记录仍不能代替wait；不从journal PID清理、不自动重启、不接生产或硬件。

前序：[状态管道显式失败候选](A23_STATUS_TRANSPORT.md)。

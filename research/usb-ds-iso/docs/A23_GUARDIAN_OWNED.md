# A23 guardian 直接拥有 worker 的离线对照（2026-10-21）

后续：[guardian自身中断与管道失效对照](A23_GUARDIAN_FAILURE.md)完成537来源、33安排与64测试。新46个actor仅10个有创建者wait，36个终止但回收未认证；不能把上一阶段存活guardian的直接wait结论延伸到guardian死亡。以下保留原阶段。

本阶段新增4个来源：固定requester parent、纯消费者、guardian audit与tests，总计532，原528来源保持。冻结的worker包装、内部Python fixture、发布IO继续使用原字节；parent不再创建worker，只通过管道请求一次绑定交接。生产broker/receiver/collector/permit、原launcher、driver/桥/C均未改，SDK材料仍为历史缓存。

新拓扑的关键是guardian直接保留两个Popen句柄：一个requester parent、一个worker。worker创建后，句柄先进入guardian局部状态，再发布ownership记录。因此owner记录缺失或半写仍会被报告为缺口，但不影响存活guardian用实际子进程句柄wait；没有从journal PID发送信号的恢复路径。

流程：

1. guardian先独占并同步guardian-use，绑定owned-plan和launch摘要。parent只发送包含job、nonce、plan摘要与requester/guardian PID声明的请求；请求前/请求后已退出的固定场景不创建worker。
2. guardian验证请求，创建原launcher-use与attempt，同步attempt文件/job/父目录，记录launch.ready，再直接Popen固定worker。worker仍使用既有ready/gate与requester lifeline检查。
3. guardian保留句柄后发布handoff/owner，handoff绑定job、nonce、plan/launch/integrated-plan摘要、requester/guardian/worker PID及maximum_accepts=1。parent核对后独占保存一次accept；错误job/nonce和第二份handoff均拒绝。
4. guardian放行worker，在parent被中断时仍由自己communicate/wait。取得实际wait状态后，才向仍存活的parent发送绑定handoff摘要的结果；worker自报end与wait返回码必须一致。

新plan保存为owned-plan.json；为原封不动的worker包装提供同字节crash-plan.json兼容别名，纯消费者强制两者相等。这没有沿用旧“parent创建worker”的结论；creator与wait另由新guardian观察明确记录。parent源码AST也检查没有Popen/fork/waitpid/kill/killpg/run_path调用。

36种安排首轮通过：16种进程/协议安排加20种缓存坏件。

| 安排 | 结果 |
| --- | --- |
| normal | 唯一允许guardian_owned_model_complete |
| before-request / after-request | parent退出79，无worker；guardian-use保留，不重试 |
| worker-unrecorded / owner-partial / owner-synced | 终止parent，worker因lifeline EOF退出86；guardian仍完成wait，前两者保留记录缺口 |
| after-handoff | parent已接受交接再退出79；worker退出86，回收成功但任务不完成 |
| child-payload.begin / receipt.partial / receipt.link / stdout.emit | 在固定暂停点SIGKILL requester；worker因父EOF退出86，guardian直接wait，保留结果/部分结果 |
| after-parent-report | worker完整完成且guardian已wait，parent仍退出79，外层拒绝 |
| handoff-job-mismatch / handoff-nonce-mismatch | parent拒绝且退出82，worker不执行payload，guardianwait86 |
| handoff-repeat | parent仅接受一次，第二份handoff拒绝并退出82，workerwait86 |
| guardian-gate-closed | worker因gate EOF退出87，无payload；guardianwait成功但拒绝任务完成 |

20种坏件包括未wait/错误creator/BOOL或拼接worker状态/worker计数、requester未wait/BOOL状态、缺失或错误owner、handoff nonce、缺失或错误accept、重复接受升级、request nonce/accept摘要、end原因或PID、result的wait/worker字段及缺失父目录同步步骤。保持原owned-plan pin后均拒绝。

新增22项、父中断回归20项和集成launcher回归22项，共64测试无跳过通过。纯消费者在open/io.open/waitpid阻断下分析16份缓存；只读verify在Popen阻断下完成。532来源搬移后以独立UUID/nonce/PID回放，36安排的确定性语义一致；正确/错误/缺pin的只读CLI返回0/2/2。

两份回放共新建32个requester和28个worker，全部60个进程都由本轮guardian持有的直接子进程句柄完成wait。requester返回分布为8次79、14次注入SIGKILL、6次82、4次0；worker实际wait状态为22次86、2次87、4次0，并与其end报告一致。4份owner缺失/半写的worker也已直接wait；不会因此把失败任务升级为完成。

32份guardian-use均保留，28份已启动场景的attempt保持；重试/恢复各拒绝32次，证据字节不变。18份parent-accept各只写一次，8对实际receipt/part核对同inode、nlink=2和字节相同，封存复制为独立普通文件。按journal PID发送信号0次。回归测试另有4个仅单元操作目录和2个模拟争用线程，没有额外实际worker。

本轮与上一阶段的区别必须保留：上一阶段20个worker只确认终止，其中14个在原parent中断后回收未认证；本轮是新拓扑、新进程，28个worker都有guardian实际wait证据。它不能追认旧14个worker已回收。全局orphan_reaping_verified仍false，新的guardian_worker_wait_model_valid只表示当前直接子进程的模型检查通过。

边界与负对照：

- 该对照假定guardian保持存活。本阶段没有终止guardian，也没有证明guardian故障后的回收、任意指令崩溃或所有后代进程树清理。
- 它是固定源码/固定参数/有界小报告的审计原型，guardian用communicate(timeout=3)收集；不是通用生产supervisor/broker，也未替代既有生产入口。同步文件IO仍没有独立中断期限。
- worker源码中的runtime record hook和gate仍为既有离线fixture安排；SDK payload/receipt/snapshot是历史模型字节，没有真实SDK、时钟域或quiet drain认证。
- 对原缓存发布消费者的复用采用显式机械投影：先验证原始trace为包含launch.ready的合法前缀，再仅移除这个新增边界，生成内部publication plan检查历史材料和receipt。投影plan不作为外部授权，实际guardian wait独立核对；删除真实同步步骤仍拒绝。
- 外部owned-plan pin是调用方信任输入，不是签名。负对照协调重pin after-parent-report为normal并修改外层退出、handoff/use/消息绑定，可得到模型完成；来源、生产、硬件、断电和旧孤儿回收标志保持false。
- 独占标记只约束保留目录；没有全局nonce防重放、断电持久性、校验到exec/child读取的原子绑定或OS能力隔离。搬移hook仅覆盖Python父回放，对原checkout及/Volumes打开观察0，不继承到requester/worker/CLI。

证据：

- review：`private/analysis/A23-guardian-owned-review-20261021-r1`
- review SHA256SUMS：`d67c52e911ca33b15819e337ad2b3b824f84419cbc581c24a14acb5a5dbeae18`
- validation：`private/analysis/A23-guardian-owned-validation-20261021-r1`
- closeout：`private/analysis/A23-guardian-owned-closeout-20261021`

只读入口：`tools/audit_a23_guardian_owned.py --check <review> --expected-sha256 <review_pin>`。单case纯入口为`assess(owned_plan_bytes, plan_pin, job_byte_cache, guardian_observation, requester_messages, worker_messages)`。review、owned-plan、integrated-plan、launch摘要层级不同，沿用8192节点与既有字节/路径/普通文件封存限制。

23项保护文件、实际49/65账本及失败owner/state保持；65已回收、remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录保留/授权消费/permit claim均0，生产采集关闭。

下一步离线覆盖guardian自身中断时的管道失效与恢复拒绝，明确外层生命周期依赖；继续区分“终止”与“wait回收”，不从journal PID重建清理权限，不接生产broker或硬件。

前序：[父进程中断与worker退出观察](A23_PARENT_CRASH.md)。

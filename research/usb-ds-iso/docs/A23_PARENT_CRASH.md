# A23 父进程中断、worker 归属与退出观察（2026-10-21）

后续：[guardian直接拥有worker的离线对照](A23_GUARDIAN_OWNED.md)完成532来源、36安排与64测试。本轮28个新worker由guardian直接wait；旧14个非子进程worker回收状态仍未认证，不追认旧结果。以下保留原阶段。

本阶段新增固定parent/worker包装、纯消费者、audit与tests共5个来源，总计528，原523来源保持。使用前阶段已封存的同步launcher和worker原字节，在新的临时副本中注入Popen前后父进程中断；生产receiver/collector/permit、原launcher/driver/桥/C均未修改，SDK数据仍为历史模型缓存。

已复现此前的归属窗口：父进程Popen成功后、owner记录创建前退出，worker确已存在，但owner.json缺失；owner记录半写时也相同。因此，缺失或无效的ownership记录不能用作“没有worker”的证据，也不能授权重启或按其中PID清理。

实验的固定安排：

- 审计guardian直接拥有parent子进程。parent调用冻结launcher，运行时只包装其Popen，原launcher源码不改。
- worker仍由parent的Popen创建；新wrapper在同一worker进程中运行冻结的Python fixture，不再启动第三层进程。wrapper核对6个运行来源摘要，先发带job/nonce/plan绑定的ready消息，再等待guardian管道。
- parent独占持有lifeline的写端，worker持读端。parent退出后，worker在固定检查点读到EOF并以86中止；guardian控制管道关闭则以87中止；等待guardian最多2秒，超时以88拒绝。本轮未触发超时后备。
- guardian在worker仍被管道挡住时，通过macOS kqueue EVFILT_PROC/NOTE_EXIT建立只读退出观察，再放行或在指定子步骤暂停时SIGKILL自己的直接parent句柄。guardian不从owner文件或ready消息的PID向worker发信号。
- 退出事件和end消息分别保留。guardian尝试waitpid(worker,WNOHANG)均得到ECHILD；它不是worker父进程，不能把退出观察记为亲自wait回收。

27种安排首轮通过：11种进程安排加16种缓存坏件。

| 场景 | parent结果 | worker结果与准入 |
| --- | --- | --- |
| normal | 退出0，原launcher报告完成 | 原parent已wait，唯一允许外层模型完成 |
| before-popen | 固定退出79 | 无worker握手/退出事件，use/attempt保留，拒绝 |
| after-popen-unrecorded | 固定退出79，owner缺失 | guardian收到ready，父lifeline EOF后退出86；归属记录缺口成立 |
| owner-partial | 固定退出79，owner半写 | 同上，不修复记录或重启 |
| owner-synced | owner文件同步后退出79 | 记录有效也不代表允许恢复；worker退出86 |
| child-payload.begin / receipt.partial / receipt.link / stdout.emit | 在worker固定暂停点SIGKILL parent（-9） | worker读到父EOF退出86，保留相应部分或完整结果，全部拒绝 |
| after-parent-report | 原launcher已完成报告并wait worker，外层parent退出79 | 内层完成保持true，外层仍拒绝 |
| gate-closed | parent正常收集worker失败后退出0 | guardian gate EOF，worker退出87且不执行payload，拒绝 |

16种坏件检查owner的BOOL PID/父PID/plan摘要、ready的BOOL PID/nonce/plan摘要、end原因/worker PID、缺退出事件/错误事件PID、把guardian观察升级为wait、BOOL returncode/未wait父进程、缺原parent报告、worker计数矛盾和owner缺失；保持原外部crash-plan pin后全部拒绝。

新增20项、集成launcher回归22项及发布回归22项，共64测试无跳过通过。纯消费者在open/io.open和waitpid阻断下分析全部11份缓存；只读verify在Popen阻断下完成。528来源搬移后使用新UUID/nonce/PID重跑，27安排的确定性语义一致，正确/错误/缺pin的只读CLI返回0/2/2。

两次回放共启动22个parent和20个worker：

- 22个直接parent均已wait；parent退出分布为10次固定79、8次注入SIGKILL、4次0。
- 20个worker均收到绑定end消息并观察到内核NOTE_EXIT；报告退出分布为14次父EOF中止86、2次guardian EOF中止87、4次正常0。
- 其中6个worker由原parent完成wait；另14个在parent中断后成为非guardian子进程，只确认终止，**不声明已由guardian或系统完成回收**。orphan_reaping_verified始终false。
- 两份回放共4次复现owner缺失/半写但worker存在。8对实际receipt/part核对同inode、nlink=2和字节相同；封存时复制为独立普通文件。
- 22份use/attempt均保留，重试与恢复各拒绝22次且字节不变；guardian向worker PID发送信号0次。回归测试另有6个仅单元操作目录和2个模拟争用线程，无额外实际worker。

重要边界：

- 这是受控gate、固定源码和固定检查点下的进程中断实验，不是原launcher在任意指令位置崩溃的完整证明。worker包装新增管道检查及运行时record hook，不能声称生产SDK已有该行为。
- 父死亡后能够终止worker，与能够wait回收worker是不同结果。当前guardian不拥有worker，实际回收仍依赖其他进程，尚未认证；也不证明所有后代或进程树清理。
- owner文件fsync、管道握手与kqueue事件均未建立全局PID/来源认证或断电协议。PID只用于本次只读退出观察和关联；不允许拿封存PID发送信号。没有全局nonce防重放、OS能力隔离或校验到exec/child读取的原子绑定。
- 外部crash-plan pin仍是调用方信任输入。负对照将after-parent-report场景重声明为normal、更新绑定pin并协调修改外层退出观察，可得到模型完成；来源、孤儿回收、生产和硬件标志保持false。
- 搬移audit hook对原checkout及/Volumes打开观察0，仅覆盖父回放Python，不继承到parent/worker/CLI。没有真实SDK、driver时钟/context刷新、原生编译或USB/SD访问。

证据：

- review：`private/analysis/A23-parent-crash-review-20261021-r1`
- review SHA256SUMS：`366b54ca0fc43065281c17c20026af597ff1d2385e1ed95b71b043ba8eed1ecd`
- validation：`private/analysis/A23-parent-crash-validation-20261021-r1`
- closeout：`private/analysis/A23-parent-crash-closeout-20261021`

只读入口：`tools/audit_a23_parent_crash.py --check <review> --expected-sha256 <review_pin>`。单case纯入口为`assess(crash_plan_bytes, plan_pin, job_byte_cache, outer_observation, guardian_observation, worker_messages)`。review、crash-plan、integrated-plan和launch是不同摘要层级；沿用8192节点与既有字节/路径/普通文件封存限制。

23项保护文件、实际49/65账本及失败owner/state保持；65已回收、remaining0，81..112未正式保留。正式记录/保留/授权消费/permit claim均0，生产采集关闭。

下一步准备guardian直接拥有并wait worker的离线对照，让parent只接受已绑定的运行交接；保留本轮缺记录反例，继续拒绝按journal PID清理和自动重启，不接生产broker或硬件。

前序：[同步发布接入离线fixture launcher](A23_INTEGRATED_FIXTURE.md)。

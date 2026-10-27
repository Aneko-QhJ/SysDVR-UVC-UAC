# A23 统一 supervisor 收集、清理与关闭候选（2026-10-20）

后续：[job/receipt只读关联](A23_SUPERVISOR_JOB_LINK.md)完成507来源、57场景与56测试；识别entry与SDK receipt绑定差异，提供未应用静态接入计划，只声明跨模型对应，不改变permit或认证现场同次job。以下保留原阶段。

新增5个独立来源（统一固定fixture、supervisor、纯字节消费者、audit、tests），总计503，原498来源及两阶段封存保持。此前18种收集与15种清理安排合并，normal去重后32种，再补5种关闭故障，共37种。全部经过同一个supervisor函数、33字段observation schema和同一纯字节准入规则；不再根据旧schema分派准入。旧模块仅提供场景列表、字节格式/材料关联与历史来源校验，两个旧supervisor未执行。

37种安排在原位置与搬移回放均通过。仅normal、read-interrupted允许离线模型完成，其余35种拒绝。继承的覆盖包括缺/非法stdout、缺材料、退出7、SIGTERM、输出前后超时、stdout/stderr越限、stderr、报告绑定错误、driver/内部worker失败、spawn失败、后代持管道、EOF但进程活、读取/selector错误、组终止失败或不存在、直系后备、wait错误/超时和组合清理失败。

新增关闭安排：

| 安排 | 观察结果 |
| --- | --- |
| stdout-close-error | 子进程已退出0、driver有效，但stdout父侧关闭注入失败，拒绝 |
| stderr-close-error | 同上，stderr关闭失败，拒绝 |
| both-close-error | 两个管道关闭均注入失败，两个错误都记录，拒绝 |
| selector-close-error | selector关闭注入失败，后续两个管道仍执行关闭，拒绝 |
| close-and-wait-error | EOF但进程仍活，超时终止；stdout关闭失败后仍尝试cleanup wait，注入wait失败，候选保持未回收，拒绝 |

每个已启动job都会按selector→stdout→stderr分别记录close_attempts、close_completed、close_errors。一次关闭错误不会跳过后续关闭或cleanup wait。关闭注入发生在实际close之前，错误资源留给独立测试harness清理；harness资源救援与直系子进程救援分别记录，不改写候选观察或升级准入。正常退出已回收的关闭失败场景不会再对已回收PID/进程组发信号。

统一输出限额为stdout64KiB、stderr8KiB，缓存各仅多保留1字节证明越限，每次os.read最多4096字节。selector读取与completion wait共用Popen返回后开始的0.5秒supervisor monotonic deadline，cleanup wait另限0.5秒；一次EINTR在同一预算/子进程继续，不重启worker。全流程不映射driver、owner或设备时钟域。挂起worker和fork holder各有2秒fixture TTL，harness wait另限3秒。spawn/exec本身及材料收集耗时不由该deadline认证。

EOF、进程退出、组信号attempt/outcome、直系fallback、completion/cleanup wait、资源关闭分别表达。组信号前不poll/reap自己持有的leader，保留PID生命周期；not_found不标记sent。任何终止尝试本身阻止完成资格；输出完整、退出0或driver完成也不能绕过内部worker健康和资源关闭要求。测试故障明确是注入的调用结果，不是现场OS异常复现。

纯消费者验证严格33字段、类型与状态关系、资源关闭标签/顺序/结果、精确23或25成员材料清单、stdout的case/来源/清单/result绑定，以及已有epoch/receipt/版本/worker关联。候选observations不保存动作PID；只有fixture诊断中保存holder PID/group，绝不据此发送信号。全部动作仅针对本次创建并持有的句柄和原组，不提供生产或任意命令入口。

验证：

- 新20、旧cleanup20及旧collection20项，共60测试无跳过通过；旧回归只读封存材料，不重跑旧worker或driver。
- 覆盖33字段错误类型、矛盾关闭声明、48次正常/嵌套材料成员缺失、23次normal成员截断；重算worker清单与stdout摘要后的内部健康伪造拒绝。
- 消费者open/io.open被阻断时仍分析全部37场景；外层收集与封存正常读文件。只读verify不launch，错误fixture pin在Popen前拒绝。
- 503来源搬移后重跑37场景，语义与完整observation一致；正确/错误/缺失pin的只读CLI返回0/2/2。

原位置与搬移共72个直系Python worker、6个fork holder，共78个进程；另2次spawn错误为注入，无进程。候选直接回收64个，harness直系救援8个、父侧资源救援12次。组终止尝试36次（sent30、模拟error4、模拟not_found2），直系后备尝试6次（sent4、模拟error2）；候选关闭尝试216次、成功声明204次，剩余12次由harness清理。未认证后代wait回收、逃逸session或整个进程树。未新增原生编译、driver/SDK模型或实际时钟查询。

限制负对照继续保留：把stdout-close-error观察中的close_errors清空，并把close_completed伪造成全部成功，纯消费者会准入内部一致声明。封存外部pin与固定矩阵审计能发现档案修改，但不建立真实进程/close调用来源认证、exec原子绑定或OS能力隔离。Python搬移hook拒绝原checkout和/Volumes文件打开，hook不继承到子进程。生产集成及permit保持false。

证据：

- review：`private/analysis/A23-supervisor-unified-review-20261020-r1`
- review SHA256SUMS：`f0322a1990f2d1db525984856db81c87c1ff2b93db1d0c80bf971541192b8f67`
- validation：`private/analysis/A23-supervisor-unified-validation-20261020-r1`
- closeout：`private/analysis/A23-supervisor-unified-closeout-20261020`

只读入口：`tools/audit_a23_supervisor_unified.py --check <review> --expected-sha256 <pin>`。validation附正确的`replay_a23_supervisor_unified.py`及其摘要，并保留搬移结果、封存和测试日志。沿用8192节点、64MiB单文件/256MiB总量、深度18及普通非符号链接文件约束。

23项保护文件、实际49/65账本及失败修复owner/state保持；65已回收、remaining0，81..112未保留。USB/SD/真实SDK/driver时钟/context刷新/部署/正式发行与保留均0，生产采集关闭。

下一步回到既有waiting/job/receipt/permit消费接口，梳理统一观察如何只读关联job绑定与receipt、列出未认证条件并准备静态接入差异。先保持离线fixture限制、真实入口和发行关闭；现场来源、真实时钟域、SDK runtime、quiet/drain及生产permit仍需独立验证。

前序：[独立收集候选](A23_SUPERVISOR_CANDIDATE.md)、[管道与清理候选](A23_SUPERVISOR_CLEANUP.md)。

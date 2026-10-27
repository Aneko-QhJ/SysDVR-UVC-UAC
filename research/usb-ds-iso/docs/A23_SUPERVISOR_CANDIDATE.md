# A23 独立 supervisor 收集候选（2026-10-20）

后续：[supervisor管道、退出与清理边界](A23_SUPERVISOR_CLEANUP.md)补15种安排；60测试与498来源搬移通过，区分EOF/退出、组终止sent/not_found/error和harness救援，不认证整个进程树或来源。以下保留原阶段。

本阶段增加纯 Python supervisor、固定假 worker、纯字节消费者及审计/测试5个来源，总计493，原488来源保持。使用上阶段已封存完整 driver 模型的3份材料种子（normal、capture-worker-error、capture-worker-unfinished-return），没有重新构建或执行 driver/native/SDK。固定假 worker 只复制这些离线材料、输出报告并模拟进程行为。候选没有接入生产 supervisor、receiver 或 permit。

| 18种指定安排 | 结果 |
| --- | --- |
| normal | 进程退出0、流完整、stdout与全部材料关联、driver/缓存worker资格有效，允许离线模型完成 |
| no-stdout | 材料完整、进程退出0，但缺 stdout，拒绝 |
| malformed-stdout / partial-stdout | stdout非法/截断，拒绝 |
| empty-materials / missing-material | 空材料或缺 version-profile，拒绝 |
| abnormal-exit / signal-exit | 实际观察退出7 / SIGTERM返回-15，拒绝 |
| timeout-before-output / timeout-after-output | 超时前无材料，或已有有效stdout与完整材料；均终止进程组、回收直系子进程并拒绝 |
| oversize-stdout / oversize-stderr | 超过64KiB / 8KiB，上限加1字节用于记录越界，终止并拒绝 |
| stderr-output | 退出0但有stderr，按此候选的严格策略拒绝 |
| wrong-case / wrong-digest | stdout的case或清单摘要不符，拒绝 |
| driver-failure | 外层进程退出0，缓存driver与worker均失败，拒绝 |
| worker-failure | 外层进程退出0、driver完成，但缓存worker失败，拒绝 |
| spawn-error | 注入一次Popen OSError，无子进程、无重试，拒绝 |

每套18场景实际创建17个固定 Python 子进程，另1个为注入的 spawn 失败。全部已创建直系子进程均 wait 回收，不重试。命令固定为当前 Python、-I、-B 和已核对SHA的假 worker 脚本，仅接受指定case；子进程使用新 session、DEVNULL stdin 和两个管道。输出使用 selector 分块读取、内存有界；超时和输出越界时对本次创建的进程组发SIGKILL，记录返回-9。没有任意命令或生产入口。

supervisor 的 deadline 用独立 time.monotonic：超时场景0.5秒，其他场景2秒，从Popen返回后开始；结束清理的 wait 上限另为1秒。不声称约束Popen本身耗时，也不把此时钟映射到driver/owner/设备域。模型worker中的60秒等待均由父进程在上述限额内终止。本轮没有查询driver时钟、Mach timebase或刷新执行上下文。

收集规则区分 process_healthy、driver_complete、worker_healthy 与 completion_admitted。进程退出0、stdout声称成功或driver完成，单项均不能授权完成。stdout关联case、材料来源、完整文件清单摘要、result摘要及完成状态；消费者继续调用此前的纯字节关联校验，检查epoch/receipt/版本/worker材料。normal需精确23成员，两个失败种子各25成员。异常结果是可保存的失败证据，不是收集器崩溃。

来源仍有限制：收集记录与stdout、清单、PID/返回码声明不能独立证明现场来源。负对照把abnormal-exit缓存 observation 的returncode从7改为0后，纯消费者会把内部一致材料视为完成；它不认证这个伪造的外部观察。固定矩阵审计和外部review pin会拒绝修改后的封存档案，但这不等于建立了生产进程来源边界。script摘要检查与exec也不是原子绑定。未测试后代进程、继承管道持有者、kill失败/读取中断或全部调度，不声称进程树回收/OS能力隔离。

验证：新增20、完整driver worker回归20和独立worker回归20项，共60项无跳过通过。48次正常/嵌套材料成员缺失、23次normal材料逐文件截断均拒绝；21个observation字段的错误类型拒绝；重算worker清单、stdout摘要后的健康伪造拒绝。消费者在open/io.open阻断下仍分析全部18场景。消费者不读文件，外层收集和封存检查读文件。

493来源搬移到临时目录后重新运行18场景，语义和完整收集记录一致；三种只读CLI正确/错误/缺失pin返回0/2/2，验证时不启动子进程。原位置与搬移共34个Python假worker、2次模拟spawn失败、34次直系回收，8次超时/输出超限的进程组终止，2次假worker自身SIGTERM退出。没有新增原生编译或完整driver执行。Python搬移回放阻止原checkout和/Volumes文件打开；该hook不继承到子进程，不宣称OS隔离。

证据：

- review：`private/analysis/A23-supervisor-candidate-review-20261020-r1`
- review SHA256SUMS：`0d79d13386e5d5e8b25b9944f05371ce245ccfbbbc6b98f943adba36c6a5e24d`
- validation：`private/analysis/A23-supervisor-candidate-validation-20261020-r1`
- closeout：`private/analysis/A23-supervisor-candidate-closeout-20261020`

只读入口：`tools/audit_a23_supervisor_candidate.py --check <review> --expected-sha256 <pin>`。来源快照、3种子和全部子进程结果保存在review中；独立搬移回放与日志保存在validation中。封存沿用前阶段限定8192节点、64MiB单文件/256MiB总量、深度18及普通非符号链接文件约束。

23项保护文件、实际49/65账本和失败修复owner/state保持；65已回收、remaining0，81..112未保留。USB/SD/真实SDK/context刷新/部署/正式发行与保留均0，生产采集关闭。

下一步继续离线覆盖直系进程退出但后代持管道、流已EOF但进程仍活着的窗口，以及读取/终止/回收失败。实际进程来源与权限、真实时钟域、SDK runtime、quiet/drain和生产permit仍未认证。

前序：[完整隔离driver的worker故障与收集边界](A23_DRIVER_WORKER_FAILURE_MODEL.md)。

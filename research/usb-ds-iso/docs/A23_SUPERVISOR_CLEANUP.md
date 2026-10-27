# A23 supervisor 管道、退出与清理边界（2026-10-20）

后续：[统一supervisor候选](A23_SUPERVISOR_UNIFIED.md)合并两阶段32种指定安排并补5种关闭错误；503来源、37场景与60测试通过，同一观察/限额/终止/准入，保留来源未认证负对照。以下保留原阶段。

新增5个独立来源（固定Python fixture、cleanup候选、纯字节消费者、audit、tests），总计498，原493来源不变。没有修改上阶段候选或生产入口，也没有重新运行driver/native/SDK；材料复用已封存normal种子。此前3份输入种子及清单完整保留，实际只使用normal。

15个指定安排首轮通过：

| 安排 | 观察与准入 |
| --- | --- |
| normal | 两路EOF、正常退出0，允许离线模型完成 |
| read-interrupted | 注入一次read EINTR，在同一deadline、同一子进程继续，正常完成；不重启worker |
| leader-both-held / leader-stdout-held / leader-stderr-held | 固定worker fork一个持管道后代，ready握手后直系进程退出0；对应管道仍未EOF，超时终止原进程组，拒绝 |
| eof-worker-alive | 两路EOF但worker仍活，完成wait到期后终止，返回-9，拒绝 |
| stdout-eof-worker-alive / stderr-eof-worker-alive | 仅一路EOF，另一管道仍持有；超时终止，拒绝 |
| read-error / selector-error | 有效报告已收到后注入读取/selector错误，终止并拒绝 |
| group-kill-error | 注入killpg失败，明确记录error，后备终止仍由候选持有的直系进程，wait回收；拒绝 |
| group-kill-not-found | 注入killpg目标不存在，记录not_found，不能标为sent；后备直系终止、回收，仍拒绝 |
| wait-error / wait-timeout | 注入cleanup wait OSError / TimeoutExpired，候选保持reaped=false、returncode=null，拒绝；测试harness单独救援回收 |
| cleanup-multiple-errors | 组终止、直系后备终止及cleanup wait均注入失败，候选拒绝，测试harness单独救援回收 |

新候选把group/fallback的attempted与none/sent/not_found/error分别记录。不在组信号前poll/reap直系leader；保留自己创建的Popen句柄及未回收leader的PID，再处理原进程组，避免依据材料中的任意PID采取动作。holder PID/group只作fixture诊断，不用作终止目标。正常completion wait已成功的路径不会再发信号。此策略不认证session身份、exec原子绑定或逃离进程组的后代。

fixture的fork仅发生在固定单线程Python进程内。3个holder场景通过独立ready管道握手；holder有2秒TTL，supervisor用独立monotonic的0.5秒deadline。EOF和退出分别判定；超时后cleanup wait限0.5秒。注入错误明确是模拟的OS调用结果，不声称复现了现场内核故障。harness救援的wait另限3秒，仅清理本测试创建并持有的直系句柄；它不改变候选观察或完成资格。后代并非supervisor直系子进程，未声称wait回收后代或认证整个进程树。

纯字节消费者检查25个观察字段、严格类型、signal attempt/outcome与fallback关系、EOF/退出/错误状态，以及23份normal材料、stdout与材料清单/result摘要、此前epoch/receipt/版本关联。观察字段中未保存可用于现场动作的PID。EINTR继续读取不是重启或新采集；所有场景launches=1、retries=0。stdout/stderr返回缓存各不超过64KiB+1字节，单次读取4096字节；本阶段没有扩展旧18场景的全部输出超限矩阵。

新增20、旧supervisor20及完整driver worker回归20项，共60测试无跳过通过。覆盖25字段错误类型、signal attempt/outcome矛盾、23次缺成员、23次逐文件截断，以及消费者open/io.open阻断下全部15场景通过。只读verify测试保证不launch；错误fixture pin在Popen前拒绝。

原位置与498来源搬移回放的语义和完整观察记录一致；三种只读CLI正确/错误/缺失pin返回0/2/2。两处合计30个直系Python worker及6个fork holder，共36个进程；候选直接回收24个，测试harness救援回收6个。组终止尝试26次：sent20、模拟error4、模拟not_found2；直系后备尝试6次：sent4、模拟error2。6个holder收到原组终止路径覆盖，但不声明后代wait回收。没有原生编译、driver模型/真实SDK执行或driver时钟查询。

来源限制继续保留：把eof-worker-alive观察中的超时、退出码和组信号字段一起改成内部一致的正常声明，纯消费者仍可能准入，负对照已验证。固定矩阵审计和外部review pin可以发现封存档案变动，但不认证真实进程来源。Python搬移回放禁止原checkout与/Volumes文件打开；hook不继承到子进程，不证明OS能力隔离。

证据：

- review：`private/analysis/A23-supervisor-cleanup-review-20261020-r1`
- review SHA256SUMS：`0dd9603fb5d9b0084c07ca423dc4dac9ffb9925547737fda7f7efee3f5e8054e`
- validation：`private/analysis/A23-supervisor-cleanup-validation-20261020-r2`
- closeout：`private/analysis/A23-supervisor-cleanup-closeout-20261020-r2`

封存附件更正：r1 validation误附上一阶段candidate回放脚本；原review、实际回放结果、全部测试及源文件均未改变。r2 validation移除误附脚本，补入正确cleanup回放脚本及摘要说明；r1封存完整保留，更正未新增进程执行。

只读入口：`tools/audit_a23_supervisor_cleanup.py --check <review> --expected-sha256 <pin>`。材料、holder握手声明、候选观察与harness救援记录分别保存，read-only校验不启动任何worker。沿用8192节点、64MiB单文件/256MiB总量、深度18与普通非符号链接文件的封存约束。

23项保护文件、实际49/65账本及失败修复owner/state保持；65已回收、remaining0，81..112未保留。USB/SD/真实SDK/context刷新/部署/正式发行与保留均0，生产采集关闭。

下一步：在新隔离副本中统一此前18种收集安排和本阶段15种清理安排（normal重叠），使用一致的观察schema、输出限额、终止与准入规则；补流关闭异常，保留两阶段封存和来源未认证负对照。现场进程来源、真实时钟域/SDK runtime/quiet drain及生产permit仍未认证。

前序：[独立supervisor收集候选](A23_SUPERVISOR_CANDIDATE.md)。

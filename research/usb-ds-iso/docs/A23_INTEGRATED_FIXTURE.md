# A23 同步发布接入离线 fixture launcher（2026-10-21）

后续：[父中断与worker归属窗口](A23_PARENT_CRASH.md)完成528来源、27安排与64测试。复现owner缺失/半写但worker存在；退出事件不升级为wait，14份孤儿worker终止后的回收仍未认证。以下保留原阶段。

本阶段新增6个来源：拆分的发布IO、新离线launcher、固定worker、纯字节准入、audit、tests，总计523，原517来源保持。已把前阶段发布顺序接入新的 fixture launcher 副本；旧launcher、生产receiver/collector/permit、driver/桥/C和未应用静态diff均未修改。嵌套SDK材料仍是历史缓存，没有新SDK或硬件执行。

父子职责现在明确分开：

1. 父进程先以xb独占创建launcher-use记录，绑定launch和integrated-plan摘要，并同步该文件。重复或并发调用在写trace之前被拒绝；空use文件也保留且拒绝。
2. 父进程核对外部plan pin、固定worker、两个库摘要与输入清单，再独占创建attempt、分段写入、fsync文件并同步job及其父目录。完成后记录launch.ready，才调用固定Popen。
3. 子进程核对use、attempt、父trace完整前缀、源码库和输入摘要，仅执行后半段：payload屏障、历史材料同步、receipt.part写入/fsync、不可覆盖link发布、result目录同步及stdout。
4. 父进程有界收集输出、等待和清理；纯消费者联合检查新计划/使用记录、父同步前缀、实际supervisor观察、receipt/part、stdout及原缓存语义。只有整条链正常才允许integrated_model_complete。

拆分IO继续使用原封不动的`a23_fixture_publication.write_all/sync_directory`；正常trace为前阶段的8个attempt步骤、一个新的launch.ready边界，以及10个子步骤。发布层本身接受字节，语义由父/worker/消费者核对。plan明确绑定launch、库摘要和注入安排；外部pin是调用方信任输入。

51种安排首轮通过：31份实际launcher安排加20种缓存坏件。

| 安排 | 数量 | 结果 |
| --- | --- | --- |
| 正常 | 1 | 唯一允许集成模型完成 |
| 父attempt文件/job目录/父目录同步前模拟失败 | 3 | 保留use/attempt，不记录launch.ready，不启动worker |
| 模拟spawn失败 | 1 | 同步完成但无worker，拒绝 |
| 子10个发布步骤后退出73 | 10 | 保留部分或完整材料，拒绝 |
| 子材料同步/receipt文件同步/link/目录同步前模拟IO错误74 | 4 | 拒绝，不修补或重试 |
| worker退出7、输出后超时、缺stdout、stderr | 4 | 即使receipt完整匹配也拒绝 |
| 父读取、stdout close、selector close、wait错误 | 4 | 子退出0或材料完整仍不提升资格 |
| partial+close、sync+close、exit7+close、timeout+wait | 4 | 组合失败仍拒绝 |

20种坏件覆盖use缺失/BOOL计数/plan摘要、attempt缺失/BOOL计数、缺父同步/缺ready/乱序/额外trace、part缺失或不一致、receipt错误job/授权升级、stdout/材料拼接、observation的plan/attempt绑定和close/reap/prelaunch错误。保持原plan pin时全部拒绝。

新增22项、发布候选回归22项及fixture绑定回归20项，共64测试无跳过通过。测试还确认：错误外部pin或变更库在Popen阻断下拒绝并保留use；两个线程竞争同目录时只有一个进入模拟spawn，trace没有第二份begin；空use不写trace；消费者在open/io.open阻断下分析全部31份缓存，只读verify在Popen阻断下完成。

523来源搬移后以独立UUID/nonce再跑一次，51安排的确定性准入、绑定/拒绝与恢复语义一致，CLI正确/错误/缺pin返回0/2/2。两次共62个audit fixture目录，62份use和attempt保持，重试与恢复各拒绝62次，六份启动前同步失败均无worker。32对实际receipt/part核对同inode、nlink=2和字节相同；封存复制为独立普通文件。

实际启动54个Python worker：候选回收50，注入wait错误的4份由harness救援回收；10次注入close失败由harness关闭资源。这些救援不修改候选observation，也不升级完成资格。没有fork后代或原生编译/完整driver/真实SDK执行。64测试另有7个仅单元操作目录、两组共4个模拟争用线程，未产生额外实际子进程。

需要保留的边界：

- 读取错误可能使父进程在stdout输出与末尾trace追加之间终止worker；原始trace和`publication_trace_complete`逐份保存，搬移语义比较排除UUID和此时序字段，只比较可重复的准入/拒绝结果。本次两份末尾完整性观察也一致，但不证明全部交错。
- supervisor的0.5秒deadline从Popen之后计时，覆盖收集/等待；父进程同步文件IO尚无独立中断期限。wait/close注入分支不证明整个进程树已回收。
- 本阶段没有中断父进程本身。父在Popen前后崩溃时的子进程归属、孤儿进程和清理尚未验证。
- use同步、attempt和目录同步是进程存活期间的调用顺序证据，不证明真实断电恢复、上游launch持久发行、全局nonce防重放或trace持久性。删除/复制目录和绕过接口仍不由此协议阻止。
- trace和外层observation没有来源认证。负对照将close失败计划改成normal、重新pin并协调修改use/observation，可获得模型完成；实际来源、断电、SDK、生产与硬件标志仍false。
- 脚本与库/输入仍通过路径核对，校验到exec/child读取的原子绑定未建立。搬移hook仅作用于Python父回放，对原checkout及/Volumes打开观察0，不继承到worker/CLI，不是OS隔离。

证据：

- review：`private/analysis/A23-integrated-fixture-review-20261021-r1`
- review SHA256SUMS：`6e33161eac73724abbad63c08f67264f30609b052fd07c0343df5bcd2c30d103`
- validation：`private/analysis/A23-integrated-fixture-validation-20261021-r1`
- closeout：`private/analysis/A23-integrated-fixture-closeout-20261021`

只读入口：`tools/audit_a23_integrated_fixture.py --check <review> --expected-sha256 <review_pin>`。单case纯入口为`assess(integrated_plan_bytes, plan_pin, job_byte_cache, stdout, stderr, observation)`。review、plan、launch摘要是不同层级。沿用8192节点与既有字节/路径/普通文件封存限制。

23项保护文件、实际49/65账本和失败owner/state保持；65已回收、remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/部署/正式发行保留/授权消费/permit claim均0，生产采集关闭。

下一步离线覆盖父进程在Popen前后中断时的worker归属与清理，保留已失败票据和拒绝重启规则；不升级到生产或真实硬件入口。

前序：[fixture中断发布与恢复拒绝](A23_FIXTURE_PUBLICATION.md)。

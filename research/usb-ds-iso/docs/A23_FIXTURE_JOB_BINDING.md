# A23 fixture 启动前绑定与退出后关联（2026-10-21）

后续：[fixture中断发布与恢复拒绝](A23_FIXTURE_PUBLICATION.md)完成517来源、43安排和62测试；新增独占标记同步与receipt分段同步/link发布候选，原launcher未改。进程中断证据不升级为断电持久性或全局防重放证明。以下保留原阶段。

本阶段新增纯字节协议、固定 Python 子进程、一次性 launcher、audit 和 tests，共5个来源；总计512，原507来源保持。实现的是新的离线 fixture job 与其输出的对应关系，没有调用 SharedSequence32 的 issue/consume、native permit claim、生产 receiver、broker 或真实 SDK。

新的 fixture job 不复用历史 shared32 job UUID，也不继承它的授权。每份 launch 声明包含独立 UUID、随机256-bit nonce、固定 fixture 摘要、缓存来源 review pin、23份输入材料的精确字节清单，以及 maximum_launches=1/model_only=true/production_execution_authorized=false。外部调用方必须另行提供 launch 摘要。

| 对象 | 产生时点与校验 |
| --- | --- |
| launch.json | 子进程启动前生成；固定 fixture 和输入材料摘要由外部 launch pin 约束 |
| launch-attempt.json | launcher 以 xb 独占创建，早于 pin/source/input 校验和 Popen；后续失败保留标记，同目录第二次调用拒绝 |
| stdout report | 本次 Python 子进程生成；绑定 UUID、nonce、launch/attempt 摘要和输出材料清单 |
| result/receipt.json | 本次 Python 子进程生成；增加 stdout 摘要，退出后由纯消费者核对 |
| SDK receipt / epoch / snapshot | 原封不动复制的历史模型缓存，明确标注 historical_model_cache；不是本次 SDK 执行的结果 |
| observation | 父进程观察退出、EOF、限额、清理和 wait；不由子进程的完成声明替代 |

新关系标为 `fixture_launch_result_correspondence`。它关闭了先前只能声明历史不同模型之间对应的 fixture 层缺口，但不认证物理同次运行、SDK 来源或生产许可。`cached_sdk_materials_generated_this_launch`、`job_launch_binding_authenticated` 和所有生产/硬件标志始终 false。

launcher 只接受 `/private/tmp` 下的规范路径、固定脚本名和外部 fixture pin，使用 Python -I -B 与固定参数。父进程通过 selector 有界收集 stdout/stderr（64KiB/8KiB），deadline 为独立 supervisor monotonic 的0.5秒；失败尝试终止本次进程组，必要时直系后备，关闭各资源并 wait。外部 harness 的回收不提升完成资格。本阶段没有 fork 后代；不证明整个进程树回收，也不宣称该新 launcher 的所有异常分支都已覆盖。

纯消费者先检查原始 stdout/stderr 字节计数和统一 observation，再核对新 report/receipt。对于明确标为历史缓存的材料，它合成原缓存协议的 report，复用旧纯校验器检查 epoch/SDK receipt/版本/终态；只在这一步替换嵌套 report 的计数，不将合成 report 当成本次 child 的 stdout 或来源证明。

34种安排通过：

- 10种启动安排：normal、退出7、输出后超时、模拟spawn失败、缺receipt、部分receipt、错误nonce、错误job、材料篡改、stderr。仅normal允许fixture完成；退出7、超时和stderr场景虽然拥有匹配receipt，仍拒绝。
- 4种启动前失败：错误外部pin、错误fixture pin、输入变化、结果目录已存在。均在尝试标记后拒绝，未调用Popen；后续调用被保留标记拒绝。
- 20种纯字节坏件：receipt的job/nonce/launch/attempt/stdout/清单/授权/额外字段，attempt的BOOL或重复计数/未消耗/job，observation绑定/未回收/close失败，stdout拼接、整套跨job移植和材料拼接。保持原launch pin后均拒绝。

新增20项、前阶段job关联回归20项及统一supervisor回归20项，共60测试无跳过通过。测试还检查所有receipt成员缺失、重算report/receipt后的BOOL attempt计数、修改并重新pin的launch授权字段、纯消费open/io.open阻断，以及两线程争用同目录时只有一个调用进入模拟spawn。只读verify在Popen阻断下完成。

512来源搬移后生成全新的job UUID和nonce，重跑相同34种安排，语义结果、拒绝原因及固定fixture摘要一致；原位置与搬移的UUID/nonce互不相交，历史输入字节清单保持一致。两次共18个真实Python fixture子进程均由候选回收，harness救援0；模拟spawn错误2次，无原生编译/完整driver/SDK执行。测试另有两个竞争线程和不产生子进程的模拟调用。

必须保留的限制与负对照：

- 外部pin是调用方信任输入，不是签名或现场来源证明。把已记录退出7的外层观察改成内部一致的退出0，纯消费者仍可给出fixture完成；物理/来源/生产标志保持false。
- 独占标记只约束保留标记的同一目录。另一个负对照将同一launch/nonce与输入复制到两个无标记目录，两者都能进入模拟spawn；模拟调用2次、实际子进程0。因此不证明全局nonce防重放、抵抗删除/复制或跨目录唯一性。
- 标记采用独占创建和关闭，没有fsync/目录fsync协议，不证明断电或崩溃后的持久单次使用。中断可留下部分receipt，只有完整匹配才能通过；尚未系统验证各写入窗口。
- 脚本和输入通过路径读取，未建立从父进程校验到exec/child读取的原子绑定；Python环境、OS能力隔离、真实进程来源和实际SDK/时钟域/quiet drain均未认证。
- 搬移audit hook仅检查Python父回放进程对原checkout与/Volumes的文件打开，观察0；不继承到fixture或CLI子进程，不等于OS隔离。

证据：

- review：`private/analysis/A23-fixture-job-binding-review-20261021-r1`
- review SHA256SUMS：`0d7c2b6bd3b8ce5a0547330dbfd12faa9b8b9d3df396d556f680ffb8a406c31d`
- validation：`private/analysis/A23-fixture-job-binding-validation-20261021-r1`
- closeout：`private/analysis/A23-fixture-job-binding-closeout-20261021`

只读入口：`tools/audit_a23_fixture_job_binding.py --check <review> --expected-sha256 <review_pin>`；单case消费者为 `assess(launch_bytes, launch_pin, attempt_bytes, observation, stdout, stderr, materials, receipt_bytes)`。review pin和launch pin属于不同层级。保留既有8192节点及单文件/总量/路径/普通文件封存限制。

23项保护文件、实际49/65账本及失败修复owner/state保持；65已回收、remaining0，81..112未正式保留。生产collector/permit、前阶段未应用静态diff保持，USB/SD/真实SDK/context刷新/driver时钟查询/部署/正式发行保留与授权消费均0，生产采集关闭。

下一步离线覆盖fixture标记及receipt的中断发布窗口，明确单目录单次使用的持久性协议与恢复拒绝边界；保留跨目录复制负对照，不升级为全局防重放或生产许可。

前序：[job/receipt跨模型只读关联](A23_SUPERVISOR_JOB_LINK.md)。

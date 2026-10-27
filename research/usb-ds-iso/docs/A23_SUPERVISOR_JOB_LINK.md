# A23 supervisor 与 job/receipt 的只读关联候选（2026-10-20）

后续：[fixture自身job启动与结果绑定](A23_FIXTURE_JOB_BINDING.md)完成512来源、34安排和60测试；新Python fixture生成独立job/nonce与receipt，历史SDK字节保持缓存标签。单目录标记不证明全局防重放或断电持久性，所有现场与生产许可标志保持false。以下保留原阶段。

本阶段回到现有waiting、entry、shared permit与collector边界，新增4个来源（纯字节关联、静态计划renderer、audit、tests），总计507，原503来源保持。没有启动新worker、driver、broker或SDK模型，没有创建job/保留/发行/消费授权。只复用先前封存的模拟job和统一supervisor缓存。

关键差异已经由9个来源的16个源码锚点确认：

| 现有边界 | 绑定或动作 |
| --- | --- |
| waiting receiver | A23MakeWaitingBoundPermit负责已有build/consumed检查及一次性handoff；本阶段不调用 |
| two-epoch entry | claimProcess先于等待，claimSelection先于driver创建；均会消费对应durable use |
| shared permit / SharedSequence32 | entry binding含build manifest、receiver、consumed receipt摘要及81..112范围；issue/consume与claim会写一次性标记 |
| SDK driver receipt | 绑定session、设备身份、descriptor摘要、first_sequence和snapshot；没有job_id或consumed receipt绑定 |
| final / waiting / bound collectors | 负责已退出producer或静态文件的冻结与既有链检查，不存在统一supervisor到job的自动授权转换 |

因此，SDK receipt完成、相同序号或相同设备声明，不能证明它就是某个job的那次运行。新候选只接受明确标为`declared_cross_model_correspondence`的离线关联声明；不会把两种不同schema拼成现场授权。

关联材料包括：

- 已封存模拟job的18成员副本：scope/history/namespace、job、authorization、reservation、issue/consumed及durable markers、native context/process/selection声明，以及原entry binding和permit结果。副本中的remaining=0保持；没有再次消费。逻辑/private/tmp路径只作为字符串检查，不沿路径打开旧job。
- 统一supervisor的37份已封存observation/stdout/stderr/material缓存，未重跑这些worker。正常/内部失败材料精确23/25成员，继续执行已有版本、payload/STATUS、epoch/receipt和worker关联校验。
- 外部必须给出expected anchor摘要，绑定job成员字节清单、规范化observation、原始stdout/stderr及材料清单摘要；另有11字段显式correspondence声明，关联job/namespace、entry binding、consumed摘要、SDK binding/receipt/snapshot、supervisor case与observation摘要。

模拟job来自`A23-permit-context-review-20261020-r2`，pin为`5f843197e793bcbcf4ce1f0e3265d052d155eebbcdc2c15080841db9e4e3fda2`；复用原UUID `dde3edc8-7f62-4952-b3b4-a5f4887eb620`。提取前验证原完整缓存中的shared/native/context/supervision关联；新紧凑副本仍独立检查类型、摘要、标记、remaining、声明的context/selection/permit与entry binding。它不是对历史现场来源的重新认证。

57个场景首轮通过：37份统一缓存加20个语义坏件。坏件更新外层anchor后仍拒绝，覆盖scope、authorization BOOL/整数与硬件声明、consumed重新打开、durable marker、context PID、permit stale、selection身份，以及job/consumed/entry/session/descriptor/receipt/snapshot/case/observation关联、same-live-run关系升级及额外授权声明。33份缓存可形成一致的跨模型关联，其中只有normal和read-interrupted两份保留`linked_model_completion=true`；其余失败或不完整结果均不提升。所有结果的现场同次运行、来源、生产执行、发行、清理授权、重试和硬件入口标志始终false。

额外测试确认：18个job成员缺失在更新anchor后仍拒绝；11个correspondence字段逐一变更拒绝；remaining=False不被当作整数0。SDK receipt的session被单独替换后，即使重算receipt封存、stdout摘要、correspondence和anchor，仍因它与snapshot/result/epoch不一致而拒绝。

静态接入成果为`work/integration-plan.json`、生成的`collect_a23_supervised_job_review.py`与`work/readonly-adapter.diff`。差异只新增一个只读review入口：读取case目录和外部anchor pin，返回模型关联分析，不调用issue、consume、claimProcess、claimSelection或A23MakeWaitingBoundPermit。差异未应用，现有生产collector/entry/permit文件未改；适配器本身未安装或执行。缺少前置job-to-child绑定、实际来源、fresh build/consumption、真实时钟域、SDK runtime、quiet/drain或生产permit时，不能转成可执行许可。

验证：新增20、统一supervisor回归20及历史permit/context回归16项，共56测试无跳过通过。纯消费者在open/io.open阻断下分析全部57场景，文件打开0；外层提取、计划生成和封存正常读文件。507来源搬移后重新分析57场景、重生成计划/adapter/diff，结果一致；正确/错误/缺失pin的只读CLI返回0/2/2，不launch worker。代码和数据复算过程没有原生编译或SDK模型执行。

负对照仍保留：若把外层close失败观察伪造成内部一致的close成功，再重新声明anchor与关联，纯消费者可以得到模型完成；same_physical_run_verified和production_execution_authorized仍false。external anchor是调用方提供的信任输入，不是签名或现场证明。Python搬移hook阻止原checkout与/Volumes文件打开，不继承到子进程；不宣称OS隔离。该关联也不验证后代回收或物理连续性。

证据：

- review：`private/analysis/A23-supervisor-job-link-review-20261020-r1`
- review SHA256SUMS：`7cfc2caf4011b67fc782785c7fa633e1e2ee5ea771d667f012fa5889e1b3a711`
- validation：`private/analysis/A23-supervisor-job-link-validation-20261020-r1`
- closeout：`private/analysis/A23-supervisor-job-link-closeout-20261020`

只读入口：`tools/audit_a23_supervisor_job_link.py --check <review> --expected-sha256 <pin>`。单case纯关联入口为`read_case(case_directory, expected_anchor_sha256)`；静态adapter只是此入口的未应用CLI包装。外部review pin与case anchor pin是两个不同层级，不能互换。沿用8192节点、64MiB单文件/256MiB总量、深度18和普通非符号链接文件约束。

23项保护文件、实际49/65账本及失败修复owner/state保持；65已回收、remaining0。历史模拟job的81..112声明不代表正式保留，正式namespace仍不存在。USB/SD/真实SDK/driver时钟/context刷新/部署/正式发行与保留均0，生产采集关闭。

下一步准备fixture-only的launch前job绑定声明与launch后结果关联，使一份新的隔离回放能携带自身的job/receipt上下文，而不依赖跨历史模型对应。先明确单次使用、失败保留及外部信任输入，继续禁止真实permit/发行/SDK入口。实际运行来源、时钟域和quiet/drain依旧未认证。

前序：[统一supervisor候选](A23_SUPERVISOR_UNIFIED.md)。

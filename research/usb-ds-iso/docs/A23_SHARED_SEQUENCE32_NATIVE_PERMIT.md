# 共享32序号账本与原生文件许可（2026-10-19）

后续：[只读来源复核器与独立构建](A23_READONLY_SCOPE_VERIFIER.md)完成文件/注入模型验证；正式发行与现场acquire保持关闭，失败最终收集器尚待实现。以下保留共享账本阶段结果。

共享命名空间引擎和独立原生文件permit已完成实现、编译及离线验证。不同作业使用同一占用记录，原生许可绑定正式结构的发行/消费回执、构建与基线scope、进程context及设备选择。23个原生场景、11个共享账本场景、12份坏件及18项检查通过，搬移后独立重编译/重放一致。

当前验证全部采用临时命名空间、合成context和模型permit。生产引擎与生产permit分支已编译/实现，但生产fresh verifier、专用新构建与采集CLI尚未接通；真实预览仍不可发行。没有新建生产32账本、正式发行、消费或保留81..112，也没有启动真实等待器/接收器、访问SDK/USB/SD或构建设备固件。

## 一个共享命名空间，多个作业

新增 `tools/a23_shared_sequence32.py`。namespace.json绑定原始位置、唯一命名空间ID、冻结scope和历史；jobs下每个作业独立UUID、job.json及authorization.json。授权严格绑定scope、作业ID、maximum_invocations=1和simulation模式，字段类型也必须一致。

同一全局.lock保护所有作业的准备、保留和消费。81..112仅用一个block-00081.json，绑定作业路径/ID、job及authorization原始字节摘要和scope，一次占用全部32。作业A保留后，无论后续发行是否成功，作业B都无法接管；占用文件为空、部分或完整均不自动释放、重写、补发。历史任一半区间重叠都会整体拒绝。

生产命名空间为仓库 `private/sequence-reservations32`，独立于旧16序号账本。模型只能使用/private/tmp子目录；规范路径、原位置、模式和作业结构必须匹配，副本不能继续执行写入。新引擎不会将32 schema塞进旧parser，也不删除或升级旧49/65文件。新生产目录本轮未创建。

scope包括351旧来源加8新来源共359份的摘要、最新69清单/库存、构建/binary、device/recipe和旧账本/记录摘要。每个写入边界重新调用fresh scope检查器，冻结scope不同即拒绝；正式分支还要求formal_issuance_available和acquisition_mode_implemented为true。当前只读scope明确为false，因此正式初始化在创建目录之前拒绝。

## 发行、消费与明确提交

发行持久写入整个32保留，复核scope后写issue.json，再复核并验证回执，最后排他写issue-commit。消费必须见到正确issue-commit；先持久consume-attempt，再写consumed.json、复核并验证，最后写consume-commit。所有写入先持久化排他创建，再写内容、fsync、读回及同步父目录。

空/部分文件、已有attempt、缺commit或材料失效均保持拒绝，没有恢复半成品的API。issue.json/consumed.json落盘而复核未通过时，不产生完成标记，恢复旧scope也不能继续消费或拿原生许可。durable commit是该阶段的提交点，不能仅凭文件存在或旧issue.remaining1判断仍有机会。

消费回执remaining0、receiver_launched=false。文件引擎没有接收器runner，也不启动SDK；永久attempt阻止同一消费再次执行。生产授权将来必须来自新的明确指令及正式核验，合成模型authorization不提供此授权。

## 原生permit桥接

新增 `host/a23_shared_sequence_permit.h/.m`，实现现有 `A23TwoEpochEntryPermit` 接口：

- `A23SharedSequencePermit`只接受固定生产命名空间、simulation=false及已准备好的正式scope。
- `A23SharedSequenceModelPermit`明确接受临时模型及simulation=true，允许合成pid/context；生产类在模型路径上返回nil，未写attempt。

构造与每次声明边界都复核原始JSON、scope、namespace/job/authorization、共享32占用、发行、消费及两个commit。JSON要求规范编码并拒绝重复键；不同模式、路径、作业或摘要不能混用。entry binding中的authorization_receipt_sha256绑定consumed.json原始字节。

`claimProcess`先持久创建native-process-attempt，再核验binding和既有执行环境策略，保存context与进程声明，保存后再次fresh检查。生产分支还要求context.pid等于当前getpid；模型不声称真实pid来源。`claimSelection`只能由同一成功对象继续，一次性标记后核验context完全相同、HS速度和不同的device/interface ID，再保存选择声明并复核。

跨实例/进程靠排他标记阻止重复；同一实例按调用方串行队列使用。内存中保留已确认context、process及selection原始字节，后续读取结果会核对文件与scope。任何已观察到的变化使stale永久为true，process_claimed/selection_claimed随之失效，材料恢复也不会解除。部分保存或保存后fresh失败不返回成功，不能从这些文件构造第二次进程许可。

fresh verifier由调用方提供，必须只读且重新核验当前/冻结构建、最新卡基线、无关历史及授权。这里没有默认生产verifier，也没有把模型lambda或简单BOOL当作真实来源认证。现有原生入口还未将新permit接进生产构建；正式启动前与最终收尾的完整重核验仍需接通。回执摘要一致性不是物理来源或二进制签名认证。

## 联合分析和验证

`tools/analyze_a23_shared_sequence32.py`核验共享占用到原生context/process/selection的完整链、两个提交点、永久attempt和最终文件清单。结论仅为supplied_model_chain_complete；formal_issuance_available、hardware_entry_enabled、hardware_verified、process_origin_authenticated及receiver_launched均false。

11个共享场景包括：两个不同作业跨进程争抢、两个原生进程争抢同一消费回执、空保留、发行失败、保留后scope失效、发行前scope变化、历史漂移、区间重叠、偷用另一作业回执、复制命名空间及两个缺commit场景（两个竞争在同一场景中统计）。两种跨进程竞争均只一个成功者。失败/恢复scope后另一个作业仍不能接管已保留区间。

23个原生场景中正常和跨实例拒绝重放两份完整，其余21份拒绝。覆盖binding/context/sandbox/布尔pid、选择身份、声明前后scope变化、保存后fresh失败、context/process/selection文件被改写、core回执变化、生产类拒绝模型、永久标记碰撞、模式改标、缺少issue/consume commit，以及scope失效后恢复仍保持stale。

12份坏归档覆盖布尔计数、拆为16、错误owner、消费remaining、context/选择pid、过期native结果、模式混用、基线scope、重复JSON键、未知作业文件及部分占用。基线坏件重算namespace/job/授权/占用/发行/消费/原生声明的下游摘要，仍由外部expected scope核验拒绝，避免以旧哈希不符代替该语义检查。

18项专项检查通过；原生文件permit编译使用-Wall/-Wextra/-Werror、AddressSanitizer及UndefinedBehaviorSanitizer。搬移359来源及材料，新进程不读原checkout或/Volumes，提取冻结审查函数重编译原生fixture，重跑23原生/11共享/12坏件；两份完整原生链和各故障分类一致，两种竞争再次各一成功。

本轮代码审查补上了阶段commit：早期成功草稿只核验完整issue/consumed文件，最终版要求明确提交标记，保留早期草稿及设计说明；不将旧草稿用作最终缺commit验证。

- 最终审查：`private/analysis/A23-shared32-review-20261019-r1`。
- 验证：`private/analysis/A23-shared32-validation-20261019-r1`。
- 早期材料：`private/analysis/A23-shared32-draft-materials-20261019`。
- 收尾：`private/analysis/A23-shared32-closeout-20261019`。

## 续接

351旧来源保持，新增8项后359；23保护项、旧49/65记录、旧真实账本含.lock、失败修复owner及状态不变。65仍已回收/remaining0，81..112实际未保留。沿用2026-10-18设备关机/SD弹出记录，本轮未核验现场。

下一项离线实现正式只读fresh verifier，并把新permit、scope和共享消费回执接进独立构建/原生入口及最终收集，补充跨作业无关历史排除和失效材料审查。生产发行、采集CLI、设备双轮包复用、真实SDK映射/trace/URB代际和连续稳定性仍未验证或不可用；继续优先使用编译、文件副本和注入模型。

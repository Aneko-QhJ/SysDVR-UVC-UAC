# A23 缓存来源准入、verifier与静态收集关联（2026-10-20）

后续：[缓存外层取证与完整文件清单边界](A23_CACHED_OUTER_FORENSICS.md)已补齐四份外层原字节，覆盖first capture全部96文件；身份/退出仍为保存声明，现场运行未认证。以下保留原阶段。

本阶段接续[缓存时钟域与模型算术](A23_CACHED_CLOCK_DOMAINS.md)，在同一92文件缓存范围内补齐历史来源准入、verifier报告、最终收集、保存摘要与外层封装的关联。结果分类为 `consistent_cached_static_collection_metadata_subset`，所有完整链、运行来源、实际时限和生产许可字段仍为false。

## 新增校验

- 从已验证构建重建历史准入：392来源及workflow摘要、receiver/supervisor引用、point-in-time限制、单次标记和两份expected scope。当前审查来源增长到434，不能替换历史构建的392。
- verifier报告限定schema、字段和严格布尔/整数类型；检查成功、model roots、未认证binary且未开启硬件。final状态与保存检查点一致，声明的模型调用计数与driver匹配，case与plan对应。
- 最终收集精确核对52份inputs、463257字节、8个目录声明、报告摘要、单次标记和全部成员；stdout/stderr与监督封装保存的字节一致。
- 保存的analysis中shared摘要与既有模型记录对应，entry/SDK摘要中的epoch、URB、有效槽、6144有效字节及quiet区间与缓存子集对应。保存的完整链声明单独记录，不提升本消费者的完整链认证字段。
- 外层封装限定成员、schema、构建引用、成功/退出/完整链声明、报告状态、控制交付及权限位。全部依赖已有构建/session/permit/context/时钟子集先通过。

消费者只接受已固定的 `supplied_static_model` profile。最终收集明确声明 `child_exited=false`、returncode和binary摘要为null；外层 `producer_exited=true` 只表示另一层保存的退出声明。将最终收集连同observation一起改成 `observed_model_child_exit`，即使重算全部封存摘要也会拒绝。这是当前离线profile的支持范围，不是断言观察退出这种模式永远无效。

verifier的33次检查只是报告中的正整数声明。34次的构造模型也可满足本阶段关联，`verifier_execution_authenticated` 和 `verifier_check_count_authenticated` 始终false。未运行原生verifier，也没有从执行轨迹重建调用次数。

## 对抗场景与验证

45个场景：正常、声明检查数变化、同步更新引用的quiet最小值、同步更新引用的队列延迟共4种一致；41种坏件拒绝。40种新语义坏件均通过旧子集校验后被新层拒绝，另1种旧receipt坏件由旧层拒绝。

坏件覆盖准入摘要/计数/权限/scope/标记、verifier失败/类型/来源/额外字段、报告final/calls/case、inputs清单/目录/报告pin/收集标记/流副本、静态模型退出升级、额外成员、保存摘要的包/总量/quiet/权限及外层声明/标记/覆盖。

新增17项测试、旧时钟16项及旧permit/context16项共49项，无跳过通过。434来源完整搬移后45场景字节结果一致；正确/错误/缺失外部pin的只读CLI分别返回0/2/2。

纯消费者审计到的文件打开为0；搬移主重放拒绝原checkout和 `/Volumes` 文件打开，观测为0。三个CLI子进程不继承该Python审计钩子，只确认出口状态和返回值；该检查不证明操作系统能力隔离。

## 封存与恢复

- 审查：`private/analysis/A23-collection-links-review-20261020-r1`，2351清单成员，SHA256SUMS摘要 `f2d3df4f0258bdb695e88061a7a4033b65f3340d957b628d385d0626b6702450`。
- 验证：`private/analysis/A23-collection-links-validation-20261020-r1`，测试日志、搬移结果/脚本、最终化脚本及正常观察记录。
- 收口：`private/analysis/A23-collection-links-closeout-20261020`，源文件摘要、票据/文档前后快照、23保护项、账本和验证引用。
- 父收口：`private/analysis/A23-clock-domains-closeout-20261020`，摘要 `7169ac8aa1f33f4ff288b405b24f73546894520d0c2472ad4b3d81e5f4fdd657`。

已有431来源字节不变，仅新增消费者、audit及测试3份。历史392来源构建、冻结证据、真实49/65、账本、失败修复owner及设备端代码保持。票据仍为65已回收、remaining0、采集关闭；81..112仅为模拟文件里的序号声明，未创建正式32 namespace或保留。

## 未完成范围与下一步

本阶段没有读取原根来证明其新鲜度、原子快照或commit前后未改动；目录仅与缓存contract对应，没有取得真实目录来源证明。原manifest中raw以外的其他外层取证材料未加入92文件语义范围。保存的原分析器没有独立运行，因此 `saved_full_analysis_reproduced=false`。

下一步继续离线审查raw之外的外层取证/worker结果与整体缓存边界，明确可以复现的声明和缺少的独立证据。另可单独准备原生最小等待精确比较及显式时钟域候选，不能修改冻结构建或直接当成部署修复。真实verifier轨迹、进程/时钟来源、现场deadline/quiet/callback drain、完整SDK链、生产permit和操作系统能力隔离仍未认证。

本轮USB、SD、真实SDK对象、原生执行、context刷新、正式发行/保留均为0；未构建固件或修改设备包。

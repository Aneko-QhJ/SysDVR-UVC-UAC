# A23 driver callback、deadline 与 profile 采样故障回放（2026-10-20）

后续：[参与式版本时钟快照候选](A23_VERSIONED_CLOCK_CANDIDATE.md)已独立验证43场景与58测试，参与式ABA被拒绝，但绕过契约仍漏检；完整driver未切换，以下两个原反例保持。

接续[完整driver数值模型](A23_ISOLATED_DRIVER_MODEL.md)，本阶段执行46个新增场景：24个deadline边界、10个profile采样内部变化和12个callback/提交故障。优化、UBSan及462来源搬移重建的结果一致；新增20及旧完整模型20/副本20项，共60测试无跳过通过。生产采集保持关闭。

## 边界结果

完整driver仍使用相同隔离候选，deadline、emit/stop/guard及receipt/result部分没有改动。driver引用的时钟是数值注入对象，owner保持独立计数域，二者无实际映射认证。

| 行为 | 结果 |
| --- | --- |
| callback到达等于control 16ms或ISO 2s上限 | 允许；两轮保存与quiet/receipt完成 |
| 无callback，轮询恰好等于上限 | 超时；ISO缺失时仅abort一次 |
| 2/3比例，轮询距精确阈值还差1 tick | ceil已达上限，保守超时策略保持 |
| 2/3比例，callback到达距精确阈值差1 tick | ceil等于上限，允许 |
| callback在100 tick到达，排队到25000100 tick才处理 | 按到达时间判断，通过；处理延迟不冒充到达延迟 |
| ISO超时后无callback | owner进入CancelPending，保留存储，无第二次abort |
| abort后晚到ISO callback | owner记录一次callback并进入Completed，但未获保存确认的存储仍保留；driver继续终止 |
| 重复ISO/control、外来指针、control错误/多余字节、ISO错误 | 首轮保存前终止；外来指针不解引用并保留原存储 |
| 两轮之间收到旧control callback | 只保存第一轮，不再arm第二轮 |
| early ISO、ISO拒绝或trigger拒绝 | 终止，不重复提交；trigger拒绝可触发一次abort |

每个deadline场景的端点由独立Python Fraction oracle计算。对照的是既有最大时限策略：arrival采用ceil > limit，poll采用ceil >= limit。它与quiet使用精确最短等待属于不同规则，本阶段没有将最大时限改成精确比较。

## profile读取中的变化与ABA反例

在quiet起始或结束的nowTicks内部，分别改变numerator、denominator、domain、instance，共8个场景均拒绝；起点失败不提交quiet_start，终点失败不settled。

另外2个ABA场景在同一次nowTicks内部改变numerator后恢复。fixture记录确实发生过一次变化，但桥的前后profile相同，完整driver仍然完成。这是当前双次读取的明确漏检反例；`profile_mutation_aba_rejected=false`、`profile_reads_atomic=false`，不能据此认证原子快照或底层时钟。

`fault-facts.json` 是fixture诊断sidecar，记录注入比例/端点、变化次数和owner状态。消费者限制字段集合、整数/布尔类型与authority声明，并关联初始profile、quiet事件、最终结果及receipt；已保存epoch还核对原始payload、STATUS、注入标签及bundle摘要。这些检查不认证sidecar来自真实clock，也不证明所有诊断字段的生产语义。owner状态通过fixture中的KVC访问现有数组导出，不新增生产API。

## 隔离与封存

新renderer仅替换模型main并插入FaultClock；与父review比较，所有其他生成文件完全相同，包括driver候选、paired/budget/owner和journal。真实factory与Mach/context实现仍被裁剪；每版执行前检查otool与nm记录，仅链接Foundation及系统运行库。这不是OS能力隔离证明。

首轮r1在编译阶段因旧prefix的pairZero未使用而被-Werror拒绝，没有生成可执行文件或运行模型；r2恢复四个映射数据区的零值检查，保留失败封存。r1/r2及搬移合计10次compiler jobs（9成功、1失败），生成4份模型可执行文件，执行4次46场景模型及4次无参数拒绝入口。

搬移回放的Python审计钩子记录原checkout与/Volumes打开0；编译器和原生子进程不继承钩子。其命令使用搬移输入。正确/错误/缺失pin的只读CLI返回0/2/2，检查入口不执行原生模型。

最终review：`private/analysis/A23-driver-fault-model-review-20261020-r2`，1850成员，摘要 `a9d12c5487edf34b3ac41867c6f970c32a6ab596cfeab7fcc621231d9b6a2fb6`。

失败封存：`private/analysis/A23-driver-fault-model-review-20261020-r1`，498成员，摘要 `e672c426abfba09ac9e3fc1a59263f3f597ff4947b759019c1134a04a41e68b8`。

验证：`private/analysis/A23-driver-fault-model-validation-20261020-r1`。收口：`private/analysis/A23-driver-fault-model-closeout-20261020`。

原457来源、冻结driver、23保护项、真实49/65、账本及失败修复owner保持；仅新增5份离线renderer/audit/fixture/测试来源。65已回收、remaining0；81..112只作为模型数值，未发行或保留。本轮USB/SD/真实SDK对象/实际context刷新/设备包改动均0。

下一步继续离线设计profile与ticks的一次性快照或版本协议，明确所有写入方参与的契约，以本次ABA反例检验；另行增强sidecar诊断字段的消费关联。现场时钟来源、owner/driver域映射、真实SDK runtime、quiet/drain与生产permit仍未认证。

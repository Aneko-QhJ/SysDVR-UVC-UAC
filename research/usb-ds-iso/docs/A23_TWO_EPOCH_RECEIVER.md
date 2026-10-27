# 有限两轮接收协调器与分轮归档（2026-10-18）

后续：[独立两轮SDK资源层](A23_PAIRED_SDK_RESOURCES.md)已编译并以假operations接入本页离线协调器；真实SDK资源仍被本页入口拒绝，SDK执行驱动未接入。以下保留原验证结果。

已新增独立的离线两轮协调器、分轮持久归档及独立分析器。最多两次ISO、两次BURST及一次异步abort；第一轮全部核验并持久保存后，后续一次poll才可准入第二轮。47个原生场景、20份坏归档及10项专项检查通过，搬移后重建与重分析结果保持。

本版只接受 `offlineSimulation=true` 的新资源能力；没有SDK provider、枚举、等待/启动CLI、正式回执发行或序号保留入口。两轮正常结果是离线模拟证据，不表示新硬件测试已准备完成。

## 新增实现

- `host/a23_two_epoch_receiver.h/.m`：独立能力协议及有限两轮状态机。旧SDK adapter、one-shot driver及全部317既有来源保持。
- `tests/a23_two_epoch_receiver_test.m`：一个模拟共享transport、两对实际Foundation存储与47个成功/故障场景。
- `tools/analyze_a23_two_epoch.py`：只依赖Python标准库，重新验证两轮文件、数据、STATUS、时限与事件顺序。
- `tools/audit_a23_two_epoch.py` 与专项测试：冻结输入、原生ASan/UBSan构建、坏归档及历史状态保持检查。

资源能力提供两份184320字节数据区、两份26880字节事务表和一个共享transport。初始化逐对验证四块活跃地址范围不相交，并冻结身份/描述符摘要。两个owner均使用既有的实际one-shot `A23TransactionOwner`，没有复位或重用旧owner。

首次尝试后，会话、共享资源、四块存储、owner及已完成快照保留至进程退出；本版没有destroy、close或“排空已确认”接口。底层owner确认保存后虽然释放自己的存储引用，会话仍持有全部存储。加两轮完整快照至少844800字节，不是进程总内存上限。

## 准入与验证

1. 只启动一次；起始序号仅接受至少81、`first mod16=1`且32序号不溢出的模型范围。本轮仅使用81..96和97..112，未分配这些序号。
2. 第一轮要求完整168字节、全零首次STATUS字段及匹配端点/版本；第二轮重新读取STATUS，要求与第一轮完整after原件一致，读取时间晚于第一轮保存。
3. 每轮重新采样frame，lead32；复用既有runtime guard检查query≤2ms、age≤16ms、enqueue≤8ms，再检查trigger gap≤8ms、总age≤32ms。记录新的采样和预算，不能沿用第一轮时钟。
4. ISO与控制回调入口用原子计数记录首次到达时间，立即标记重复、错误status/字节数、错误事务指针及触发前ISO完成；队列内继续记录原始事件。第二轮ISO/触发及保存前再检查这些标记，包括日志写入期间发生的旧回调。
5. ISO回调恰一次、控制回调恰一次且已被队列观察；校验完整960项事务布局及状态0，恰16个192字节有效槽，按顺序逐字节核对ISO1序号和载荷。有效槽可位于不同位置，原始184320/26880字节全部保存。
6. after要求序号、COMPLETE、post/report结果0、URB/report ID一致、3072请求及传输、URB status3、HS、单report；ISO7终结1/bitmap65535/actual3072，以及有效的MFI/FrameID lead32头。第二轮URB ID必须区别于第一轮。
7. 超时以原生入口时间判断：控制16ms、ISO2s；队列延迟不能独自把及时到达改判为超时。停止后不恢复；最多一次异步abort，abort返回不表示排空。detach不再发abort。

目前只有STATUS中的URB ID和注入服务结果，**没有执行实际HOS URB服务分配/完成，也没有验证设备EXE3/trace**。设备完整日志在未来物理测试后另行关联；当前不会把一个注入的`trace_lossless`布尔值当作已取得原件。第16轮ED地址别名反例仍保留，本版最多两轮，不构成连续流修复。

## 持久归档门禁

每轮排他创建 `epoch-0` / `epoch-1`，保存以下原件：
`raw.bin`、`transactions.bin`、`before.bin`、`after.bin`、`metadata.json`。
每个文件O_EXCL/O_NOFOLLOW创建、fsync、逐字节读回，再写有序SHA256SUMS与COMMITTED，最后同步目录和父目录。失败留下部分目录，不覆盖、不删除、不重试。保存成功事件也必须通过现有持久journal，最后才确认owner并允许下一轮。

关键边界已实测于本机模型：文件已COMMITTED而saved日志失败，或saved写入时收到旧回调，均保留已提交目录，`saved_epochs=0`、ISO仅一次、第二轮被阻止。归档完整与会话可继续是两个独立条件。

独立分析器不信任result中的complete标记；它校验24个正常日志事件的身份、次数、时间及顺序，重算两份manifest/commit、全部数据和STATUS、URB身份、真实预算算术、回调时限及先保存后开始关系。正常模型81..112共6144字节，URB501/502，第一轮有效槽0..15、第二轮120..135。所有hardware/provenance/trace/drain/连续流标志保持false。

## 验证结果与保留项

- 47个原生场景：正常路径1、初始化拒绝5、其余停止41；完整分析仅接受正常路径，拒绝46份其他模型。
- 覆盖身份/描述符/存储错误、STATUS/ISO7/URB/载荷/事务错误、重复及旧代ISO/控制回调、回调指针错误、触发前ISO到达、journal/保存失败、第二轮保存碰撞、两种超时、迟到控制、预算超限、detach及退出。
- 20份坏归档全部拒绝，其中11份已重算manifest、COMMITTED及相关journal摘要，验证语义而非仅哈希失败；含旧序号、重复URB、错误ISO7、二轮before不一致、载荷/事务破坏、预算/时限伪标、跨会话混合、布尔冒充整数和越权声明等。
- 10项专项检查通过；原生构建启用ASan/UBSan、-Wall/-Wextra/-Werror。
- 搬移323份来源和归档后，新进程以冻结的编译命令函数重建47模型，重算正常链及20份坏件。正式Python重放阶段未读取原工作区或/Volumes；编译器使用搬移来源和系统SDK。没有声称所有历史导入依赖已可搬移。
- 317旧来源逐字节保持，新增6项后323；23保护文件、故障修复owner和失败状态保持。首次编译失败日志与45场景中间审查r1保留，最终以47场景r2为准。

最终审查：`private/analysis/A23-two-epoch-review-20261018-r2`。
验证：`private/analysis/A23-two-epoch-validation-20261018-r1`。
收尾：`private/analysis/A23-two-epoch-closeout-20261018`。

## 现场状态与下一项

本轮真实USB/SD/SDK对象、固件构建、发行及序号保留均0。65..80已永久保留且消费，仍为已回收、remaining0；SD沿用14:41:59+08已安全弹出状态，设备已关机。81..112仅模拟数值。

最新69原件的快照摘要及inventory已绑定进离线计划；没有把它宣称为可正式发行的新69基线回执，也未修改旧63流程。当前硬件接收器和计划仍为一次。

下一项离线实现并审查独立SDK两轮资源provider/映射分配能力、执行驱动及明确生命周期；随后准备专用build/receipt/collector与最新69基线、原子32序号保留流程。不得把本版offlineSimulation检查改成一个开关直接实测。完整设备URB代际、SDK映射、设备包复用和硬件连续稳定性仍待验证；新硬件测试另需明确指令与现场状态。

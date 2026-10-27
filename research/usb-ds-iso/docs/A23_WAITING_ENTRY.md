# A23隔离等待入口与SDK启动分离（2026-10-15）

后续实施见[等待接收器构建与启动门禁](A23_WAITING_RECEIVER.md)：新main及完整构建/
消费门禁已接入并离线核验，75项相关回归通过，新记录仍为0。本页保留上一阶段语境。

已把被动等待适配器接入新的隔离入口组件，拆开SDK准备与传输启动，并接入持久日志和
独立的单次文件许可检查器。32组完整入口注入场景、14项新增检查与此前44项相关回归
全部通过，0跳过。真实IOKit绑定及SDK实现仅参与编译链接；未执行真实IOKit/SDK、USB、
SD或设备部署。旧接收器/采集工作流保持原样，新组件还没有可用的真实采集启动器。

本轮没有取得新的实机故障证据，首次SDK burst超时根因仍未知；三份实时票据均为0。

## 新入口的执行顺序

[a23_waiting_burst_entry.h](../host/a23_waiting_burst_entry.h)与
[实现](../host/a23_waiting_burst_entry.m)复用原SDK provider、transport和coordinator。
所有入口方法、等待回调、日志及资源交接在调用者的一条串行队列内执行。组件复制ops表，
调用者须保持ops.context和入口存活至相应关闭/完成阶段。

| 阶段 | 已实现的行为及边界 |
| --- | --- |
| begin/pollWaiting | 日志成功后注册并排空；拒绝已存在或模糊实例，不自动改选；尚不打开SDK |
| take | 排空当前消息并复核身份，最多一次借用service交接；过早调用prepare会停止该入口 |
| claim | 独立文件许可先核销；失败、中断或日志回执失败均阻止SDK打开 |
| SDK准备 | provider先retain独立service引用、安装SDK自己的interest观察，再取描述符、pipe及缓冲区 |
| 关闭等待器 | 再处理准备期间积压的通知；在回调之外关闭通知端口，释放interest/iterator/借用引用 |
| 构造coordinator | 只在关闭、零释放失败及日志回执成功后进行；复核资源的interface/device/parent身份 |
| startPrepared | 另一次显式调用；启动前再次检查退出/断开及日志，随后沿用原STATUS→ISO→BURST流程 |
| 启动后 | 不再pump等待消息；未完成I/O交给原协调器保留、等待和报告，不提前销毁SDK资源 |

SDK准备本身可能触发GET_DESCRIPTOR，因此许可必须先于provider.openCandidate，不能等到
STATUS/BURST前才核销。正常交接时，两份service引用各自有持有者：关闭等待器只释放其
借用引用，SDK引用一直保留至SDK interface销毁。释放失败的token和原生错误继续记录，
closed不能替代“全部引用释放成功”。原SDK队列上的断开消息仍需由调用者接回新入口；
组件不承诺在真实异步通知与同步SDK调用间消除所有竞态。

原SDK计划的16ms控制期限、ISO/退出预算及最多一次提交/触发/abort保持。断开后不再向
已断设备abort；ISO已完成但控制回调未到的场景也不需要abort。两者仍保留未完成资源。

## 文件许可、日志和独立核对

新许可仅接受`waiting-authorization.json`的独立schema/backend、固定且类型严格的完整
计划、接收器文件SHA256、预期build manifest/recipe与UUID。旧SDK receipt不适用。
`WAIT_RECEIVER_CLAIMED`独占创建并fsync/读回，记录receipt摘要及所选身份；已有文件、
写入或持久化失败均不删除标记、不重试。即使核销后的日志失败，也不会重新打开SDK。

**该检查器只核验调用者提供的预期摘要和已消费receipt。完整构建/当前源校验及票据消费
仍须由未来的新启动门禁完成，当前没有签发器或真实采集CLI。** 本轮的文件许可样例都在
明确标注的注入目录或临时目录内生成；没有生成可用于真实硬件的新次数。

新日志写入器独占创建JSONL，每行限4095byte、最多128行，文件和父目录fsync并逐行读回。
等待策略和外层事件统一使用入口clock与timebase，SDK coordinator使用同一clock；
adapter原始ticks仍是最近一次检查值，不能充当物理到达或清理完成时刻。路径校验用
POSIX realpath，与Python冻结清单保持一致，避免Foundation折叠`/private/tmp`的歧义。
前置失败保留SDK NSError的domain/code/阶段等信息；布尔字段严格保持JSON布尔类型。

[独立核对器](../tools/analyze_a23_waiting_entry.py)验证事件顺序、唯一身份、等待期限、
关闭条件、SDK binding/timebase，以及SDK准备/控制事件相对交接日志的先后关系；随后
复用原SDK材料分析器。文件中出现一行并不能证明调用者收到持久回执，核对器明确保留
`journal_acknowledgement_verified=false`、构建源未认证、物理同run未认证及USB权限false。

EXE3收集器已验证会原样保留新等待日志和结果，冻结后可单独再核对；现有collector尚未
把新核对结果纳入其主分析结果。它仍不把模型EXE3与主机记录认作同一次物理运行。

## 验证与封存

[审查工具](../tools/audit_a23_waiting_entry.py)先冻结源码，再从冻结树严格编译12个原生
单元，链接实际等待adapter、IOKit绑定及原SDK代码，ASan/UBSan下运行
[注入fixture](../tests/a23_waiting_burst_entry_fixture.m)。32组包括正常和文件许可路径、
旧实例/模糊选择、许可拒绝、核销后中断、SDK打开失败/中断、准备期间新到达、三份释放
失败引用、准备后退出/断开、启动日志中断、迟到通知、未完成ISO/控制与各日志阶段失败。

[14项新增检查](../tests/test_a23_waiting_entry.py)还覆盖18类损坏/旧版/类型错误/符号链接
receipt、重复核销和既有失败标记；篡改事件顺序、身份、binding、计划、timebase、布尔/计数
及部分/重复JSON均被拒绝。新旧相关回归共58项通过，0失败、0错误、0跳过。
源码闭包显式包含a23的C/header以及SDK依赖，弥补旧工作流只选io_usb_host文件的缺口；
这次冻结不表示未来启动器已会校验该闭包，也不等于冻结了全部系统框架运行环境。

- 审查：`private/analysis/A23-waiting-entry-review-20261015`，98份源码、334条manifest；
  manifest SHA256：`d684c3c9a016e387f1dddd0c9d57a8bc59ed3d1021d8887f4949655bc3f88c10`。
- 验证：`private/analysis/A23-waiting-entry-validation-20261015`，9条manifest，含58项日志。
- 复核旧主机对接257/验证9、V3候选504/验证9和原失败run17条全部一致；此前60份输入、
  七份生产源及三份实时票据的摘要保持。未改原接收器、设备候选、旧工作流或sealed材料。

## 下一步

1. 完善新接收器的隔离构建/描述入口和构建源校验门禁，再接单次消费、信号退出及未完成
   I/O的进程保留；原失败票据不能复用，准备阶段仍只产生remaining=0的候选材料。
2. 将等待核对结果纳入EXE3收集的新封装，继续保留失败原字节、回执失败与物理来源限制。
3. 回到V3诊断实际可达线程、TLS/reent、栈及日志错误/重入成本，形成一次有区分力的诊断
   方案。不能用当前电脑验证外推USB通过、设备运行成本已满足或原根因已确认。

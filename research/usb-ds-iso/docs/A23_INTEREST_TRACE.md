# Interest通知路径与最小留证候选（2026-10-24）

后续集成：[当前103件诊断候选](A23_LIVE103_INTEREST_READY.md)已编译封存，含准备期与关机确认后的失败留证，等待新单次授权和现场就绪确认。下文保留此前隔离阶段历史。

审查确认：当前SDK interest handler是generalInterest，不能将`interest_seen=true`等同于设备终止或sysmodule崩溃。真实Triple provider对任何message都会立即置`arrived`，随后异步pin；`preparationHealthy`据此失败，driver报`paired_resource_fault`。入口仅对termination显式requestExit，并不意味着其他通知会被忽略。先看到driver资源故障、后看到entry退出，也不能排除termination，因为故障标志与队列回调是两个观察边界。

本次177..224失败没有保存消息类型，不能恢复它或用设备30秒正常到期补作通知原因。此次仅新增隔离的原始message/入口tick记录，保持任意interest都停止；没有放宽lease健康条件、延长设备窗口或追加实机。

## 实际绑定与本地SDK依据

核对的是实测build的`generated/live_adapter.m`和`generated/live_main.m`，并与623来源内的paired adapter/入口生成链一致性核验。实际SDK操作在内部interest队列直接调用provider回调；provider先原子置故障标志，再向IO串行队列派发pin和用户回调。旧SDK层丢弃`hostObject`和`messageArgument`，provider最终只留下布尔值。

本机SDK四份头文件已连同SHA256封存，依据限于此SDK版本：

| 入口或消息 | 头文件给出的语义 | 对本次失败的意义 |
| --- | --- | --- |
| IOUSBHostObject interestHandler | generalInterest，在独立于IO队列的内部串行队列服务，termination只是其中一种状态变化 | 布尔标志不能区分通知种类 |
| `kIOMessageServiceIsTerminated` / `0xe0000010` | 通用服务终止消息 | 可能种类之一，本次没有保存类型 |
| `kUSBHostMessageConfigurationSet` / `0xe0005000` | setConfiguration相关消息 | 同样会被当前provider停止，不等于本次收到它 |
| `kUSBHostMessageDeviceIsRequestingClose` / `0xe0005003` | 新客户端尝试seize设备服务，要求当前所有者关闭；SDK说明message包括请求服务的registry ID | 提供另一类可区分假说，不证明本次有其他客户端抢占 |

SDK定义的DeviceCapture/Seize/Surrender有各自条件；本候选保持原InitOptionsNone，不添加capture、seize、surrender、reset或销毁操作。消息码与IOReturn错误码可能数值重叠，应按它来自interest回调这一事实解释，不能只按十六进制套用USB错误名称。

## 隔离实现

新增5来源，总628，原623保持：`host/a23_interest_trace.h`、`tools/a23_interest_trace_candidate.py`、`tools/audit_a23_interest_trace.py`、`tests/a23_interest_trace_fixture.inc`、`tests/test_a23_interest_trace.py`。

每个provider信号对象内置固定8条记录。原故障标志仍首先置位；随后记录原始uint32 message和`mach_absolute_time` tick，再派发原异步pin。入口不分配动态内存、不写日志或文件、不调用USB。结果getter在原IO队列将已提交记录转成JSON，已有driver/失败快照可携带lease字段；旧实测程序和部署均不改。

行只写一次，用release提交/acquire读取；最多8条，CAS尝试次数有界，满后只置overflow、不绕回覆盖。claim、commit、pending分别报告，不编造未提交行。故障已置位但尚未取得记录槽的窗口显式为`latch_without_slot=true`、complete=false；有槽未提交同样不完整。9个并发写者的超容量安排全部join，结果显式overflow。

`complete`只描述本次观察前缀的槽提交状态，既不证明原子快照，也不排除getter之后的新事件。不同getter字段也不是同一原子观察。reservation ordinal不是并发事件的真实到达全序；入口tick是provider回调中的观察，不是内核发出通知的时刻。原SDK对象/参数仍未采集，字段`argument_captured=false`保持；不能据此认证发送者、请求registry ID或物理来源。

新增观察也会改变回调中的时序，因此不能称为零开销或与旧代码完全等价；不把模型时序当作实机结论。记录失败、pending或overflow不会解除原停止保护；诊断不足时保持不可判定。

## 验证

最终8个原生进程均exit0并由创建者直接wait，ASan/UBSan stderr为空；6项专项检查通过。仅链接SDK类型，使用注入操作，没有真实SDK对象、USB、SD、新授权或正式范围操作。

- 无通知正常三轮完成；终止、请求关闭、配置、未知`0xffffffff`和零值都按原策略在第三轮前停止，保存各自原始值和非零入口tick。
- 10个通知显式overflow，最多保存8条，不覆盖旧行，不提交第三轮。
- 独立契约安排分别观察故障先于槽、槽先于提交，以及9线程并发；未提交数据不作为完整空记录或有效行返回。
- 旧623来源、25保护项、81/113/145/177四个namespace及本次actual177记录均保持。旧三轮失败不升级为成功。

开发r1因未使用的fixture辅助函数触发Werror，编译失败；补上准备存储检查后r2的8个原生场景通过，但封存SDK头文件时因SDK路径含符号链接被原文件守卫拒绝。改为解析到实际SDK路径后r3通过。r4额外明确故障先于槽的留证窗口，最终8场景/6项检查通过。全部版本保留，r2不追认为完整审查通过；共4编译作业、24fixture进程及27个测试线程均由创建者wait/join。

## 后续边界

当前只是从冻结三轮adapter派生的隔离留证候选，没有当前103件现场scope或新正式入口构建，不可实测。下一项将这项最小观察接入103件基线、628及必要新增来源、完整49..224消费历史和新的有界范围，核对失败快照/收集器仍保存并解释这些字段后，才形成新候选并取得新单次授权。

新实验先回答“实际是哪类interest、何时进入provider，以及资源保护在什么边界观察到它”。若得到request-close或配置类消息，再按其实际语义研究参数/发起方和处理策略；不预先忽略通知。已消费177..224不补轮、不重试，SD已弹出，旧97件build只可归档验证。

材料：`private/analysis/A23-interest-trace-review-20261024-r4`（manifest SHA256 `2715bb67735eff72db9a15e8251cbb2e699b9a98244508262800e4b40c69771a`）；专项验证在`A23-interest-trace-validation-20261024-r1`。SDK原件、副本来源摘要、开发失败版本及最终交接索引见`A23-interest-trace-closeout-20261024`。

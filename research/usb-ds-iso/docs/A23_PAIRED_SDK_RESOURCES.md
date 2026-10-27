# 两轮SDK资源能力与离线验证（2026-10-18）

后续：[独立SDK两轮驱动与联合回执](A23_TWO_EPOCH_SDK_DRIVER.md)已完成编译和假operations验证；真实映射/双轮未测，旧离线协调器保持拒绝SDK资源。以下为本阶段历史结果。

独立的两轮资源provider已实现并完成离线审查：一次准备、同一接口和pipe、四块独立存储、运行后保留资源。真实SDK API代码已编译；本轮用Foundation及注入operations替代真实客户端、映射和USB访问。没有写卡、部署、序号保留或新实测。

40个准备场景、23个运行场景、12份坏回执和11项专项检查通过ASan/UBSan；搬移后重建及重分析一致。正常模型两轮81..112共6144字节；SDK映射和真实双轮行为仍未验证。

## 能力与准备路径

新增 `host/a23_paired_sdk_adapter.h/.m`，旧323项来源不改。

`A23PairedSimulationProvider`只接受simulation operations；独立的`A23PairedSDKProvider`只接受非simulation operations。模式不符时在retain/查询/open前拒绝。每个provider仅一次准备调用，包括失败，不自动重试。

调用方提供借用service token及HS身份。新资源层依次执行：

1. 校验非布尔、非浮点、正uint32 token，device/interface/parent关系及HS速度。
2. retain一次；open前、open后、四次分配后三次核对身份，拒绝中途变更。
3. 校验实际descriptor及端点83/MPS256/bInterval1，复制pipe一次。
4. 按data0/table0/data1/table1顺序分配184320/26880/184320/26880字节，table请求KernelUserShared，其余为None；检查可变对象、长度及全部活跃地址范围不相交，再清零。
5. 未开始运行且没有通知/不确定性时，准备失败或显式`closeUnused`按一次destroy/release清理。进入STATUS/frame/ISO/BURST后，`closeUnused`仅拒绝，保留接口、pipe、服务引用及存储，不声称排空。

通知在新SDK interest回调入口立即原子记录，队列内再更新状态和通知调用方。准备期间出现通知或operations模式变化，保留已返回的部分分配（包括失败步骤返回的对象）、接口与引用。模型在open、第三次分配、最终身份核对和模式变化处分别保留0/3/4/2块存储，均不destroy/release。

SDK实现继承现有引用/身份查询，新增独立interface包装。7个descriptor/pipe/allocate/STATUS/frame/destroy方法体逐字节绑定旧adapter；BURST改为经过lease限制的scope值，仍为41/54/value/index2/length0、SDK timeout0.016秒。descriptor访问可能发出GET_DESCRIPTOR，**真实准备不是只读USB操作**；本轮没有调用真实准备。

## 运行时约束与现有协调器

资源层最多2次ISO/BURST、4次STATUS、2次frame和1次异步abort；ISO必须匹配本轮存储、960事务初始化、端点接口能力及串行顺序。第二轮前要求第一轮ISO/控制回调各恰一次且成功；回调入口拒绝重复、错误status、错误指针和触发前ISO完成。通知、模式变化、存储地址/长度变化、错误顺序和额外调用均阻止后续请求。

资源层不验证“第一轮证据已持久保存”。该门禁仍由上一轮未改动的`A23TwoEpochReceiver`负责：完整数据/STATUS/URB/ISO7核验，fsync/读回/持久journal通过后才开始下一轮。因此资源结果中的`continuation_save_verified=false`保持，不能把回调完成当成保存回执。

模拟provider输出已接入原协调器完成双轮归档。SDK provider输出明确为`offlineSimulation=false`，原协调器在任何请求前拒绝；没有把SDK观测重新标为mock。本轮非simulation分支由假operations检查，未创建`IOUSBHostInterface`或真实映射对象。

实际SDK执行驱动、其专用回执及收集格式尚待接入；本次没有现场执行/枚举/等待CLI或正式发行入口。运行后的引用与存储保留至进程结束；即使两轮回调完成也没有active destroy或强制排空方法。

## 发现并修正的具体问题

- `error=NULL`：初稿只在调用者要求NSError时检查错误，导致“retain返回YES但附带NSError”被发布。现在准备及异步提交均内部接收NSError，再向外转交；模型即使传NULL也拒绝并清理准备资源。
- `closeUnused`：初稿把运行中拒绝关闭也标为异常，正常路径提前停止。现在无损拒绝这类关闭探测，已有异常仍保持；接口和引用不释放。
- 真正地址重叠：Foundation no-copy工厂在请求mutableBytes时可获得独立存储，初始故障件并没有重叠。改用固定backing的NSMutableData子类，断言实际指针偏移，再证明部分重叠被拒绝。
- SDK事务struct是packed，类型alignment为1。保留真实SDK头定义，不把偏移1的固定视图误称为违反ABI；该模型可准备，但不证明SDK实际接受此种映射。
- 严格布尔：初稿将逻辑表达式编码为整数0/1，独立分析器拒绝正常资源回执。修正BOOL编码，保留布尔冒充计数的拒绝检查。

失败语法/断言/初始数值布尔材料均已独立封存；没有改变旧封存材料来令测试通过。

## 联合回执与验证

新增标准库分析器 `tools/analyze_a23_paired_resources.py`，同时核验`paired-result.json`中的资源状态与旧两轮完整归档。除旧载荷/URB/ISO7/时限/保存顺序外，要求一次pipe复制、四次模拟分配、引用和四存储保留、回调各[1,1]、计数上限、无通知/异常/destroy及正确模式。

一个具体反例是：协调器两轮已完成后，直接对资源层尝试第三次ISO或额外STATUS，协调器自己的complete仍为true，但资源层已异常。新联合分析拒绝这两种结果；不能仅凭上层complete宣称整条链完整。

准备矩阵40场景：3个可准备并安全关闭的模型（含SDK模式假operations及packed视图），37个拒绝/保留场景。运行矩阵23场景：仅正常路径获离线完整链，其余22个拒绝，含SDK资源被旧离线协调器拒绝。12份坏回执覆盖异常标志、SDK模式、引用丢失、destroy、分配/pipe/回调/STATUS计数、布尔计数、上下层结果不一致及越权保存/硬件声明。

原生编译采用-Wall/-Wextra/-Werror、ASan及UBSan；11项专项检查通过。搬移329份代码和审查材料，新进程从冻结来源提取同一fixture/编译函数，重建40+23模型并重算12坏件，结果一致。正式Python重放阶段原工作区及/Volumes读取0；原生编译使用搬移来源和本机SDK。

最终审查：`private/analysis/A23-paired-sdk-review-20261018-r1`。
验证：`private/analysis/A23-paired-sdk-validation-20261018-r1`。
失败材料：`private/analysis/A23-paired-sdk-draft-failures-20261018`。
收尾：`private/analysis/A23-paired-sdk-closeout-20261018`。

## 续接状态

323旧来源保持，新增6项后329；23保护项、旧49/65记录、65..80保留和故障修复owner/失败状态保持。真实USB/SD/SDK客户端/映射、固件构建、正式发行及序号保留均0。沿用上次确认的设备关机、SD于14:41:59+08安全弹出记录，本轮没有现场核验。65仍已消费并回收、remaining0；81..112未保留，仅为模型值。

下一步离线实现独立SDK两轮执行驱动、入口时间/预算/保存门禁和联合回执；再准备专用build/receipt/collector、最新69基线与原子32序号保留流程。继续优先使用编译和注入模型替代现场操作。完整设备trace/URB服务、真实映射、设备包复用和连续稳定性仍未验证；真实测试另需明确指令及现场状态。

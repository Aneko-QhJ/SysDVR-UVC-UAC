# IOUSBHost 单次 burst SDK 适配与离线验证（2026-10-13）

本文记录08:19的能力层阶段；后续协调器与独立主机格式已在[电脑复核](IOUSBHOST_BURST_SDK_COORDINATOR.md)完成，采集入口仍未开放。

独立 SDK burst capability adapter 已实现并严格编译通过。33 个新注入场景和47个原有适配场景
通过 ASan/UBSan；171 项 Python 回归通过、0跳过。没有实例化真实SDK设备对象、访问registry、
发USB请求或访问SD。本次冻结目录：`private/analysis/A23-IOUSBHost-burst-sdk-adapter-20261013-081956`。

## 实际代码路径

`host/io_usb_host_burst_sdk_transport.h/.m` 新增 A23DormantBurstSDKTransport。
它复用 A23AdapterSDKProvider 已验证并持有的 interface lease：retain service→前身份→open→
后身份→当前SDK描述符/EP83→184320byte data和26880byte共享transaction分配。
模块再次检查身份关系、描述符/active alt0与存储，使用这两块SDK存储构造原有transaction owner，
不拿普通NSMutableData代替真实映射。模块自身不枚举或打开service。

SDK接口新增独立固定能力 enqueueSequenceOneBurst，仅接受准备后的SDK-role lease。
实际编译的调用是 enqueueDeviceRequest，tuple固定41/54/1/2/0、data:nil、completionTimeout:0.016。
lease和transport各自限制一次尝试，SDK拒绝入队也消耗唯一能力；不会重发或发设备cancel/reset/seize。
旧no-TD driver不调用此能力，max_device_triggers仍0；本轮重新编译了当前无TD接收器并验证
describe不变，未知capture/repeat或缺少consumed receipt均在设备访问前exit2。

| 适配条件 | 实现 |
| --- | --- |
| before原文 | sdk_control_reply、固定STATUS tuple、accepted为真正BOOL、无NSError、count/长度均168、fresh IDLE；begin不早于准备时刻，end不晚于当前时钟 |
| frame | sdk_frame_number、有效uint64及frame_time、begin在before之后、end不晚于当前时钟；currentFrame+64无溢出 |
| ISO | 对应lease原始buffer地址、960行初始化、request192/offset/options0；SDK预算query≤2ms、age≤16ms、enqueue≤8ms，owner仅提交一次 |
| trigger | durable intent之后重查预算、身份断开状态、owner状态和callback入口原子标记；gap≤8ms、age+请求timeout≤48ms |
| callback | ISO/控制分别在入口记录mach arrival，异步投递到串行队列；完整32bit IOReturn、byte count、NSError domain/code/文本保存 |
| after | 必须自己的ISO完成且control已经完成处理；控制Pending时不发同步STATUS，避免阻塞回调队列；只读一次、保留短/溢出计数及错误 |
| close | ISO完成或入队拒绝，精确owner证据已被调用方保存/读回并ack；已发控制必须完成；accepted ISO须已尝试after，已断开时可跳过不可执行的STATUS |

before/frame只记录调用方提供的SDK观察，不能把source字符串当作来源认证。
后续实机协调器必须从同一个lease读取并绑定这些原文与身份。本轮测试使用明确标记的
SDKFixtureOperations/Interface，仿真SDK形状的回复来源；不调用A23DormantSDKOperations的registry/open方法。
这些注入输出不是hardware采集证据。

资源未知时保持持有：陌生ISO指针、没有自己callback、abort拒绝、保存失败、journal失败不强制关闭。
提交后模块自持有，直到安全关闭；异步host abort最多一次，断开不abort，已到达ISO completion不abort。
未开始I/O的Prepared关闭会先丢弃owner再销毁SDK映射；提交后的存储由owner ack决定释放。
closeAfterOwnerAcknowledged依赖现有owner的调用方契约，不自行声称文件已commit或DMA已排空。

## 验证范围

33个SDK-role注入场景覆盖ISO/控制两种顺序、同步控制完成、control仍Pending、入队拒绝、
accepted附带NSError、控制错误/非零字节、陌生指针、无callback、abort拒绝、断开、保存失败，
以及短/错误/溢出STATUS、旧或未来的观察时刻、错误来源/BOOL类型、触发意图后预算超限/ISO到达、
journal确认失败和重复callback。另检查simulation lease被新模块拒绝、新模块被simulation executor拒绝，
未提交的错误ISO tuple不转发，直接重复使用lease burst能力也不转发。

6项Python集成检查独立读取33份导出journal/result/fixture-calls和保存的模拟core：请求数、
回调/after/close顺序、短回复原文、NSError原始u32、保留资源及策略关闭。正确模拟payload
不能掩盖控制失败；SDK适配事件不能作为既有simulation或no-TD hardware采集格式导入。
原19项准备/引用、10项STATUS/session、18项no-TD原生场景再次通过，验证新增能力没有改变原路径。

冻结包保留首次编译错误和中间30场景输出；最终源码对应build-final-3.log、native-final-3.log及
native-fixtures-final的33场景。中间材料不计新增实机样本。

## 尚未实现的实机入口

模块是可编译的SDK能力层，没有burst硬件协调器、硬件journal/transaction/collection写入格式，
也没有实机凭据创建或capture命令。测试保存的是模拟core，不能调用现有
A23SaveHardwareObservation冒充burst：该函数固定声明no_td，backend为iousbhost-no-td-1。
所有hardware_entry_enabled、hardware_verified、baseline_accepted、allow_next_burst和callback_drain_verified仍false。

下一步可在电脑实现独立burst硬件证据格式、身份/描述符及各请求原文绑定，并接好协调器的
2s ISO截止、控制软件deadline、1s退出等待和失败输出。当前能力层不会自己计时到16ms后取消控制；
control-pending注入场景只验证等待期间的资源持有，未模拟SDK真实超时或证明硬截止。
同步after STATUS仍使用既有3s请求timeout，所以可能在ISO/control完成之后阻塞；它不用于触发预算。

实机才可确认的仍是SDK timeout粒度、USB调度余量、新API burst数据/空槽状态、设备事件关联和DMA排空。
当前stage=no_td_observation_complete_policy_pending、remaining=0；不需要拷文件，没有新部署或放行。

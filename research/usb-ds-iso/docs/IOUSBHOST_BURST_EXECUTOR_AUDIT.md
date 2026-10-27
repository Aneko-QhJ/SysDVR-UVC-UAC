# IOUSBHost 单次 burst 模拟执行器与日志绑定（2026-10-12）

后续10-13已完成[模拟collection设备关系审计](IOUSBHOST_BURST_COLLECTION_AUDIT.md)，
新增合成ISO7/设备日志并接受完成report_count0或1；下文记录10-12初版及其冻结材料。

可注入执行器和独立字节审计已完成。22 个原生模拟场景通过 ASan/UBSan；147 项相关 Python
回归通过，0 跳过。本轮 USB 请求、SD 访问均为 0，没有新增实机次数。
冻结目录：`private/analysis/A23-IOUSBHost-burst-executor-20261012-221304`。

## 已实现的执行路径

`host/io_usb_host_burst_executor.m` 使用现有 transaction owner、预算守卫和证据保存器，
只接收注入的 Mock operations，未接入 SDK 实机 transport，也没有 registry/open/capture 入口。
构造器拒绝 simulationOnly=false；这个标记是接口约束，不能证明任意外部实现的来源。
测试实际使用的 BurstMock 只操作普通 NSMutableData 和模拟回调。

固定一次 960×192 ISO、一次 41/54/1/2/0 控制尝试，最多一次异步 host abort。
before STATUS 由调用方提供；after 只读一次，全部原始字节进入 journal。不自动重试或发设备 cancel。
控制请求显式传入 0.016 秒，但本轮只能检查 Mock 收到该参数，SDK 的超时粒度仍未验证。

callback 入口新增原子到达标记，在 owner 把处理任务投递到串行队列之前置位。
因此同步到达或 trigger_intent 持久化期间已到达的 ISO 回调，可以在最终触发检查中被识别，
即使 owner 的队列处理尚未执行，也不会发起控制或对已到达的完成调用 abort。
最终检查和真正调用之间仍不是与内核完成原子的操作；本轮不能证明线缆触发早于完成。

trigger_intent 先持久化，随后重查时钟、到达标记与 owner 状态，再消耗唯一尝试并调用控制。
ISO 和控制各自完成、分别记录；ISO 完成后 snapshot→after STATUS→保存→读回验核→存储 ack。
interface 的模拟关闭还须等待控制完成。控制在 16ms 软件检查时仍 Pending，只停止和继续持有；
迟到的成功完成允许满足关闭条件，但不会删除 deadline 失败记录。
ISO 缺失、陌生指针、保存失败或 journal 失败不会强制释放；断开不调用 abort。
2s ISO 截止与 1s 退出等待用注入时钟推进验证，没有实际等待或销毁 SDK 对象。

## 独立审计及验证

`tools/analyze_io_usb_host_burst_executor.py` 独立解析 JSONL journal、结果及保存的核心 bundle，
核对固定计划、原始 STATUS 哈希、frame/入队/trigger 预算、控制请求元组、回调计数及完成状态，
再把 snapshot 和 manifest 哈希、callback arrival、overall、firstFrame 与 raw/transactions 绑定。
关闭必须在 core commit 和控制完成之后；结果中的失败原因必须与 journal 一致。
哈希证明这些文件彼此一致，不证明它们来自硬件或排空了 DMA。

| 模拟组 | 观察与判定 |
| --- | --- |
| ISO 先完成、控制先完成、控制同步完成 | 3 个正常模型路径完整通过；关闭在两项完成及保存之后 |
| ISO 同步到达、意图保存时到达、意图后预算超限 | 控制尝试 0，完成到达时不额外 abort |
| ISO/控制入队拒绝、控制错误/非零字节、短 STATUS | 保存可获得的失败证据，不判通过 |
| 控制超时或迟到、重复 ISO/控制 callback | 失败记录保留，成功字节不能清除失败 |
| ISO 不返回、abort 拒绝、断开、陌生指针、保存失败 | 仍持有资源，不强制关闭；断开 abort 0 |
| journal 写入成功但确认失败 | 耐久前缀可供检查，不能据此触发或证明成功关闭 |

新增 10 项 Python 测试检查上述 22 份原生输出，同时故意修改控制元组、预算、snapshot、
原始字节、callback 时刻、关闭顺序、失败记录、计划、布尔类型和 hardware 标记，均拒绝。
CLI 正常模型 exit0，失败模型 exit1，格式错误 exit2。所有分析结果的 hardware_verified、
usb_strict_pass、baseline_accepted、allow_next_burst 和 callback_drain_verified 均为 false。

## 电脑上仍可推进的部分

下一步可实现 single-burst collection 的设备侧独立审计：将完整 A23 启动日志、ISO7 原始字段、
设备 submit/终结及三组控制广播与本轮 host journal 绑定，并用缺失、错序和错误事件的离线样本验证。
当前模型 after 的诊断区为零，不含完整 ISO7，也没有设备日志；device_log_bound 和
hardware_trigger_binding_verified 因而固定 false。

实机 transport、控制 timeout 粒度、USB 调度余量、原生空槽政策及 callback/DMA 排空仍未确认。
当前凭据 stage 仍为 no_td_observation_complete_policy_pending、remaining=0；没有新部署或放行。
之前的无 TD run、读卡 collection、原生语义核验和 burst 草案全部保持原件。

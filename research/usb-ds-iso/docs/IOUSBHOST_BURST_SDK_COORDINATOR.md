# 单次 burst SDK 协调器与主机观察格式（2026-10-13）

后续13:11阶段已完成[独立SDK collection与设备关系](IOUSBHOST_BURST_SDK_COLLECTION.md)，
204项Python检查无跳过；本文以下保存12:04协调器阶段的结果和当时待办。

电脑实现已完成：独立 SDK 单次 burst 协调器、独立 transaction 保存格式、失败/最终
checkpoint 及主机关系审计。34 个新原生注入场景通过 ASan/UBSan，184 项 Python 回归通过、
0 跳过。原有 SDK/STATUS/no-TD/session/保存故障检查通过；当前无 TD 接收器重新编译，
4 项离线入口防护通过。真实 SDK 设备对象、registry、USB、SD 访问均为 0。

冻结目录：`private/analysis/A23-IOUSBHost-burst-coordinator-20261013-120418`。
最终协调器源码对应 `build-final-6.log`、`native-final-6.log`、`native-fixtures-final/`；
Python 环境和完整结果为 `python-environment.json`、`python-full-final.log`。
目录保留中间编译错误、测试失败及较早的 30/32/34 场景输出，均不计实机观察。

## 协调器及截止

`host/io_usb_host_burst_sdk_driver.h/.m` 的 A23DormantBurstSDKDriver 只接受调用方已准备的
SDK lease、串行队列、本地时钟、可信输出目录和 journal。它不枚举、打开 service、创建
采集凭据或提供 CLI。before STATUS 与 frame sample 从同一个 lease 读取；身份、三份缓存
描述符原文及 SHA256、session UUID、固定计划和 timebase 在开始前绑定并落盘。
描述符每份有 1024 byte 上限；不满足要求时构造失败，尚未开始 I/O，lease 仍归调用方。

固定计划为 960×192、lead64、ISO 一次、41/54/1/2/0 触发一次、STATUS 最多两次、
异步 host abort 最多一次；SDK 拒绝也消耗该次能力。没有设备 cancel、重发或 repeat。
之前的 query≤2ms、frame age≤16ms、enqueue≤8ms、触发 gap≤8ms 和 age+请求 timeout≤48ms
检查保持有效。单次 SDK 控制请求仍只请求 completionTimeout:0.016，不能声称硬件按 16ms 截止。

调用方须定期 poll；没有独立后台 timer，也没有进程强制退出逻辑。软件截止为控制 16ms、
ISO 2s，停止后等 1s 保存 retained checkpoint；未知请求继续持有并接受迟到回调。
ISO 和控制都在 SDK 回调入口记录首个 mach arrival，再投递到 owner/协调器队列。
截止判断使用入口时刻，避免队列或磁盘延迟误报；首次 poll 前就迟到的完成也留下失败。
owner 的原始 callback arrival 同时保留，不把 SDK 与 owner 两个时刻混为一项。
触发与 ISO 的协调器起始时刻写入 checkpoint，可独立核算，超时结论不会被迟到成功覆盖。

自己的 ISO 完成后立即保存 core，即使控制仍 Pending；保存成功只 ack owner 的 buffer
引用，SDK lease、interface 和控制请求继续持有。控制完成后才读一次 after STATUS，
随后在 core 已 commit/ack 的条件下关闭。已知断开跳过不可执行的 after，且不发 abort。
陌生 ISO 指针、没有自己的 callback、保存失败、journal 失败或重复 ISO 回调时不强制关闭。
关闭后观察 250ms 才保存 final checkpoint；此时间段不证明 callback drain。

同步 after STATUS 仍使用原有 3s timeout，只在 ISO/control 完成后执行；它可能阻塞队列，
不参与触发预算。请求返回值、完整 32bit IOReturn、NSError domain/code/u32、短回复原文
和 SDK 原始 bytesTransferred 都保留，正确 payload 不能覆盖这些失败。

## 独立格式与审计

| 材料 | 格式与约束 |
| --- | --- |
| session.jsonl | A23-burst-sdk-session-event-1，独立 UUID、顺序、时刻；SDK 事件以原 schema 嵌入，不冒用 simulation/no-TD session |
| transfer/ | A23-burst-hardware-transaction-bundle-1 / iousbhost-single-burst-1；固定 single_burst/seq1，身份及描述符 hash 绑定 |
| core 文件 | 原始 raw.bin 184320 bytes、transactions.bin 26880 bytes、metadata.json、SHA256SUMS、COMMITTED |
| retained/、final/ | A23-burst-sdk-checkpoint-1；checkpoint.json、SHA256SUMS、COMMITTED；分别最多创建一次，失败后不覆盖或重试 |
| 保存纪律 | exclusive/no-follow 创建，fsync、逐字节读回、commit 最后写入；core 全部成功后才 ack 精确 owner，checkpoint 不 ack |

原 A23SaveHardwareObservation 继续固定 no_td 和 iousbhost-no-td-1。新函数
A23SaveBurstHardwareObservation 不改旧格式；默认 simulation 分析器和旧 no-TD hardware
分析器都拒绝新 core，必须显式选择 burst。新格式记录 SDK 形状的观察，不认证来源。
当前全部测试使用 SDKFixtureOperations 注入；MOCK_ONLY 和 fixture-calls 明确标记模拟来源，
未实例化 A23DormantSDKOperations。文件中的 execution_mode=hardware 是独立格式声明，
不能把这些注入输出算作新的实机样本。

`tools/analyze_io_usb_host_burst_sdk.py` 独立检查 descriptor/hash、固定计划与 budget、
session/core/checkpoint 身份、STATUS 原文及 tuple、SDK/owner callback 原始时刻、请求和
回调次数、保存/ack/after/close 顺序及截止失败。重新计算 hash 后的错身份、错 frame、错
回调、错请求、布尔冒充计数、失败抹除和策略重标记仍被拒绝。journal 失败只能审计保存的
前缀，host_binding_verified=false；缺失/损坏 checkpoint 拒绝。

34 份新注入输出只有 5 条正常主机路径 host_observation_complete=true：ISO 先完成、
控制先完成、inline 控制完成、控制队列延迟、ISO 队列延迟。控制 Pending 时 core 已 commit
但 interface 未关闭；控制/ISO 超时后迟到可另存 final，仍 exit1。实测注入回调延迟 20ms/2.01s
即使此前未 poll 也保留截止失败。SDK timeout 粒度没有由这些软件注入测试得到验证。

13 项新增 Python 检查及既有 171 项回归无跳过；既有 33 项 SDK transport 场景重新执行，
47 项 SDK/STATUS/no-TD 场景、16 项 session、18 项 no-TD driver 和 6 项保存场景均通过
ASan/UBSan。保存检查包括中途写失败、同名目录和 symlink 拒绝，失败时 owner 继续持有。

## 下一步与实机缺口

本轮只完成主机观察格式及协调器；尚无独立 SDK burst 硬件 collection、完整 A23 日志/ISO7/
三组控制广播的跨设备绑定、单次凭据工作流或 capture 入口。已有模拟 collection 的关系规则
可复用，但不能直接把硬件形状的 SDK 输出改名后导入模拟格式。

下一步可继续在电脑实现独立 SDK burst collection 和设备关系审计，再审查单次入口及凭据。
真实 SDK timeout 粒度、USB 调度余量、有效包/空槽原生状态、设备终结关联和 DMA 排空仍需实机。
stage 保持 no_td_observation_complete_policy_pending，remaining=0；baseline_accepted、
allow_next_burst、hardware_verified、usb_strict_pass、callback_drain_verified 和 burst capture
entry 全部保持 false。没有新部署，本轮不需要拷文件或连接 Switch。

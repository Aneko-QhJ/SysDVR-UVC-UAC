# A23有界内存trace原型（2026-10-13）

后续已完成[实际handler隔离候选](A23_EP0_HANDLER_CANDIDATE.md)：48项源码回放、完整libnx
ELF、账本封装与266项回归。下文保留本原型阶段的验证范围；没有新增实机结果。

电脑原型已实现：固定128条记录，满时保留原记录并饱和计数丢弃，freeze后不可修改；
内存导出包含长度、身份、时基、记录/头部CRC32，独立Python解码。原型插入A23真实
客户端源码的临时副本，25个回放场景与插入前的模拟服务调用结果一致；设备架构编译
通过。当前生产源码、部署NSP/IPS、USB协议、timeout和采集凭据均未改动，USB/SD访问0。

记录已能分开[HOS共享SETUP审查](A23_HOS_SHARED_SETUP_AUDIT.md)的覆盖候选、GetSpeed
早退、ISO post失败及ACK等待/报告/解析失败。它尚未部署，不能据此确认实机根因或
测量实际trace开销。旧32轮serial成功、首次SDK burst失败及remaining0保持。

## 核心与生命周期

- `device/ep0_trace.h`：标准C11、单一owner线程、调用方零初始化存储；没有SDK、时钟读取、
  malloc、锁、USB或文件操作。调用方提供tick和boot/session各16byte标识，必须非零。
- 只能从未初始化进入recording，再freeze；没有原地reset或覆盖旧session的接口。
  初始化/冻结参数错误会拒绝。每个新session使用新的零初始化存储。
- 每条48bytes，记录数最多128。满后不滚动覆盖，dropped饱和到UINT32_MAX。无效记录
  增加invalid；最后一次有效观察的end tick即使因容量丢弃也推进freeze时间下界。
- 所有接口非阻塞eventWait均计数，4个uint16计数饱和时表示“至少65535次”；最后一次
  Result完整保留32bits。未就绪轮询不占记录槽。未保留每次未就绪的耗时及完整返回码历史。
- freeze之后append/poll/re-freeze均拒绝，存储逐字节不变；export可重复得到相同字节。
  live状态或输出buffer太短返回0且不修改输出buffer。导出必须在owner停止记录后进行，
  不允许另一线程边写边读。本原型没有实现多线程同步或自动quiescence判定。

记录器热路径只做有界内存操作；CRC计算和序列化在freeze后的export中执行。
文件写入只存在于离线fixture，在所有客户端模拟服务调用和断言完成后执行。
CRC检查损坏，不认证来源；boot/session标识同样由调用方提供。当前wire固定simulation
标记，解码结果hardware_verified/root_cause_confirmed永远false，没有硬件格式放行入口。

## 记录阶段与数据有效性

| 阶段 | 保留内容 |
| --- | --- |
| event_ready / event_clear | 接口、独立递增request_id、操作前后tick、原Result |
| setup_read | GetSetup前后tick和Result；成功时保留实际8byte，失败时不读取未初始化buffer |
| iso_enter | 实际setup、进入时state和seq |
| speed / guard | GetSpeed结果及成功时的speed；目标接口/忙状态/速度/非HS早退原因 |
| sequence / iso_post | seq写入后的值；post前后tick、长度、Result及成功时URB |
| ctrl_clear_pre / ctrl_post / ctrl_wait | IN/OUT方向、clear及post/wait分阶段Result，长度或URB |
| ctrl_clear_done / ctrl_report / ctrl_parse | 完成事件clear、取报告、解析自己的URB分阶段结果；成功解析的actual |
| ack | 原_ctrlAck整体跨度及内部IN阶段最终Result，原有stall行为保留 |
| status_snapshot | STATUS写入前state/seq；不把这两项代替原168byte主机回复证据 |
| device_state | 断开分支中的状态及当前seq；不隐式清除seq或重置trace |

arg0/arg1与setup都有valid位。速度失败不保存未初始化speed；post失败不声称URB有效；
解析失败不声称actual有效。ACK整体跨度包含内部操作，因此begin可以早于前一条记录的
begin；end必须单调且不超过freeze，不能按所有begin严格单调拒绝合法嵌套跨度。
request_id表示一次客户端服务，不表示总线请求号，也不把0/1广播当成两个总线BURST。

不存在接口2event记录时，poll_count>0说明它曾被检查，last_result保留最后一次观察。
它不能定位所有未就绪时刻，也不能单靠缺少记录证明HOS丢弃了请求。记录满/invalid、
stopped或服务阶段不完整时，解码不会宣称完整观察窗口。

## Wire v1与解码

头部固定128bytes，随后count×48bytes，最大6272bytes。所有整数明确little endian，
不直接写C结构体或padding。CRC32使用标准多项式，`123456789`向量为CBF43926。

| 头部偏移 | 字段 |
| --- | --- |
| 0..7 | EP0TRC1和结尾零 |
| 8..15 | version1、header128、record48、capacity128，各u16 |
| 16..35 | simulation标记、count、dropped、invalid、freeze_reason，各u32 |
| 36..39 | 必须为零的保留字段 |
| 40..63 | frequency、start tick、freeze tick，各u64 |
| 64..95 | boot ID及session ID，各16bytes |
| 96..103 | payload CRC32、header CRC32；计算header CRC时自身字段置零 |
| 104..111 | 4个接口poll_count，各u16 |
| 112..127 | 4个接口last_poll_result，各u32 |

记录字段顺序：begin/end各u64，ordinal/request_id/result/arg0/arg1各u32，stage u16、
interface/flags各u8、setup8bytes。ordinal由核心生成，从1连续增加，不复用存储位置。
独立解码器拒绝layout、长度、CRC、身份、时间、valid位、非法owner、重复请求ID及
阶段顺序错误；CRC重算不会绕过语义检查。计数缺失或保留字段非零同样拒绝。

解码的`iso_post_and_ack_returned`只是客户端路径描述，不代表ISO传输已完成或burst通过。
完整性标记不替代原STATUS、raw/transaction、ISO7、自身URB终结及完整启动日志验收。
`mixed_first_interface_setup`只比较各接口第一次成功读取；完整session的第一次可能都
是before STATUS，后续覆盖需查看对应request的实际setup及iso_paths。

## 实际源码副本验证

`tools/probe_a23_ep0_trace.py`首先核对生产源码三个哈希与冻结A23一致，然后按明确函数
范围插入记录点。每个替换锚点必须唯一，源码漂移即拒绝。实际生产源码不修改，也不把
生成副本接入Makefile。测试bridge中的assert、fixture身份和文件导出仅供电脑模拟。

25个回放包括原17个EP0场景、6个共享SETUP场景及2个完整session。
前23个与原冻结fixture输出逐项相同；完整session分别编译原源码和插入副本，在同一
服务模型下比较返回结果、post/STATUS次数、日志计数、seq及虚拟结束tick。
服务返回、速度、日志耗时和总线到达仍为注入，没有模拟HOS机器码或真实USB。

已确认的区分能力：

- 32ms覆盖模型：0/1先读BURST，接口2读C1/51 STATUS，无sequence写入或ISO post。
- 速度失败：speed Result97且speed valid=false，guard出现，sequence/post均无。
- post失败：sequence已写1，post Result96，URB invalid；原ACK分支继续按源码执行。
- ACK超时：ISO post已执行，ctrl_wait Result94、虚拟1000ms，ACK结果保留，seq仍1。
- GetSetup失败：Result98，没有setup字节；接口2没有ready事件时保留poll_count/last_result。
- 完整正常session记录STATUS→BURST→STATUS；覆盖session接口2只读两次STATUS。
  正常66条、覆盖52条，均低于128条，无溢出，模拟服务结果与原源码相同。

核心检查覆盖初始化/重复初始化、live/短buffer导出、嵌套跨度、非法记录/回退时钟、
冻结边界/不可变、满容量保留前缀、counter饱和及重复导出/CRC向量。
25个源码回放及核心检查通过ASan/UBSan；设备AArch64核心以严格C11/freestanding编译
为独立.o通过，未链接libnx程序、生成NSO/NSP或部署。
12项新Python检查包括所有截断长度、extra byte、CRC损坏、重算CRC后的非法字段、
不完整ACK/STATUS控制阶段及源码锚点漂移。相关回归246项无跳过通过，未宣称全库discovery通过。

## 复现与证据

从仓库根目录运行，输出必须是新目录：

```sh
python3.12 research/usb-ds-iso/tools/probe_a23_ep0_trace.py \
  --output /private/tmp/a23-ep0-trace-new-review
python3.12 -m unittest discover -s research/usb-ds-iso/tests -p 'test_ep0_trace.py' -v
python3.12 research/usb-ds-iso/tools/analyze_ep0_trace.py \
  /private/tmp/a23-ep0-trace-new-review/dispatch-ack-timeout.bin
```

最终证据：private/analysis/A23-EP0-memory-trace-review-20261013，保存生成源码、native程序、
25个trace及独立JSON解码、完整session基线、溢出sample、AArch64.o和SHA256SUMS。
源码快照、相关回归、manifest和凭据核验另存
private/analysis/A23-EP0-memory-trace-validation-20261013。
初始23场景原型仅存/private/tmp；最后格式含poll快照，不能用旧临时sample替代最终材料。

## 下一步

电脑上准备独立候选构建的接入/导出方案：明确唯一owner线程何时初始化和freeze，如何
确认停止记录及USB/ISO所有权，再导出已freeze字节。当前测试bridge不能直接移植为
生产代码；不得把控制回调返回、STATUS查询或设备断开自动当作所有权已排空。
还需记录boot/session与实际部署哈希绑定，并核对日志保留/延迟导出对时序的影响。

原型保留原同步LOG，故结果一致仅证明这些服务模型下的控制行为。没有测量真实tick/store
开销，也没有验证去掉或延后SD日志后行为；不能把AArch64编译通过当作设备行为验收。
本阶段不产生新firmware或可用次数，不选择新USB查询命令，也不改变timeout。
根因确认仍需接口2实际8byte setup、速度结果及post/ACK阶段的设备观察。

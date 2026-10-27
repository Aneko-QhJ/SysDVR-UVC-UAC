# 新transaction接口的空窗口观察方案（2026-10-12）

继续[SDK与原始STATUS绑定](IOUSBHOST_SDK_BINDING_AUDIT.md)，把新backend空窗口的预检、
一次提交、失败停止和独立观察分类落实到可注入会话及分析器。本轮只运行Mock；实际服务打开、
IOBuffer映射和USB请求未执行，设备仍A23，采集阶段及所有入口次数0不变。

后续[运行条件准备](IOUSBHOST_RUNTIME_READINESS.md)已完成服务引用、最终入队预算及pending退出
的具体实现和模拟核验，使用v2计划；本页v1冻结证据仍保持原内容及解释边界。

## 要区分的事实

旧libusb/legacy空窗口已有960槽Underrun/overall0基线，但新IOUSBHost transaction API
的空槽原生语义尚未实测。旧兼容层的NotSent转换/整体结果传播不能直接当作新API白名单。
当前先准备一个没有设备TD的窗口，完整保存新API提供的状态、actual、时间原文以及STATUS和
设备日志。它用于区分“观察是否完整”“空槽返回什么”“这些状态是否可接受”三件事。

模拟返回全Underrun、全0、271槽0xe000400e前缀或全0xdeadbeef，都可以完整观察；这不表示
它们在实机上是正常状态。前缀271只是故障注入数据，不是新增历史失败、根因或实机复现。
分析器不将未知值归并为成功或Underrun，按原32bit值保留counts、连续区间及初始空槽区间。

`observation_complete`只表示提供的Mock证据符合固定方案且完整。
`empty_native_policy=unverified`、`empty_status_policy_verified=false`、`baseline_accepted=false`、
`allow_next_burst=false`和`hardware_entry_enabled=false`在所有结果中保持不变。
历史三次native/raw分歧仍为失败；没有用模拟空窗口重新分类历史实机结果。

## 固定计划与预检顺序

[io_usb_host_probe_plan.py](../tools/io_usb_host_probe_plan.py)只输出固定JSON，不提供执行、prepare、
repeat、burst、lead覆盖或空槽白名单参数。计划为simulation、scenario no_td、960条request192/
options0、firstFrame lead64、最多一次ISO提交、设备trigger0、最多一次异步abort、repeat0，
实机入口关闭。未知字段、数值变化及bool/int/float替换在独立分析器中拒绝。

`initNoTDWithQueue:journal:`在prepare_begin中记录同一计划；C与Python定义由18份原生日志
交叉核验。当前provider仍在任何registry查询/打开之前拒绝真实operations。

| 顺序 | 离线组件落实的条件 | 仍须实机确认 |
| --- | --- | --- |
| 选择/Ready | 唯一候选、device/interface/parent ID、HS、alt0/EP83/ISO/MPS256/interval1，精确存储长度 | 真正枚举、服务引用寿命、排他打开和映射 |
| before STATUS | 原始168bytes、请求成功且无NSError、fresh IDLE/seq0/URB0；先持久化，再准许后续动作 | 真实控制回复及本次设备身份 |
| 帧号 | 一次mock_frame_number采样，begin不早于before结束，end不晚于记录时刻；uint64加64不能溢出 | 真实frameNumberWithTime及采样新鲜度/提交余量 |
| ISO提交 | 必须等于绑定firstFrame，最多一次；无帧号/错误帧号拒绝 | 新API实际提交结果与空槽完成语义 |
| callback/快照 | 自己的指针、原始overall及960条记录；pending/陌生指针不确认释放 | 实际DMA、取消及用户回调排空 |
| after/保存 | 完成快照后一次STATUS，原始回复绑定；只接受no_td scenario，完整保存/ack后才关闭 | 真实无TD日志、原生状态政策及后续验收 |

frame_sample包含currentFrame、begin/end Mach ticks、firstFrame和lead64。分析器除日志顺序外，
还比较native submit begin/return与journal边界，callback arrival必须与原始owner元数据完全一致。
输出帧号查询时长、sample end到native submit的间隔及提交调用时长，单位均为未换算的Mach ticks。
它不把输入帧号推算为实际总线相位，不建立设备时钟对齐。

本机SDK明确firstFrameNumber使用帧号，frameNumberWithTime省略microframe，不能将currentMicroframe
的数值直接塞入该字段。当前仅消费Mock帧号，未调用这些方法。排序及加64的算术检查不能证明
实际入队时仍有提前量；fsync、系统负载和SDK排队也会消耗时间。
`software_frame_freshness_verified=false`，未来真实backend仍须准备采样年龄阈值、时基和入队预算。
旧libusb的40ms等待与pump机制没有移植为新SDK运行条件；当前不声称完成严格时序对照。

## 控制请求与失败停止

纯函数A23NoTDControlAllowed只接受vendor interface IN c1/51/value0/index2/length168，覆盖全部
256种request码的模拟检查。它没有发送功能；将来真正的控制请求执行器必须接入该限制。
当前模拟会话没有trigger入口；真实operations无法打开，SDK readStatus也未运行。

新的空窗口日志审计要求两个有序STATUS记录，拒绝缺失、重复、格式损坏及任何其他vendor请求，
包括trigger50、cancel52、frames53、burst54和未知请求/错误tuple。标准控制记录可保留；
“两个日志记录”不是总线抓包或跨设备时钟关联，也不能证明固件日志没有遗漏。
旧STATUS/ISO7解析继续复用，no_td头部必须保持fresh，诊断112bytes允许变化的软件快照。

| 条件 | 已实现的停止与存储处置 |
| --- | --- |
| 预检/短或陈旧before/帧号失败 | 不提交ISO；原始回复或失败事件保留，Prepared资源可关闭 |
| wrong firstFrame | stop，提交计数0，禁止改一个帧号后重试 |
| pending期限到达 | 最多一次主机异步abort；返回值不表示DMA结束，禁止第二次abort、重投或关闭 |
| pending断开 | stop，不向已断开服务abort；继续持有映射及资源等待自己callback |
| 无callback或陌生指针 | 持有原存储与资源；不保存“完成包”，不关闭、不重开、不再提交 |
| after缺失 | 不保存确认或释放原存储；短/失败after则保留原文及已完成失败包 |
| 错误scenario | stop且不ack；可按原no_td方案保存失败证据，但不会变为通过 |
| 完成且保存 | ack后关闭；即使原生错误也保存原文，Completed不等于成功，不进行完成后取消 |
| 迟到/重复callback | journal继续记录；计数和事件本身否定观察，旧已保存raw不被覆盖 |
| journal/证据写失败 | 停止；禁止缺少确认的释放，不覆写或续写部分产物 |

plan的retain_until_process_exit描述当前Mock单请求隔离对象的有界存活方式。它不是已验证的实机
退出策略，也不提供强制destroy/reset许可。真实无callback退出、映射与SDK销毁仍须独立证明。
monitor的自持有和日志前缀也不是用户回调排空；callback_drain_verified始终false。

## 独立分析与本轮证据

[analyze_io_usb_host_no_td.py](../tools/analyze_io_usb_host_no_td.py)先验证完整collection、原始STATUS/
journal/native绑定和固定计划/帧号，再核对控制日志、960条原始状态与raw全零。
非零overall、未终结Invalid槽、actual非零、残留raw、timeout、detach、late或计划错配都会否定观察。
保持unknown empty status分布，不接受来自legacy无计划日志或旧burst的“新基线”。

CLI退出0表示Mock观察完整，1表示完整保存的失败观察，2表示损坏/格式错误/不属于此方案。
所有结果中baseline_accepted、allow_next_burst、hardware_verified和usb_strict_pass仍为false。
哈希用于关联提供的字节，不认证固件或日志，没有真实USB通过声明。

```sh
# 输出固定离线方案，不查询设备、不改变任何采集次数。
PYTHONDONTWRITEBYTECODE=1 python3 research/usb-ds-iso/tools/io_usb_host_probe_plan.py
# 只读审计本轮已冻结的Mock空窗口。
PYTHONDONTWRITEBYTECODE=1 python3 research/usb-ds-iso/tools/analyze_io_usb_host_no_td.py \
  research/usb-ds-iso/private/analysis/A23-IOUSBHost-no-td-plan-review-20261012/collections/clean-underrun
```

新增18个C/Objective-C空窗口场景通过ASan/UBSan：四类状态分布、非零overall、残留raw、actual非零、
Invalid槽、迟到回调、两种abort结果、pending detach、缺callback/帧号/after、溢出/错误帧号及
scenario错配。原有18个适配场景、10个STATUS会话和16个生命周期回归均通过。
74项Python检查全部通过、无跳过，新增14项包括重新计算哈希后的计划/帧号/时间错配和控制请求拒绝。
51次独立CLI返回预期结果；18份会话中13份可保存collection，仅4种Mock分布观察完整，接受基线0份。

材料冻结于private/analysis/A23-IOUSBHost-no-td-plan-review-20261012/：最终源码、原始Mock字节/
会话/13个collection、独立CLI结果、回归和sanitizer日志、SDK header哈希及provenance。
旧SDK绑定212份、旧session122份文件哈希只读核验通过；未修改旧冻结目录。
采集状态SHA256保持a592fc6bfe95f34c7a716f37dd0974e6481cfca04686354f1dfd6a77b8615ecd。

## 后续single burst的条件

服务引用、帧号采样年龄和pending有界等待的实现/拒绝条件已在后续运行条件准备中完成。
取得新API自身的一次fresh无TD完整证据，解释并冻结该backend的空槽原生政策后，才能另行准备
single burst。观察工具不自动推导政策或消耗/增加次数，不能直接把本页Mock通过作为准备依据。

后续burst应保持同一新backend、HS/A23/interval1/MPS256、request192/960槽/lead64，单次fresh
启动和唯一burst；在接受入队后记录trigger时间及原始控制请求结果，再关联自己的16个连续seq、
native/overall、STATUS/ISO7/设备唯一URB终结。trigger等待及截止时间必须由新backend预算定义，
不能凭旧工具40ms参数认定时序等价。任何失败停止，不重投、不开始串行，不宣称根因或修复。
这些是待准备条件，当前没有新burst执行器、真实采集入口或剩余次数。

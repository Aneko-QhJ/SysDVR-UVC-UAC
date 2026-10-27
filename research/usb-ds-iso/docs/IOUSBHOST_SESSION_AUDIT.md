# IOUSBHost离线会话、断开与设备关联（2026-10-12）

继续[离线证据链](IOUSBHOST_EVIDENCE_PIPELINE.md)，完成可注入的单请求会话组件、持久化事件日志、
独立会话分析器和STATUS/ISO7/启动日志关联检查。实际运行仅使用MockProvider/MockLease/MockPipe，
没有IOUSBHost服务枚举或创建、真实请求、SD访问、设备补丁修改或新采集入口。
旧三次错误、serial-clock的32轮成功、采集阶段及次数不变；根因和长期稳定性仍未确认。

## 生命周期与所有权

[io_usb_host_session.h](../host/io_usb_host_session.h)与对应.m接受提供的候选、资源provider和journal。
候选必须唯一，registry ID是非零整数，interface ID不同于device ID且parent_device_id匹配。
先验证提供字节的A23 HS描述符，再调用provider；打开返回的identity还须与选择时相同。
provider目前只由测试实现，不是系统注册表枚举、真实打开或权限的替代证据。
打开失败、identity变化、分配/pipe失败、打开中断开均停止；没有endpoint reset或自动恢复。

| 事件/阶段 | 模拟组件行为 |
| --- | --- |
| Ready | 独占原data/transaction存储及资源，尚无I/O借用 |
| submit | 每个会话只允许一次；非零firstFrame，owner持有存储 |
| deadline | 日志保存后请求一次异步abort；成功/拒绝均停止，不将abort返回当作完成 |
| detach且pending | 按自己的device/interface ID关联；不对消失服务发abort，不销毁或释放存储 |
| detach且Ready | 没有提交，可关闭资源；禁止随后提交 |
| detach后无回调 | 保留这一个有界owner、资源及存储直至进程退出，不能靠通知解除DMA所有权 |
| 正确完成 | owner先复制全量证据，再写事件日志/通知消费者；允许保存错误证据 |
| 陌生回调指针 | 不读取陌生地址；owner/会话Retained，不允许保存确认或关闭释放 |
| 已保存并校验 | 原存储获ack后才允许关闭资源；Completed不是传输成功分类 |
| 证据或事件写失败 | 停止；无完成/保存确认时禁止关闭，不覆写失败目录或日志 |

在任何提交尝试后，一个有界monitor会自持有至进程退出，继续记录关闭后的回调。
正确完成并保存后，资源可以关闭；monitor只保留owner快照、journal及计数，不再发请求。
未完成/陌生指针时则连资源和原存储一起保留。它不是用户回调排空，也没有暴露重开或重投入口。
测试故意保留若干隔离对象至退出；不能把它们误当作可无限创建的实机恢复策略。

SDK的interestHandler在独立于I/O queue的内部串行队列上执行，见本机IOUSBHostObject.h。
将来真实adapter必须dispatch_async至会话queue后处理，不能直接在通知队列改owner状态或同步等该队列。
真实destroy、对象取消注册、服务断开下的映射和用户回调时序仍需单独核验。

## 迟到回调与持久化事件

owner新增提交前安装的completion observer，每次回调都会记录原32bit status、arrival Mach ticks、
count、owner旧状态及指针是否与原提交地址相同。只比较地址；即使存储已释放也不解引用。
首份raw/transaction快照在observer的任何磁盘等待前复制；重复回调不重新读取或覆盖快照。
这些ticks仍是软件观测，不证明总线服务相位。

A23SimulationJournal独占创建0600文件，每个JSONL事件短写/EINTR处理、fsync及逐字节读回。
同一会话queue写入，文件最多128事件，每行最多4096bytes；失败后禁止继续追加动作日志。
父目录及文件须可信且没有其他写入者。文件可能以一段未完成JSON结尾；分析器明确拒绝该尾部，
不会默默跳过后把剩下的正常行当作成功。没有“已排空回调”footer。

[analyze_io_usb_host_session.py](../tools/analyze_io_usb_host_session.py)核验session ID/index/ticks、
唯一选择、registry父子关系、Ready配置、最多一次提交、callback/snapshot、保存与关闭的顺序。
它通过日志内manifest SHA关联既有完整bundle，还比较firstFrame、overall、owner状态、保存时
callback数量和timeout。没有bundle只能验收日志前缀，不能通过模拟会话。

新增late-after-close模拟：bundle内callback_count_at_save仍为1，raw及原状态不变；关闭后第二次
回调写入独立journal，分析结果callbacks=2、late_callback_observed=true、simulation_session_pass=false。
即使删掉stop文字，迟到事件本身也会否定通过。它没有把旧已冻结快照改成第二份“正确结果”。
callback_drain_verified、hardware_verified及usb_strict_pass在该工具中恒为false。
文件哈希和单次日志读取只证明读取到的内容，不能证明之后永远不会有更多回调。

## STATUS、ISO7与完整日志的关联范围

[audit_io_usb_host_device.py](../tools/audit_io_usb_host_device.py)消费提供的两个168byte原始STATUS和
完整日志字节，不查询设备、不写run/collection。检查协议magic/version、sequence范围和endpoint83，
保留全部头字段及112byte诊断原文，区分fresh和terminal。

启动日志要求唯一A23/ISO7/interval1标记、HOS22.5.0、目标usb模块BuildID与范围、成功查询/attach、
runtime result0/非零record/last-rc0和启动顺序。拒绝缺开头/无换行尾、第二套启动、冲突身份、
rollback或target mismatch。runtime record原值保留，不以某个固定历史次数代替安装身份。
日志没有签名或机器码内容；startup_log_identity_matches不等于firmware_bytes_verified。
通用“running(video + audio)”文字不能证明音频实际启用、视频已关闭或本次采集绑定。

single_burst要求唯一submit/timing/terminal，以自己的seq/URB关联到STATUS的report ID、state2、
requested/transferred3072、urb_status3和结果0。设备tick顺序及frequency19200000单独核对，
没有与主机Mach跨时钟对齐的推论。ISO7检查terminal1/bitmapFFFF/actual3072、error_offset0、
context sentinel和interval1/MPS256字段、firstFrame选择与控制字一致、模块内环指针及前两个
成功事件的ED标签。事件sentinel无效时只保留原dwords，不把其中可能陈旧的CC解释为有效事件。
首TRB位置按输入动态验证，不固定17D000；检查247槽环及Link跨越后的自己的ED地址。

no_td要求前后STATUS头保持fresh、没有submit/timing/terminal及vendor trigger/cancel记录。
diagnostics可以含变化的软件快照，不能错误要求168bytes完全相同，也不把它解释成一个burst。
关键日志行格式错误直接拒绝；重复提交/终结、错误ID/状态、取消、context或event错误均不能通过关系检查。

11项设备检查包含旧burst-window样本的只读回放。其STATUS字节由历史JSON头字段与diagnostics_hex
重构，明确不是当时保存的原始168byte二进制，也不属于新IOUSBHost backend。
旧2630byte日志SHA256仍为53eda5f61219329820a790611fef2c00daa1d929e4b82f87cf7069ad98e31f9e。
回放只证明解析与已有样本相容，不计作新的实机样本；capture_binding_verified、firmware_bytes_verified、
video_closed_verified、hardware_verified和usb_strict_pass恒为false。

## 验证与冻结

16个Objective-C生命周期场景覆盖normal、关闭后迟到、pending断开、无回调、陌生指针、两种
abort结果、enqueue/open拒绝、identity变化、候选歧义、parent不符、Ready/打开中断开、保存失败
及journal中途写失败。ASan/UBSan通过。owner和既有六包写盘测试因observer改动重新验证，均通过。
独立检查共44项全部通过：12项会话、11项设备、既有15项证据与6项framework解析；无跳过。
布尔字段严格类型验证，不能将JSON数字0当作false或将false当作原生status0。

```sh
/usr/bin/clang -std=c11 -fblocks -fobjc-arc -Wall -Wextra -Werror \
  -fsanitize=address,undefined -framework Foundation -framework IOUSBHost \
  research/usb-ds-iso/host/io_usb_host_transaction_owner.m \
  research/usb-ds-iso/host/io_usb_host_evidence.m \
  research/usb-ds-iso/host/io_usb_host_runtime_guard.m \
  research/usb-ds-iso/host/io_usb_host_session.m \
  research/usb-ds-iso/tests/io_usb_host_session_test.m -o /tmp/a23-session-test
/tmp/a23-session-test /tmp/a23-session-new-directory
PYTHONDONTWRITEBYTECODE=1 A23_SESSION_FIXTURES=/tmp/a23-session-new-directory \
  /opt/homebrew/bin/python3.12 -m unittest discover \
  -s research/usb-ds-iso/tests -p test_io_usb_host_session.py -v
```

有效冻结材料为private/analysis/A23-IOUSBHost-session-review-20261012/：当前源码、final模拟会话、
独立CLI结果、原生/写盘回归记录、设备模拟/历史重构输入和结果、provenance及SHA256SUMS。
事件字段曾在临时调试输出中以int代替BOOL；已纠正并在独立分析器交叉检查，冻结只收final输出。
旧冻结目录不改写，采集状态SHA256仍为a592fc6bfe95f34c7a716f37dd0974e6481cfca04686354f1dfd6a77b8615ecd。

## 仍可离线推进与必须实机确认

电脑上下一步可实现真实SDK adapter的编译/故障注入边界，补原始STATUS保存和会话/collection绑定，
设计并冻结新backend空窗口及fresh单burst的预检、停止和验收条件。先处理空槽策略未知这一缺口，
不能把旧backend空槽Underrun或旧32轮通过直接移植为新backend许可条件。

本页冻结时仍没有真实SDK provider；后续[SDK适配与原始STATUS绑定](IOUSBHOST_SDK_BINDING_AUDIT.md)
已补真实操作实现编译及Mock核验，provider明确拒绝真实operations。没有服务枚举/打开、
实际IOBuffer映射、vendor STATUS/trigger执行或新采集阶段。
真正的服务唯一性/排他打开、映射、HS配置、新接口返回及取消/断开/回调排空行为需要实机证据。
提供字节的identity、Mock资源关闭、旧日志回放和软件模拟都不能替代这些确认。

# 短包 SDK 组件与设备侧录关系（2026-10-27）

后续[NSP/IPS配套包、驻留入口与写盘](A23_SHORT24_PACKAGE_AND_ENTRY.md)已完成离线准备和
检查；本文的“下一项”保留本阶段顺序。仍没有真实SDK采集、部署或新实测授权。

本轮把[16TD×24字节候选](A23_SHORT24_OFFLINE_CANDIDATE.md)接到独立的SDK主机组件，
并建立主机文件与EXE3/OWN2/trace的关系核验。最终21个原生注入场景及7项关系检查通过。
SDK方法按本机头文件完成编译，**没有创建真实SDK接口/pipe对象或调用USB I/O**。

这是可编译、可复现的单次能力组件，尚无服务发现/打开程序、可直接启动的采集命令或新NSP。
没有写卡、部署、签发新范围或实测；SDK排空、资源释放、复用及持续音频仍未证明。

## 主机接线

[a23_short24_capture.h](../host/a23_short24_capture.h)与
[a23_short24_capture.m](../host/a23_short24_capture.m)包含两层：

| 组件 | 行为 |
| --- | --- |
| A23Short24SDKIO | 接收调用者已经打开的interface和pipe；检查HS、vendor接口2/alt0、endpoint0x83/MPS256/interval1；通过SDK分配raw3072及共享transaction3584字节 |
| A23Short24Capture | 固定128个transaction，每项请求24字节；一次ISO、一次BURST、最多一次异步abort；没有再次start、重试或复用入口 |

SDK方法实际调用的tuple为：STATUS `c1/51/0/2/168`，首帧`current_frame+32`，
BURST `41/54/first/2/0`，completionTimeout0.016秒。STATUS同步请求使用3秒SDK超时。
超时参数不是已证明的硬中断。SDK模式须使用导出的`A23Short24NowNanoseconds`时钟，
fixture的时钟仅用于注入；主机与设备tick不跨域相减。

调用顺序为：新鲜before STATUS→frame sample→ISO→BURST→两个回调已由owner queue处理→
after STATUS。ISO/control入口先记录原子计数与到达时刻，再转交串行队列，软件期限按入口
时刻判断，不把本地队列延迟误判为SDK完成超时。

frame查询/年龄、enqueue耗时和trigger前空档有独立检查。记录BURST意图后再次读取入口计数
和时间预算；该间隙内若ISO已返回、interest已到达或预算超限，就不发送BURST。
这只描述最后一次本地观察与调用顺序，不证明两个时刻之间不可能发生并发事件。

全部128槽被保存，包括空槽中的原生错误。组件的`observation_complete`仅表示本次回调及
STATUS观察已完成；它不判定每包正确。独立文件消费者仍会拒绝空槽错误、overall错误、
错误包长、图样、状态和设备关系，不能单凭这个布尔字段宣称传输通过。

## 停止与资源寿命

开始后capture持有自己、IO对象及两份backing。超时、拒绝、foreign pointer、重复回调、
interest、成功采样和snapshot导出均不释放或复用这些存储。异步abort返回不会清除pending。
SDK enqueue拒绝或指针归属未知时保留`io_unresolved=true`，NSError的domain/code原样记录。

所有导出均保持`process_exit_authorized=false`、`callback_drain_verified=false`和
`buffer_reuse_verified=false`。snapshot只返回不可变副本，不是持久化回执或原生交还证明；
尚未完成的副本是部分观察。后续运行主循环必须尊重这项保留政策，不能看见观察完成就退出。
真实对象创建者负责interest注册和转交，当前组件没有自行发现、打开、destroy或解除注册。

## 设备证据关联

[analyze_a23_short24_session.py](../tools/analyze_a23_short24_session.py)读取供应的主机文件，
复用既有通用EXE3/OWN2解码器，再核对短包关系：

- 主机初始STATUS新鲜、一次ISO/BURST及各一次回调、原生入口期限、lead32和最后准入预算。
- 所有128项原生结果及16个连续IS24图样，后置STATUS为384字节、正确序号和URB。
- EXE3与期望的新recipe一致，外部primary与嵌入部分逐字节相同，没有trace丢失或未匹配报告。
- 接口2的before STATUS→BURST→after STATUS顺序；STATUS IN168/OUT0两阶段与parse关联。
- 设备HS、sequence、唯一ISO post384、匹配URB、零长度IN ACK及对应终态ISO ledger。

结果中的`supplied_host_observation_complete`与`supplied_device_relation_consistent`只表示
所提供材料之间一致；不认证来源、部署或物理执行。device_lifecycle_verified、hardware_verified、
usb_strict_pass及持续音频等字段保持false。本轮没有关联真实main_return生命周期日志。

## 检查与模型来源

最终结果位于`private/analysis/A23-short24-sdk-20261027-r5`。

1. 原生Objective-C fixture使用实际组件，注入21个场景。覆盖两种回调顺序、inline control、
   queue延迟、原生晚到、超时/abort拒绝、enqueue拒绝、foreign pointer、重复回调、interest、
   短STATUS、坏frame、overall/control错误、空槽错误和两种最终准入反例。
2. C fixture直接包含候选中的实际序列化头文件，生成纯模型EXE3/OWN2/TRC2。它提供3个
   目标请求、48条trace及终态ledger；报告、join和save receipt都是显式模型输入。
   该模型没有重标旧实机文件，也不模拟完整启动广播、实际文件系统或设备生命周期。
3. 四种正常安排通过条件关系核验，其余17种被拒绝。7项独立检查包括重新计算CRC后的
   错误设备长度/sequence/STATUS反例、错误recipe、外部primary不一致，以及擦掉摘要故障
   后仍由原生时刻和重复事件拒绝的样本。空槽错误不被成功回调隐藏。

原生C/Objective-C fixture使用ASan/UBSan。此次没有重编译设备ELF或重跑此前ARM模型，
只核验已有候选及模型输入的封存摘要。文件CLI正向检查也通过。

复现命令（新输出目录须不存在）：

```sh
python3 research/usb-ds-iso/tools/audit_a23_short24_sdk.py \
  --output /private/tmp/a23-short24-sdk-audit
```

该工具只编译SDK能力代码并运行注入对象，不调用SDK构造器、注册表或采集入口。
开发中一次手工fixture命令传入65位recipe，被构造器拒绝；后续统一从已封存recipe读取。
最初C fixture补齐native类型声明后编译通过。r3独立消费者还发现逻辑表达式被Objective-C
装箱为整数而非JSON布尔值，现已显式转BOOL；r4的19个场景和6项关系检查先通过，
补充最后准入反例后选r5。先前输出保留，不通过改写原件纠正结果。

## 下一项

接下来离线完成新设备NSP的独立打包/读回核验，以及主机运行包装、完整证据写盘和
一次实验问题卡。运行包装需处理已启动对象的保留状态和停止后的持有方式，不能擅自添加
正常退出或release。卡上仍是旧192字节设备；新SDK组件不能直接对它启动。

后续硬件操作仍须适用授权与当次现场条件。本轮`remaining=0`、`acquisition_enabled=false`、
日志pending=false，旧actual465、消费namespace和冻结来源保持；没有创建新许可或占用新序号。

# SDK初始化错误与启动标记审查（2026-10-17，Asia/Shanghai）

后续：[序号65首次实测及只读回收](A23_CONTEXT65_FIRST_LIVE.md)已完成，SDK初始化及65..80载荷成功。65权限已消费，69原件已保存并弹出；下文保留原离线研究状态，不能据前后变化单独认定49根因。

续接：[序号65与执行环境证据候选](A23_CONTEXT65_RECEIVER.md)已完成离线构建和判读验证，尚无正式发行或新实测。下方保留本轮研究原始边界。

对照两次lead32成功样本及序号49初始化失败，已找到**主机执行模式差异**，并验证当前框架会覆盖父类初始化错误。它们收窄了调查方向，但尚未证明沙箱就是此次失败的原因。`boot2.flag`缺失仍是独立的部署核验问题。

## 当前实机结论

lead32已有两次单次16×192字节成功，尚未验收持续流。[序号49首次测试](A23_SEQUENCE_FIRST_LIVE.md)仅到SDK初始化，没有进入采集协调器、提交ISO或发送序号49 BURST，不能评价新序号载荷方案。49..64仍永久保留，一次记录仍failed_no_retry/remaining0；59个设备原件已保存、SD已弹出，部署回执仍拒绝，不需要自动再次读卡。

## 原始执行命令对照

从原始会话的三个确切工具调用及对应返回值提取证据，未采用审批摘要推断执行模式。原会话起于10月15日、延续至10月17日；证据仅复制本研究的三条命令，不复制其他会话内容。

| 主机运行 | 调用时间（北京时间） | 命令中的沙箱参数 | 已保存结果 |
| --- | --- | --- | --- |
| lead32首次有效样本 | 13:12:24.959 | require_escalated | 初始化成功；单次3072字节匹配 |
| lead32独立复现 | 13:37:39.676 | require_escalated | 初始化成功；单次3072字节匹配 |
| sequence49 | 15:44:38.673 | 未指定，使用默认模式 | sdk_init失败，外层0xE00002C9 |

三次run、两个receiver-build的封存均复核。原始SDK适配、被动等待、接收循环及等待入口等五份初始化相关源码哈希相同，六设备材料绑定相同。新序号接收器和旧lead32接收器的二进制不同；历史进程没有保存完整沙箱配置，不能将该对照当作只改变权限的受控实验，也不能推断当时具体被拒绝的操作。

独立重分析两次成功原件仍见host_observation_complete与host_transaction_candidate成立。组件自己的usb_strict_pass/hardware_verified仍为false，未因本轮对照而提升物理认证或改写旧记录。

失败等待日志的sdk_open_intent到preflight_failed约0.718083ms；两次成功的sdk_open_intent到prepared分别约1.790334ms、1.964667ms。这些区间含日志、清理和其他准备工作，不能等同IOServiceOpen耗时，也不能凭快慢确定权限错误。

## 为什么错误文本不能定位底层原因

本机macOS27.0.1/26A434的IOUSBHost.framework UUID为B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B。当前95236字节text与10月12日冻结文本逐字节一致；旧进程实际加载的framework身份没有独立记录。

代码只读检查器解析16个stub/selector及9个CFString，不枚举注册表、不打开USB对象。关键边界为：

| 当前框架位置 | 机器码行为 |
| --- | --- |
| Interface init，0x197AD26B0..26B8 | objc_msgSendSuper2调用父类；nil转失败分支 |
| Interface失败，0x197AD28D8..28F4 | 重新构造0xE00002C9并覆盖调用者NSError指针 |
| Object init，0x197ADC2DC | 调用openWithOptions:error: |
| open，0x197ADCEDC | IOServiceOpen，type0；失败时原始返回值曾写入父类NSError |
| open，0x197ADD0F0 | 后续IOConnectCallScalarMethod selector0进行独占打开 |

父类初始化还包括集合、队列、通知端口及描述符准备，故Interface的super-init失败不等于已观察到IOServiceOpen失败。公开文档只规定初始化建立内核通信通道及独占打开的一般行为，不为此次0x2C9指定唯一原因。[Apple对象初始化说明](https://developer.apple.com/documentation/iousbhost/iousbhostobject/initwithioservice%3Aqueue%3Aerror%3Ainteresthandler%3A)

另外运行了当前加载框架的四个注入场景：先替换Object父类初始化实现，使其只返回指定NSError和nil，再调用Interface子类初始化。**原父类实现调用0次、真实SDK初始化对象0个、USB请求0次**；模型确实分配了4个SDK Interface实例，未声称完全不涉及SDK类。结果如下：

| 注入父类错误 | 输入值 | Interface输出 |
| --- | --- | --- |
| NotPermitted | 0xE00002E2 | 0xE00002C9 / Failed [super init] |
| ExclusiveAccess | 0xE00002C5 | 同上 |
| NoDevice | 0xE00002C0 | 同上 |
| NoMemory | 0xE00002BD | 同上 |

四例均丢失NSUnderlyingError；userInfo仅含描述、失败原因和恢复建议。ASan/UBSan运行无诊断。这验证了外层错误的信息损失，不能选择其中一个模型作为实机根因。模型替换只发生在独立短进程中，未改系统framework或采集接收器。

只读查询了15:45:00..15:45:10的sandboxd/沙箱子系统/IOUSBHost历史日志。默认沙箱拒绝log命令；允许读取系统日志后返回count0。历史日志缺失不证明当时没有权限拒绝，也不能用本次log命令的限制代替上次IOServiceOpen的实际返回值。

## boot2.flag的作用及缺失边界

两份封存快照直接证明：13:41回收时boot2.flag存在且为0字节，15:49回收时缺失，仍有._boot2.flag。其余NSP、toolbox.json、IPS保持一致。两个快照限定了可观察的变化区间，不能确定删除时刻、执行者或哪次启动受到影响。

核对Atmosphère官方参考提交6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8的两个源码blob，保存完整来源与Git blob/SHA256校验：

- boot2遍历内容目录后检查HasContentSpecificFlag(program_id, "boot2")，只有有标记的程序进入启动回调；已审阅启动代码未消费或删除该标记。[官方boot2实现](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libstratosphere/source/boot2/boot2_api.board.nintendo_nx.cpp)
- 配置层生成精确的/atmosphere/contents/<program-id>/flags/<flag>.flag路径并检查文件存在；._boot2.flag不是该路径。[官方标记读取实现](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libstratosphere/source/cfg/cfg_flags.board.nintendo_nx.inc)

本轮未核验设备所运行Atmosphère二进制与参考提交一致，因此参考源码仅限定解释范围。新增三组设备上下文确实有正常保存和main_return，但缺少序号49的独有关联；它们不能证明标记在主机打开接口时仍存在，也不能证明标记缺失导致主机初始化失败。不将缺失解释为已确认的正常一次性消费，也不自动恢复标记。

## 续接动作

1. 离线准备使用新未保留序号块的独立候选和判读绑定。65..80可作为待审核范围；需先重新核对完整历史和持久保留，当前未保留或签发。49..64不可再次使用。
2. 下次主机入口明确记录执行模式、UID/EUID、系统/framework和接收器身份，并保持已知lead32及4/2/2ms预算。优先消除已知执行环境差异；目前无证据要求改固件或时间预算。不要以额外预先打开、seize或自动重试代替诊断。
3. 新正式记录不能沿用“最新四部署文件全部匹配”的旧假设。未来现场操作前须独立处理缺失标记并取得真实四文件读回、保存及弹出回执；恢复标记和新实测均等待相应明确指令。本轮未实现修复、写卡或新测试。
4. 若未来在明确的执行环境下仍初始化失败，再设计保留底层返回值的独立诊断；当前外层NSError信息不足，单纯输出更多相同字段不能恢复被覆盖错误。

## 封存及验证

本轮审查目录为private/analysis/A23-sdk-init-environment-review-20261017，29文件；SHA256SUMS摘要为4607a8bb1a87730220c470761b05026c96a79acfadfc297ae6d4e18b2cacf98a。包含原始命令摘录、三运行重分析、当前stub与常量解析、关键反汇编、注入源码/可执行文件/结果、系统日志查询结果、官方参考源码及审查脚本。

407条检查覆盖272既有来源、旧票据/设备生产源、两次成功和一次失败run、build、回收封存及49..64保留文件。它们包括逐文件哈希与结构断言，**不是407次独立实机或软件场景测试**；另外的4个注入场景才是本次运行行为模型。旧framework材料使用早期SHA256SUMS格式（无COMMITTED），47条全部匹配、无未列文件，未强加新格式或修改封存。

本轮USB0、SD0、正式签发0；设备包、接收器、预算、272来源和一次记录均保持。主pending增加研究引用，保留card_snapshot_saved=true、deployment_files_match=false、recovered=false、recovery_receipt_accepted=false及remaining0。原始实测结论与根因未确认的边界保持。

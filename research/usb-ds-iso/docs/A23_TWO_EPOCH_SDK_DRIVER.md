# 两轮SDK执行驱动与联合回执（2026-10-18）

后续：[独立等待入口、文件构建绑定及最终检查点](A23_TWO_EPOCH_SDK_ENTRY.md)已完成离线验证；生产许可与现场执行模式未实现。以下保留驱动阶段结果。

独立的 `A23TwoEpochSDKDriver` 已完成离线实现、编译及故障审查，接受上一阶段已准备且未使用的SDK lease。两轮逐轮保存，保留原生回调入口时间，收尾联合检查资源和归档。本轮以Foundation及假operations替代真实SDK客户端和映射；没有USB、SD、固件构建、部署、发行或序号保留。

42个原生场景、20份坏归档、12项专项检查通过ASan/UBSan；搬移副本在独立进程重建并重新分类一致。只有正常及“回调及时到达、队列延迟25ms”两个注入模型获完整链，其余40个均不完整。81..112共6144字节仍是模型数据，不能据此判断真实双轮或设备包复用成功。

## 接管、执行与保存

新增 `host/a23_two_epoch_sdk_driver.h/.m`。旧329项来源全部保持，包含旧离线协调器、资源层、分析器和测试。旧 `A23TwoEpochReceiver` 继续拒绝SDK资源，未改开关。

新驱动仅接受 `offlineSimulation=false`、`sdkResources=true`、`sdk_capability` 模式的健康lease；四存储及服务引用必须保持，计数为0、回调[0,0]、runtime_touched=false。构造函数在清零及owner初始化之前检查未使用状态。模型先做STATUS并在buffer写a5，构造拒绝后a5保持，防止接管已使用的缓冲区。

调用方提供串行队列、时钟、可信且已存在的输出目录及journal；负责在队列上start/poll。驱动本身没有设备发现、open、等待CLI、工单、重置、发行或授权入口。最多两次ISO/BURST、四次STATUS、两次frame、一次异步abort，活跃引用、pipe和四块存储保留至进程结束。

每轮重新取frame、lead32；沿用query2ms、样本年龄16ms、enqueue8ms、trigger gap8ms/样本年龄32ms预算，控制回调16ms、ISO2s。回调期限使用原生入口采样，不能把及时回调的队列延迟算成到达超时。完整核对960事务、16×192字节、STATUS/URB/ISO7，第二轮URB须不同，第二轮before须与第一轮after逐字节一致。

每轮文件fsync/读回、manifest/COMMITTED和持久journal都完成后才ack owner，下一次poll才准入第二轮。文件已提交而saved journal失败，仍保持saved_epochs=0，不补写、不续第二轮。旧代/重复/错误指针/控制错误、通知、保存失败或资源异常均停止；每次guard还联合检查资源层，因此两轮结束后的第三次ISO或额外STATUS会使上层complete失效。

## 观察窗口与回执

第二轮保存后先记录 `epochs_saved`，complete仍为false。后续poll从此后的时钟点观察至少250ms，持久写入 `observation_complete` 再标完整。正常journal共25条。该有限观察窗口仅为收尾门禁，**不证明回调已经排空**；更迟的回调仍会使结果无效，不能据此释放活跃映射或宣称连续稳定性。

`saveReceiptOnce` 仅在观察完成或停止后允许一次排他保存；观察未完成不会消费机会。它写独立 `sdk-receipt/receipt.json`、原始 `snapshot.json` 字节、SHA256SUMS及COMMITTED，执行同样fsync/读回。哈希绑定原始snapshot字节，避免跨语言JSON Unicode编码差异。碰撞或部分保存失败停止，不覆盖或重试。

提交时再次比较当前结果；`receiptStatus` 继续比较快照与当前结果，迟到回调使已提交回执stale/saved=false。失败状态也可以保存检查点，但分析器拒绝将它当作完整链。磁盘提交不表示将来的回调不会再来。未来正式入口仍须在最终导出result/receipt-status前做收尾检查；当前导出由测试fixture执行，尚无专用现场可执行程序。

## SDK观测与独立分析

新增标准库分析器 `tools/analyze_a23_two_epoch_sdk.py`，要求SDK专用结果/事件/bundle/receipt schema与 `sdk_observation` 模式；校验逐轮载荷、事务、STATUS、时限、保存顺序、资源计数、观察窗口及快照与最新result一致。保留原始来源字段 `sdk_control_reply`、`sdk_frame_number`、`sdk_runtime_budget`，不把SDK输入改写成mock再交旧分析器。

原生模型采用假operations走SDK provider分支，status/frame显式携带 `injected_fixture=true`；分析返回 `input_origin=injected_sdk_model`。六项来源标记全缺失时仅返回 `unverified_sdk_observation`，混合标记拒绝。字段名与文件哈希只能检查供应材料的一致性，不能认证物理来源。分析结论命名为 `supplied_sdk_chain_complete`，hardware_verified、physical_run_authenticated、device_trace_verified、callback_drain_verified、continuous_streaming_verified和hardware_entry_enabled均保持false。

`tools/a23_two_epoch_sdk_source.py` 确定性派生独立驱动和分析器，审查绑定旧文件哈希并验证生成结果完全一致，差异随审查封存。这是源码派生，不是观测数据改标。新SDK行为与门禁在新文件中实现，不改旧329来源。

## 验证材料

42个场景包含3个构造前拒绝、2个完整模型、1个两轮保存但观察未满的待定模型及36个停止模型；collector总计拒绝40。覆盖未使用接管、原生到达/排队延迟、期限/预算、载荷/STATUS/URB、旧回调、持久保存与journal故障、回执碰撞、观察窗口前后和回执提交后的故障。活跃模型引用保持1，destroy0，ISO/BURST≤2、abort≤1。

20份坏归档在修改后重算epoch/receipt manifests、snapshot哈希和journal文件绑定，再分别验证语义拒绝；另包含刻意缺失提交、部分journal和重复JSON键。覆盖mock来源、混合origin、frame_time0、缩短观察窗口、资源poison/多请求/回调/布尔计数、硬件声明、旧模式、过期/不一致回执、错误binding、载荷损坏和URB复用。拒绝原因逐项封存，不以旧manifest不符代替语义检查。

12项专项检查通过；审查原生编译使用-Wall/-Wextra/-Werror、AddressSanitizer及UndefinedBehaviorSanitizer。搬移336份来源及归档，新进程验证派生、重编译42场景、重分析2完整/40拒绝及20坏件；语义结果一致。比较排除每次生成的session UUID及观察时钟绝对值，分别要求实际观察间隔≥250ms。正式Python重放未读取原checkout或/Volumes；原生编译使用搬移来源和本机SDK。

- 审查：`private/analysis/A23-sdk-driver-review-20261018-r1`。
- 验证：`private/analysis/A23-sdk-driver-validation-20261018-r1`。
- 收尾：`private/analysis/A23-sdk-driver-closeout-20261018`。

## 续接

329旧来源保持，新增7项共336；23保护项、旧49/65记录、65..80永久保留及失败修复owner/状态不变。65保持已回收、remaining0；81..112未保留，仅模型取值。沿用上次设备关机及SD于14:41:59+08弹出记录，本轮未检查当前现场状态。

下一步离线准备专用可执行入口与build/进程环境、等待与收尾回执绑定，再准备最新69基线及原子32序号流程。真实SDK初始化/映射、完整设备trace/URB代际、双轮设备包复用及连续稳定性仍待验证，不能直接实测。继续优先使用编译、注入故障和文件副本替代有风险的现场操作；新测试须有新的明确指令和现场确认。

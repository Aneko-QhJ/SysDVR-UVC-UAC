# 无文件状态的退出链审查与阶段记录原型（2026-10-16）

针对[首次 quiet 实测未留下导出文件](A23_QUIET_FIRST_LIVE_RECOVERY.md)的问题，本轮重新
核对同一已部署候选的源码和 ELF，并实现独立的主线程阶段记录格式、写入策略原型和
前缀解析器。**这不是新的设备候选**：尚无 SDK 文件适配或主程序接入，未重编 ARM、
打包、部署或重跑实机。原 quiet ELF/接收器、生产文件和已消费次数保持。

## 先明确原程序能说明什么

同一 ELF `56778e57…` 的 main、VideoStreamThread、普通/诊断保存和 EXE3 构建/保存
共六个函数重新按真实指令字节与反汇编关联，保存函数摘要及调用地址；源码定位了十个
接入点。所用的是当前 quiet ELF，未把其他候选的地址证书套到此处。

协议枚举为 IDLE=0、PENDING=1、COMPLETE=2、FAILED=3、**RETAINED=4**。本次 STATUS
的 state4/urb_status2 不代表正常传输完成；正常捕获导出受所有权检查约束，诊断路径
仍可能保存并永久保留。state4 本身也不能说明窗口、双 join 或诊断保存是否发生。

g_running 已经是 atomic_bool；不能把无文件简单归因于普通共享 bool。设备窗口只在
同步调用前后检查，仍可能尚未返回。主线程离开循环后依次经过 cleanup begin、两次
threadWaitForExit、exporter 身份、正常/诊断导出和文件保存，多个返回/永久等待分支
都可能没有新文件。旧文件模型虽覆盖多种 FS 失败，但不提供这一次实际分支的观察。
当前仍未确认此次无文件或 ISO 零长度的根因。

## 最小接入方案

拟由 main 单独持有一个预分配的二进制记录文件，使用独立 main nonce 和运行 recipe。
文件须在 `UvcDeviceInitialize` **之前**创建并核验；不能等主导出失败后才尝试创建它。
拟定文件名 `/ep0-life-<main_nonce>.bin`，与捕获文件分离，不覆盖旧文件。

| 时机 | 计划记录 | 限制 |
| --- | --- | --- |
| USB 初始化前 | 文件准备、USB init 调用/结果 | 初始化失败应在仍可使用启动日志时报告；未准备成功不得进入本次新 USB 诊断 |
| CoreSetDiagnosticQuiet(true) 前 | quiet_enter | 成功后进入附加记录的 defer 状态 |
| main 的 g_running 循环内 | 不写阶段文件、不发周期探测 | 不改变首轮请求的窗口负载，也不额外发 USB 请求 |
| main 离开该循环后 | main_loop_left、cleanup result、每次 join 调用/返回 | 只写 main 自己的观察，阻塞调用之前的记录有独立价值；Core 文本日志仍按原门禁 |
| 两次 join 返回成功后 | exporter、owner finish、可选 trace boot/session 关联 | 失败 join 前不读取 owner、guard、trace 或 DMA 缓冲 |
| 主文件与 EXE3 保存 | 保存调用/返回、SD open 和 create 调用/结果 | 只挂接候选自己的文件适配函数，不在通用 FS API 上递归记录记录器自身的 I/O |
| 保留或返回分支 | retain / main_return | 仅闭合阶段记录，不授予清理或进程退出证明 |

该方案不是 watchdog，不设置新的 stop、不打断同步调用、不取消 URB、不绕过 join，
也不把写记录作为清理成功条件。记录 I/O 失败后停止后续附加写，不重写、补槽或重试；
原所有权与保存决策须保持原样。SDK 适配尚未实现，上述启动门禁也尚未接入设备。

如果记录只停在 quiet_enter，仍无法判断 main 尚未离开循环、调度/同步调用阻塞，
还是后续记录 I/O 未完成。调用前记录与返回记录可以保留正向阶段证据，但**最后一个
有效记录不等于实际最后执行位置**。这是方案保留的边界，不能称为已经解决所有挂起。

## LCP1 格式和已实现的策略

固定头 128 字节，最多 40 个 96 字节记录，总计 **3968 字节**。头部含版本/尺寸、main
writer ID、tick frequency/start、16 字节 main nonce、32 字节 recipe 和 CRC。记录含
连续序号、阶段、tick、result/arg0/arg1、可选 joined context、保留区及独立 CRC。

24 个阶段的 result 语义取决于相应 API：SDK 调用保存原 Result，bool API 保存布尔
返回值；它们不能混作同一种错误码。具体适配必须明确填入字段，原型不认证这些值的
物理来源。格式提供阶段槽，当前 native 样本只是受控模型序列，不是原 main 的全路径回放。

实现位于 `device/ep0_lifecycle_capsule.h` 和 `tools/a23_lifecycle_capsule.py`：

- 一个零初始化的 recorder 只允许 init 一次；writer 不匹配、倒退时间、重复 join、
  容量耗尽或终结后追加均不能产生新写入。
- quiet_enter 到 main_loop_left 之间禁止附加记录写入。主线程记录失败/保留不会打开
  Core 文本 logger，也不会调用任何所有权 getter 或资源释放函数。
- 只有两次已记录的成功 join 才允许 owner/保存阶段和 context；拒绝分支先检查门禁，
  不触碰传入的可选 context 指针。该规则不认证真实 join，仅约束所供观察序列。
- 每槽写一次；回调失败后禁用记录器。解析器保留有效前缀，区分全零尾部、缺口、部分
  记录和 CRC/顺序错误，不跳过损坏槽来拼接后面的记录。

CRC 和顺序检查不提供真实性认证。native 模型明确展示：最终 commit 失败时仍可留下
完整、可解析的槽，且有效槽数量可能比记录器收到成功返回的数量多一个。解析器始终
保持 own_commit_authenticated、physical_run_authenticated、join_results_authenticated、
cleanup_authorized 和 hardware_verified 为 false。reported_closed 只指有终结记录，
不是实际进程或资源已关闭。

## 验证范围与下一项

35 组 native 模型序列、11 项新增测试及 228 项相关回归全部通过，无失败、错误或跳过。
测试覆盖不同阶段前缀、join 失败前的不可访问 context、窗口内零附加
I/O、SD open/create 失败、写入每个位置的失败、完整字节与提交分离、容量、重复 init/
join、部分/损坏/错 recipe 和中间空洞。C 模型使用 ASan/UBSan，不调用 Switch SDK。
模型 recipe 为 `03` 后接 31 个零字节，不是任何真实运行的替代材料。

原型与同一 ELF 接入审查封存于 `private/analysis/A23-lifecycle-capsule-review-20261016`；
回归结果见同日 `A23-lifecycle-capsule-validation-20261016`。189 份来源摘要由旧 184
份加 5 个新源文件组成，旧输入不修改。

下一项是在新的隔离生成树接入主线程和精确的保存适配点，实现一次创建/预分配/
flush/readback/commit 的 SDK 文件适配；审查新文件服务对象的生命周期、同步 I/O
可能阻塞及额外持栈，完成真实 main/文件函数的故障回放与新 ARM ELF 验证。增加的
记录写入会改变停止后的 FS 时序，不能用它作为与旧候选严格单变量因果比较。
新 recipe/设备材料和接收器绑定须另做，当前入口/旧次数不适用于尚未存在的新候选。

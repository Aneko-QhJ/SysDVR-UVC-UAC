# quiet ELF 等待、静默与保存路径核验（2026-10-16）

已对[当前接收器绑定的 quiet 设备程序](A23_QUIET_RECEIVER.md)重新绑定实际指令、格式
地址、等待对象与保存调用。设备 ELF 仍是 56778e…，运行 recipe 仍是 ae65e7…，设备、
接收器及六项身份材料不改。15 项新增及此前 182 项相关回归合计 **197 项通过，0 失败、
0 错误、0 跳过**。

静默期间不进入格式化器或文本文件调用，logger 自身仍使用 832 字节。当前诊断 owner
不再包含生产捕获递归；在明确的条件及剖面替换下，视频入口加线程包装帧为 1504 字节，
音频入口加包装帧为 80 字节，main 为 4240 字节。它们不是完整线程上界或实机峰值。
NPDM 中 main 请求 8192 字节已绑定，实际线程预算仍未核实，不能据两数相减认证余量。

本轮没有设备执行、真实 SDK/IOKit、有效许可采集、USB/SD、打包、部署或签发次数。
三份实时票据和三份离线接收器记录均保持零次数；原 16.395292ms 超时原因仍未知。

## 方法和身份

[审查工具](../tools/audit_a23_quiet_paths.py)核验当前六项材料与封存接收器的身份关系，
用原工具重新生成反汇编，核对每条指令原字、符号边界及 SDK no-return 声明，重新解析
formatter dispatch、locale 和只读字面量。未复用旧 V3 地址证书或栈剖面数值。

13 个编译单元按封存参数重新预处理，得到 72 处源日志；新 ELF 绑定 65 处直接调用、
60 种格式。每种格式分别按 zero/limits/mixed 运行一次 quiet=false 和 quiet=true，
共 180 次恢复日志、180 次静默日志回放；恢复日志逐项与电脑 libc 的输出参考比较。
对实际两处诊断文件名、两处事件等待和线程 join 另作新地址核验。

冻结 180 份输入，包含上轮 177 份及本轮模型、工具、测试。编译工具、libnx、specs、
反汇编工具及使用的 SDK 声明摘要前后核对。模型解释 AArch64 指令，没有原生执行 ARM。

## 静默路径与主线程交接

[新模型](../tools/model_a23_quiet_paths.py)从实际 LogFunctionImpl 入口开始，执行可变
参数保存、ldarb、分支和返回。180 次静默回放均只经过 logger 的 32 条指令，栈帧
832 字节，没有函数调用；SP、callee-saved 寄存器与调用者栈参数恢复。静默标志字节
为注入值，未模拟处理器内存序、调度器或真实线程交错。

另外两组对照把传入格式地址改为无效指针，并将 TLS magic 置无效，分别设置 SD
已挂载/未挂载；静默路径仍返回。恢复路径的无效 TLS 则不能通过。恢复日志的 180 组
给定输入观察峰值为 2592 字节，保留 GetSize 失败不 Write、长度最多 511 字节的行为。
Open/Size/Write 故障、未挂载和预算耗尽等共 8 组对照保存。

这不是任意参数/locale/字符串/内存状态的证明。恢复日志依赖给定有效 TLS/reent、
默认 locale、映射及参数；文件系统返回为注入，未执行 SDK 文件指令或测量 I/O 时间。

主线程静默标志的两处 setter 与双 join 另按当前 main 指令核对：

- 开启静默的调用支配两处 LaunchThread，即所有到达启动点的已建 CFG 路径都经过开启。
- 两个 join 返回值分别保存在 w20/w21，经过 OR 和零判断；重新检查其到达定义，防止
  中间写入或错误常量被误当 join 成功。失败分支没有到达解除静默的路径。
- 解除静默只能在两个 join 成功后，且支配正常/诊断主文件及两处 EXE3 保存调用。

改变开启参数、成功分支、失败边或覆盖 join 返回值的负向模型均被拒绝。这个指令证据
仍假定 SDK 遵守 ABI、源级线程约定成立、有效内存且没有未知写入；没有认证真实调度。

## USB 与 join 等待

当前 eventWait 的单对象调用和 UvcDeviceProcessRequests 的三对象调用重新绑定计数、
Event.autoclear 到 Waiter.type 的实际构造，以及 waitObjects/SVC 指令。对所有 0/1
类型组合分别注入成功、超时、取消后成功、reset 重试，共 40 组；观察 waitObjects
入口以下最多 304/400 字节，没有进入间接回调。

threadWaitForExit 的实际单句柄、UINT64_MAX timeout 与 waitHandles 调用另行核对。
5 组注入成功、错误、超时、取消后成功及重复取消后成功，观察 waitHandles 入口以下
96 字节，SP 与 callee-saved 寄存器恢复。取消序列耗尽即拒绝，不把有限模型预算说成
真实等待时限。实际 join、内核返回值与线程句柄有效性未在设备上验证。

这些回放要求有效 Event/handle、给定类型、内核结果/index 和 ticks；SVC ABI 假定单列。
不能推广到未知回调类型、任意返回序列或内核/异常栈，更不能据此保证 16ms 或 30 秒内
完成 USB、join 或保存。

## 文件名和路径组合

实际 snprintf 两个调用点分别构造 `/ep0-%s.capture.bin` 与 `/ep0-%s.diagnostic.bin`，
容量 96，nonce 为终止的 64 字节小写 hex。每点取三组 nonce，6 次连续指令回放均恢复
栈，输出正确，入口以下观察峰值 1904 字节；不是所有 snprintf 输入的证明。

当前 ELF 下若干不含剖面替换的用户态前缀，可按静态 SP/直接调用/ABI 契约给出界限：
fsFsOpenFile 224、GetSize 192、Write 224、Close 176、threadWaitForExit 128、
Ep0ExecutionSaveJoined 784、AudioStreamThread 32 字节。均排除内核、异常和运行时耗时。

将明确标记的 quiet logger、恢复日志、等待对象及文件名剖面替换到其实际调用边：

| 入口与阶段 | 组合估计字节 | 含工作线程 48 字节包装帧 | 额外未解边 |
| --- | ---: | ---: | --- |
| VideoStreamThread，quiet=true | 1456 | 1504 | 在所列条件/替换下无额外未解边 |
| AudioStreamThread，诊断闲置 | 32 | 80 | 无额外未解边 |
| UvcDeviceProcessRequests，quiet=true | 1344 | — | 在等待剖面条件下无额外未解边 |
| main，quiet=false 日志作保守剖面 | 4240 | — | 在所列剖面条件下无额外未解边 |
| Ep0CandidateSaveCapture | 2512 | — | 在文件名剖面条件下无额外未解边 |
| Ep0CandidateSaveDiagnostic | 2560 | — | 在文件名剖面条件下无额外未解边 |
| Ep0ExecutionSaveJoined | 784 | — | 无额外未解边 |
| Ep0SessionStartupOnly | 400 | — | 无额外未解边 |

这里的“无额外未解边”是在所述替换/前提下，不是原始全调用图闭合证明。quiet worker
的图使用静默条件路径，main 则保守采用恢复日志剖面，不将整个 main 当成静默状态。
完整线程上界一律为 null；启动、异常、有效对象及实际预算等限制仍保留。

## 封存和下一步

本轮于 2026-10-16 完成封存，目录沿用开始审查时的 10-15 标识。
审查 `private/analysis/A23-quiet-paths-review-20261015`，214 条 manifest，摘要
`90e0304363fce9c97dd8613279174eed2fba74900943621ba40e880ed900b7b3`。
验证 `private/analysis/A23-quiet-paths-validation-20261015`，12 条另行封存，保存 197 项
回归、就绪边界、实时记录、输入和旧封存核对。[15 项检查](../tests/test_a23_quiet_paths.py)
覆盖当前身份、静默/恢复、交接指令漂移、等待、文件名以及“不提升为完整线程证明”。

此前 23 份封存共 7081 条复核；旧 177 份研究输入、七份生产文件、三份实时票据及
三份 offline-record 保持。设备/接收器程序、六项材料和现有记录不改。

下一项整理**一次独立接口 2 分支诊断的准备方案**：接收器预等待、设备启动及 30 秒
窗口的操作时序，首次 STATUS/突发的可观察顺序，join 后材料收集，失败停止及结果
判读标准。静默/隔离负载与新身份链已有离线证据；实机分支、同步耗时和真实栈状态
仍只能作为待观察量。准备方案不签发次数，也不复用原失败次数。

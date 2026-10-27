# ELF函数边界与异常出口审查（2026-10-14）

新的独立分析器按ELF符号类型/大小组织实际指令，不再把所有反汇编标签当作函数。两封存候选各核对396个FUNC符号、394个唯一入口，357个有声明大小、37个大小为0；4个局部标签并入所在范围。cache flush的循环和ret可以完整分析。异常尾部则保留两种结果：不采用SDK“不返回”约定时继续报告未知；采用明确绑定的约定时仅计算进入异常/内核之前的用户态栈前缀。

20项新Python检查、479项相关回归通过，无跳过。本轮只读两封存ELF并在电脑解析字节，没有新ARM构建或执行、native设备函数回放、打包、USB/SD访问。生产/候选runtime/旧格式/历史封存和三份票据保持，remaining=0，首次SDK burst根因仍未知。

## 函数范围来自符号，局部标签不另起函数

分析器直接读取ELF64 little-endian AArch64的section和完整symbol table，再与readelf完整FUNC列表逐项比对名称、地址、大小、绑定与section。非零大小的STT_FUNC按声明范围取指令；LOCAL NOTYPE标签仅作为范围内标签，不能自动升级为函数。396个符号中，memcpy/memmove和fsFileGetSize/localalias各共用一个入口，因此共394个唯一入口。前者一个alias大小为0，但同地址另一个FUNC有556byte声明大小，采用明确大小。

零大小FUNC只得到“下一FUNC或可执行section末尾”的范围上限，不把它描述成符号声明长度。沿控制流仍必须找到完整指令、匹配SP或真实终结边；遇到缺口、动态/不支持的SP写入、未知间接边、范围外跳转或.su不一致就保留未知。重叠/越界范围拒绝，不根据名字猜测合并。所有解析到的反汇编instruction word均与ELF可执行section里的实际4byte比较，重复指令或字节变化拒绝。

armDCacheFlush是大小为0的FUNC；armDCacheFlush_L0是LOCAL NOTYPE，循环及ret位于后者块中。合并范围后该入口用户态SP为0，循环不累积SP。这里只闭合用户态直接指令图，不包含cache操作可能触发的异常栈，不测运行时间或DMA安全。

## “不返回”只能作为已列出的条件

分别保存三份调用图：仅符号范围、符号范围加SDK“不返回”约定、再加上轮按调用点绑定的n=1/n=3句柄profile。无约定的图不会因为看到fatal名字就删边。新policy绑定确切ELF和function摘要，以及本机svc.h、diag.h、fatal.h、types.h；核对NX_NORETURN宏和五个声明：diagAbortWithResult、fatalThrow、svcExitProcess、svcExitThread、svcReturnFromException。SDK/ELF/指令/字段变化会拒绝复用。

svcExitProcess、svcExitThread、svcReturnFromException机器码都是对应svc后紧接ret，不能从“没有ret”证明不返回。采用policy时在svc处停止用户流，依赖的是SDK/内核约定，内核未实际测量；异常或内核内继续执行的栈不包含在这些数字里。svcBreak声明返回Result，始终不在“不返回”集合内；fatalThrowWithPolicy也不在集合内，因为SDK明确允许它随policy返回。

diagAbortWithResult的FUNC大小28byte，最后是调用svcBreak，紧随范围外的word为udf #0。分析器不把padding强行纳入函数，也不把svcBreak本身改成“不返回”。只有明确采用diagAbort的声明/已核对边界时，才在该用户态边界结束；不开policy继续列falls outside。可达trap、假定“不返回”函数内可达ret、未知目标或SP错误仍不闭合。

| 入口 | 新结果 | 条件与限制 |
| --- | --- | --- |
| armDCacheFlush | 用户态SP 0byte | 合并实际LOCAL标签；不含异常栈 |
| __syscall_getreent | 用户态前缀48byte | 包含TLS错误→diagAbort分支，依赖diagAbort约定；不是仅正常TLS路径的数字 |
| diagAbortWithResult | 用户态前缀32byte | 终止在异常/内核之前；不等于实际abort峰值 |
| fatalThrow | 用户态前缀224byte | 保留fatalThrowWithPolicy的可返回行为，依赖svcExitProcess约定 |
| session_capture | 原352byte保持 | 不需要新增“不返回”约定 |
| Ep0SessionSaveJoined | 原768byte保持 | 不需要新增“不返回”约定 |

TLS取reent实际先检查线程TLS标记，不匹配才进入abort；本轮没有把“合法TLS”作为剪枝条件，也未验证主线程/worker启动全过程的TLS发布。SDK约定、摘要和符号只提供条件与一致性，不认证来源，不证明实机异常行为或允许清理资源。

## 完整线程仍未闭合，但缺口已收窄

采用上述明确约定与既有wait调用点profile后，main、__appInit、__appExit剩余未知都集中于_svfprintf_r的两条间接指令。视频/音频另各保留CaptureReadVideoFrame/CaptureReadAudioFrame递归边，分别共3条未知。原falls outside、cache flush标签与waitObjects未知不再出现在这份条件图中；未经SDK约定的图仍保留异常尾部缺口。

两配置视频已知用户态profile路径仍为3600/3616byte，音频3120byte，main4592byte；这是已遍历路径，不是完整上界、实际峰值或线程栈余量。含具体wait回放的入口也不会升级为全输入证明，所有线程根的整体栈上界保持未知。没有删除采集递归、启用音频、修改logger或USB timeout。

两条格式化未知指令的附近机器码已经保存：blr x23之前通过__getreent及默认指针选择后，从对象偏移464读取x23，再调用__locale_mb_cur_max；br x1之前则从只读表取有符号halfword，结合adr基址计算分派目标。下一步应分别核对该函数指针的初始化/选择与只读分派表的索引范围、目标集合，不能仅凭当前日志没有浮点格式就忽略它们。真实newlib ABI、默认/线程locale与TLS有效性仍待绑定。

采集重试的有限性仍只在单worker/有效生命周期前提下成立，详见[上一轮审查](A23_THREAD_PATHS.md)。当前UAC禁用，电脑共享标志竞争不是本次实机或burst根因证据。失败FS、启动细阶段预算、部分线程和回滚是另行未完成项；当前票据不能由电脑结果续期。

## 可复核材料

- [独立ELF分析器](../tools/analyze_a23_elf_boundaries.py)、[只读审查工具](../tools/audit_a23_elf_boundaries.py)、[20项新检查](../tests/test_a23_elf_boundaries.py)。
- [审查结果](../private/analysis/A23-elf-boundaries-review-20261014/audit.json)、[审查摘要](../private/analysis/A23-elf-boundaries-review-20261014/SHA256SUMS)。
- [验证结果](../private/analysis/A23-elf-boundaries-validation-20261014/validation.json)、[完整回归](../private/analysis/A23-elf-boundaries-validation-20261014/regression.txt)、[验证摘要](../private/analysis/A23-elf-boundaries-validation-20261014/SHA256SUMS)。
- [线程/采集前提](A23_THREAD_PATHS.md)、[等待与独立保存入口](A23_WAIT_FIXED_PATH.md)、[进度交接](PROGRESS_HANDOFF.md)。

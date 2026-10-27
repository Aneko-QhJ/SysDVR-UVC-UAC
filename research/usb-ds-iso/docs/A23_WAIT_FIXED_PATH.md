# SDK句柄等待与定长关联路径候选（2026-10-14）

在新的隔离候选中，用定长拼接生成原REL1路径，移除关联文件adapter对snprintf的依赖。保存函数自身栈由560降到480byte，最终ELF的保存直接调用图闭合，入口累计用户态SP上界768byte；原91项启动/退出/文件/容量观察与文件名逐项保持。另沿实际SDK等待机器码核验单事件参数、数组分配、返回与重试边界，未修改等待实现或timeout。

两窗口各完整链接13对象ELF，未执行/打包/部署。91项原场景加262项定长路径检查共353项native通过ASan/UBSan；每配置156组SDK机器码回放，共312组；14项新增与443项相关Python回归无跳过。SDK回放只在电脑解释封存指令并注入SVC/tick，没有运行ARM或访问USB/SD。生产/旧runtime/格式/历史封存/三票据保持，remaining=0，根因未知。

## 定长路径与保存调用图

原路径固定为`/ep0-` + boot/session各16byte的64个小写hex字符 + `.session.bin`，共81字符和结尾NUL，82byte足够。新helper核对容量、两nonce非零、地址范围和输出别名，拒绝时输出原样；成功直接写固定前缀、hex和含NUL后缀。256组轮换byte样例与旧格式化路径逐字节相同，另覆盖短容量、零/NULL nonce与两种别名。

仅新源码树里的ep0_session_file.c与recipe改变，加入独立path header；main、worker、callback、startup/session runtime、DIA1/normal sink、handler、admission和wait源码保持。关联保存仍在原DIA1成功后一次尝试；失败join/初始化失败/原DIA1失败不追加FS操作。关联文件自己的commit不写进保存前的REL1，成功/失败均按原门槛保留资源，不授权清理，不覆写/删除/重试。

| 链接/栈观察 | 两配置结果 |
| --- | --- |
| 保存函数自身.su/机器码SP | 480byte，原560byte |
| Ep0SessionSaveJoined入口直接调用图 | 闭合，768byte；最长已知链经read→fsFileRead→sessionmgrAttachClient→condvarWaitTimeout→mutexLock |
| session_capture入口 | 原352byte保持 |
| 相对上一session候选text/data/BSS | +240 / 0 / 0 byte |
| 完整对象数 | 13 |

代码段增加240byte来自新路径helper及校验，不能称为整体体积缩小。logger与旧diagnostic/normal adapter仍使用通用格式化，相关库仍链接在ELF；新保存入口已经不再可达snprintf/_svfprintf_r或其间接调用。这次768byte包含该入口及SDK直接callee的用户态栈，不含caller已占用栈、异常/内核或实际峰值；完整线程图仍未闭合，不能据此宣称线程栈足够。

## 实际等待参数与类型

本机SDK event.h定义waiterForEvent只生成Handle/HandleWithClear。最终ELF的eventWait读取Event.autoclear并存入Waiter.type，在唯一waitObjects调用前明确把w2置为1；其自身SP为48byte。条件是Event由合法API初始化、字段未损坏且调用期间对象有效，此时类型只能0/1。通用Waitable类型2的vtable回调不属于这个单事件profile，不能由本审查给出其上界。

实际最终ELF列出11处eventWait调用点，覆盖控制IN/OUT、SETUP/ISO处理、视频/音频发送和usbDsWaitReady。源中EP0 wait/poll均传单个Event；各超时值保持。threadWaitForExit另走waitHandles，不经过通用Waitable回调：wrapper32byte、waitHandles自身80byte，svcWaitSynchronization wrapper16byte，局部直接链128byte；不证明线程已退出、join成功或有限时间内返回。

## SDK动态分配与回放边界

封存waitObjects机器码先保留224byte固定frame，再预备`4*n`的Handle数组及`48*n`的node数组，各按16byte对齐；对象数超过64在动态分配/SVC之前返回0xEE01。有效单事件n=1时，函数自身为224+16+48=288byte；等待SVC wrapper另16byte，入口累计304byte，连eventWait自身48则为352byte。即使类型0/1从不调用node方法，通用函数仍预留node数组。

新模型解释实际AArch64指令、条件码、寄存器、栈读写与直接调用，SVC返回与counter tick由fixture注入。每配置156组包括对象数1..64的两种句柄类型128组，另覆盖0/有限/无限timeout、0xEA01/0xEC01/其他错误、clear返回0xFA01后的重试、100次连续取消及对象65拒绝。所有受测合法路径返回时SP恢复，间接callback未触达；最大64对象纯句柄profile为3552byte函数frame，加SVC为3568byte。它不适用于任意Waitable或损坏对象。

模型对未知指令、未知函数/间接目标、未初始化内存、耗尽返回序列或指令预算直接拒绝，不以预算到期声称设备停止。它是具体profile回放及机器码形状核对，没有做全部输入的符号证明，也没有执行真实kernel行为或验证ABI之外的异常。

## 重试与停止时延

在受测SDK机器码中，0xEC01进入同步等待的重试路径；即使timeout=0，100次注入该结果后仍会调用第101次等待SVC。每次重试先恢复动态数组前的SP，因此栈不累积；有限/无限timeout和clear失败路径也核验恢复。这里的“取消”是kernel同步等待Result，不能等同USB URB取消、DMA释放或IOUSBHost Aborted。

因此局部栈可收敛，停止时延仍无已验证上界；本回放没有证明实际发生连续取消。线程可能阻塞、wait helper内部重试、日志/服务调用和真实HOS调度仍需证据。没有修改SDK、扩大timeout、强制cancel/close或增加查询来消除这些未知，也不能据此解释首次SDK burst的16.395ms timeout/seq0。

## 证据与下一步

- [定长路径](../device/ep0_session_path.h)、[独立新adapter](../device/ep0_session_fixed_file.c)、[路径交叉检查](../tests/ep0_session_path_test.c)、[SDK指令模型](../tools/model_a23_wait_machine.py)、[构建/复核工具](../tools/build_a23_wait_path_candidate.py)、[Python检查](../tests/test_a23_wait_path_candidate.py)。旧[关联候选](A23_SESSION_ARM_CANDIDATE.md)与[并发/栈审查](A23_SESSION_CONCURRENCY_STACK.md)仍为独立封存输入。
- [审查audit](../private/analysis/A23-wait-fixed-path-review-20261014/audit.json)、[manifest](../private/analysis/A23-wait-fixed-path-review-20261014/SHA256SUMS)：两新ELF/源码/map/recipe/反汇编/调用图、353项native、312组等待机器码回放与SDK头文件hash/快照。
- [验证摘要](../private/analysis/A23-wait-fixed-path-validation-20261014/validation.json)、[manifest](../private/analysis/A23-wait-fixed-path-validation-20261014/SHA256SUMS)：443项回归、源码/生产快照、三票据、旧封存和文档链接。

下一步电脑把单事件的参数/类型约束接到更完整的线程调用图，明确SDK异常终止和旧logger格式化的前提；需要区分局部用户栈、实际峰值与停止时间。startup细阶段/64条预算、失败FS/部分线程/借用条件和初始化回滚仍未处理，不能凭局部上界放行资源清理。真实DMA/终结、join、成本、SD持久性与来源认证未测，仍不开放实机入口。

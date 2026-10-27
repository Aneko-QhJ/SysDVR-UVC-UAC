# A23 原生PID窗口与SIGINT暂缓对照（2026-10-22）

后续：[子进程信号恢复与就绪门槛](A23_CHILD_SIGNAL_POLICY.md)完成579来源、两轮20场景与78测试。普通child的临时INT屏蔽在Python启动后恢复，就绪后再发送取样请求；仍不是pre-exec原子政策。以下保留本阶段。

本阶段新增 tools/a23_sigint_guard_owner.py、tools/audit_a23_sigint_guard.py、tests/test_a23_sigint_guard.py 共3来源，总计575，原572来源逐字节保持。它是研究原型，原pre-retained类、旧worker/取样器/分类器与生产入口均保持。

当前CPython 3.13.16中，_execute_child的真实_fork_exec调用之后才执行STORE_ATTR pid，随后登记_child_created。本轮固定subprocess.py源码、_execute_child字节码和_posixsubprocess原生镜像SHA256及原始字节。选定9个场景实际走到_fork_exec，每场景1次；不能把_USE_POSIX_SPAWN/VFORK配置值当作所有平台路径均已验证。

候选限定在Python主线程、active_count为1且SIGINT仍为default_int_handler时启动。在进入构造器前保存当前thread mask，然后临时屏蔽SIGINT；先前预保留对象继续负责实际构造。结束时恢复原mask，并再次读取mask验证。恢复发生的KeyboardInterrupt单独记录；如果构造器先有主异常，仍传播原对象。恢复失败或复核失败保留原mask供显式finish重试，不宣称已恢复。没有替换用户handler，也没有屏蔽所有异常或所有信号。

| 每轮安排 | 实际观察 |
| --- | --- |
| normal | 原始normal文件字节匹配，owner wait，模型采样通过 |
| 无guard，真实native返回处SIGINT | child已创建但pid仍未登记，原型creation_unresolved；审计直接wait本次原生返回身份 |
| guarded，native返回处SIGINT | SIGINT保持pending，完成PID登记后恢复mask时递送，owner直接wait，采样失败 |
| guarded，向本进程递送SIGINT | 本fixture同样延后，不能据此认证任意OS线程的进程信号分配 |
| guarded，STORE_ATTR pid前SIGINT | 实际opcode暂停处信号pending，登记完成后递送，owner wait |
| guarded，同一opcode直接抛Python异常 | 同步异常不被信号mask挡住，pid未知，候选仍unresolved |
| guarded，初始化前SIGINT | 信号pending后构造继续，登记后递送，owner wait；不是取消原生创建 |
| 原已屏蔽SIGINT | 原mask与pending保持，未递送的信号未被候选吞掉，采样按原mask完成；审计随后仅消费自己的测试信号以恢复环境 |
| 同步主异常加pending SIGINT | 恢复mask又触发KeyboardInterrupt，原主异常对象保持；候选pid未知，审计wait |

暂缓SIGINT会让原生创建继续进行，之后才传播中断；这是一种经过指定点验证的延期语义，不能说收到SIGINT便没有创建child。同步Python异常、其他信号、任意指令时刻、内存错误和整进程死亡都不因此获得原子性。

每轮9实际child：6通过候选保留的Popen对象直接wait，另3是实际已创建但pid未登记的负对照。后者不是上一阶段“没有执行原生创建”的半初始化模型。审计在包装真正_fork_exec时直接保留其新返回值，因此知道自己刚创建的child身份；它只对这个尚未回收的直接child执行waitpid，成功路径没有向这些child PID发信号。它没有读文件/消息/journal的PID，也没有把这个token交给候选作为恢复接口。

负对照构造器错误分支关闭stdin后，固定worker退出2；审计记录实际wait码。候选自身保持creation_unresolved、direct_wait_verified=false，不因外层审计已wait而被升级。辅助wait的超时兜底只用于审计当前直接创建且尚未reap的token，触发便会使审计失败；不提供日志PID清理或自动恢复功能。本轮成功路径未触发该兜底。

两轮主回放共18child（12候选Popen wait、6审计fresh-native-return wait），全部由实际创建者wait，未新增孤儿。主回放中所有原thread mask均精确恢复，所有已登记管道关闭。预先屏蔽SIGINT的控制保留pending，候选不调用sigwait；只有审计finally消费它自己注入的测试信号，避免污染后续测试。

另做两个实际child构造probe，分别直接调用unguarded和guarded的_create，并由保留对象完成communicate/finish。unguarded child报告mask为空，guarded child报告SIGINT仍屏蔽；两者父mask均已恢复，两个child均exit0并直接wait。这证明当前guard改变child启动时的信号掩码，恢复父mask不会恢复child。本轮没有补child mask政策，也没有把该差异当作可忽略的生产条件。合计主回放与probe共20实际child/20创建者wait。

新26项、pre-retained回归26项、保存窗口回归26项，共78测试通过。单元还覆盖非主/多Python线程或非默认handler拒绝、恢复失败与query失败保留saved mask、错误线程恢复拒绝、纯判定无文件/信号IO、未登记审计wait不升级候选。所有失败安排无cache/report/classification；只有normal与调用前本就屏蔽SIGINT的控制返回正确历史字节，task_complete与生产/物理权限始终false。

575来源搬移回放具有相同9安排归一语义，normal历史anchor/字节保持，Python源码、字节码和原生镜像一致。原始退出码各自保存，跨位置仅归非零类；inode/时间/响应摘要只在各自证据内核验。只读verify在Popen/settrace/mask/wait均被阻断时通过，CLI正确/错误/缺pin返回0/2/2。父审计hook观察原checkout或/Volumes打开0，但不继承到子进程，不能认证OS隔离或来源。

边界：pthread mask仅是当前线程状态；active_count=1检查普通Python线程，不证明没有其他原生线程。默认handler、指定插入点及当前二进制的结果不能外推为任意process-directed信号、线程、程序或运行时保证。mask复核本身也未穷尽任意异步指令中断。SIGTERM、SIGKILL、创建者或外层监督者整进程死亡、全局nonce、断电、OS能力隔离、原子spawn/exec与硬实时仍未认证。child继承屏蔽这一差异未修正，当前guard不应作为通用process manager或生产broker。

原572来源、23保护文件、实际49/65账本、失败owner/state保持；旧228 actor和14孤儿回收不追认。65已回收/remaining0，81..112未正式保留；USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，生产采集关闭，SDK超时根因未知。

证据：

- review：private/analysis/A23-sigint-guard-review-20261022-r1
- review SHA256SUMS：5176f730edda62eddb851c99c00bf28a126ee52caf7b86864149179b50218305
- validation：private/analysis/A23-sigint-guard-validation-20261022-r1
- child mask probe：validation内probe_a23_sigint_inheritance.py及a23-sigint-inheritance.json
- closeout：private/analysis/A23-sigint-guard-closeout-20261022

只读重验：

```sh
/opt/homebrew/bin/python3.13 -B research/usb-ds-iso/tools/audit_a23_sigint_guard.py --check research/usb-ds-iso/private/analysis/A23-sigint-guard-review-20261022-r1 --expected-sha256 5176f730edda62eddb851c99c00bf28a126ee52caf7b86864149179b50218305
```

下一步离线定义并验证child初始信号mask与终止政策，处理当前已测出的继承差异；不能只恢复父mask便声称整体恢复。同步异常与创建者进程死亡仍是独立缺口，不接生产或硬件。

前序：[启动前预保留进程对象](A23_PRERETAINED_OWNER.md)。

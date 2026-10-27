# A23 Popen保存窗口与外层直接归属对照（2026-10-22）

后续：[启动前预保留进程对象](A23_PRERETAINED_OWNER.md)完成572来源、两轮12安排和78测试。独立候选覆盖指定构造器/PID已登记窗口；原生创建至PID登记及创建者整进程退出仍未验证。以下保留本阶段的负对照。

本轮新增4来源共569，原565来源逐字节保持。源码为 tools/a23_spawn_boundary_owner.py、tests/a23_spawn_boundary_actor.py、tools/audit_a23_spawn_boundary.py、tests/test_a23_spawn_boundary.py。原SamplerOwner、固定worker、取样/分类器、旧现场票据和生产入口保持；新子类仅供离线验证。

已核对当前运行的CPython 3.13.16，保存subprocess.py完整字节、SHA256、SamplerOwner.capture源码摘要、字节码摘要与反汇编。目标由实际STORE_ATTR child、STORE_ATTR streams及spawned状态STORE_SUBSCR定位，而不是按猜测的行号中断。结论绑定这个本地运行时，不外推到其他Python或SDK。

| 保存窗口安排 | 实际观察 |
| --- | --- |
| 调用Popen前抛中断 | child0，slot为空，不声明wait |
| 真实Popen返回后、受信任包装返回前抛中断 | 已创建1child，但slot为空；外层已保留真实句柄，负责终止与wait |
| CPython执行STORE_ATTR child前opcode中断 | 同样已创建child而slot为空；外层句柄救援wait |
| STORE_ATTR streams前opcode中断 | child已保存，旧owner完成wait；但实际stdin/stdout两管道仍开，报告pending_streams0且closed |
| spawned状态赋值前中断 | child和管道已保存并清理，即使报告spawned仍false，不能按该字段推断无child |
| after_spawn指定点中断 | 旧owner正常清理并wait，作为已初始化对照 |
| 新隔离子类，同一streams赋值中断 | 从已保留的child.stdin/stdout/stderr按对象身份补齐列表，两管道完成关闭，wait保持 |

前三类负对照都使用测试外层保留句柄。它们没有制造未回收子进程，也不能说旧owner已经找回保存前丢失的句柄。旧closed观察与资源事实矛盾已保留。隔离修正只覆盖已保留child时管道列表未登记的问题，没有关闭Popen返回到slot保存之前的窗口，也没有修改旧封存或生产实现。

本地subprocess的析构器会观察运行状态并可能把对象加入内部活动列表；这不是应用owner的句柄交接协议，也不证明进程退出时完成了指定清理或wait。新结果不把内部回收机制当作应用的授权或生命周期证据。构造器内部原生创建、pid登记与任意异步指令间隙本轮未穷尽。

第二组是外层直接归属对照。外层进程直接Popen并保留请求者与sampler的真实句柄；请求者只持有lifeline写端并发请求，sampler持有读端与受控gate。这里请求者不是旧SamplerOwner进程，也不是sampler的OS创建者。明确改变拓扑，才能在请求者整进程os._exit(79)后仍由活着的外层直接wait两者。

sampler首先报告ready并等待gate，之后复用冻结的真实目录取样器。释放gate或取样指定暂停点继续前，若lifeline可读即拒绝；本仪器不写lifeline，已wait的请求者退出使它变为EOF。拒绝返回86，完整采样返回旧wire并exit0。中途的after_open和最终validated暂停点均覆盖。最后一次检查之后仍可能发生变化，不声称原子地排除请求者死亡。

| 外层对照安排 | 观察与验收 |
| --- | --- |
| normal | 两个直接子进程均exit0/wait，normal历史文件字节一致，仅当前诊断模型完成 |
| 请求前或请求后退出 | 请求者实际79/wait，没有创建sampler |
| sampler已创建、owner记录缺失/半写/完整后退出 | 外层句柄始终已持有；记录原始字节封存，三者均sampler86/wait，不恢复采集 |
| 读取中或最终validated后请求者退出 | lifeline检查拒绝86，输出为空，两个直接句柄均wait |
| sampler完整wire且已exit0/wait后请求者退出 | wire仍正确、旧分类commit关联完整，但请求者79使外层模型失败，样本不接受 |

owner-record.bin仅是临时对照材料，缺失、半写或完整都不授予信号/清理权限。所有清理只作用于外层实际创建并保留的Popen对象，没有journal PID查询或信号。原始wire按外部anchor/pin在父侧重新解码并与normal历史文件逐字节比较；请求者死亡后的完整wire保存作失败证据。

这组对照覆盖的是请求者退出、外层创建者存活的情况。原SamplerOwner整进程崩溃时它自己创建的child如何回收，仍未实验认证；外层自身崩溃、任意后代、跨进程句柄转移与完整broker也未实现。不能拿当前两个wait结果追认旧拓扑崩溃恢复成功。

最终16安排（7窗口+9外层），每轮22新child：6窗口child、9请求者、7外层sampler。窗口中4个由owner wait，2个由受信任外层句柄救援wait；其余16个均外层直接wait。最终原位置与搬移两轮共44child全部wait，归一语义相同；actual负退出码在各自报告保留，比较时仅归为信号终止。wire内inode/时间观察会随目录不同，因此仅在各自证据内核验SHA256，不要求跨目录相同。

开发R1/R2/R3另66child也全部wait，原版本review与日志封存在validation/preliminary。R2的半记录测试把预期半长度写成常数13而实际为14，造成一项断言失败；原失败日志保留，不追认26测试通过。修正为按实际长度计算后R3通过，R4增加跨位置语义归一后通过并完成搬移。含开发回放共110child/110wait（45请求者、65sampler），没有新增孤儿；不把不同源码版本拼成同版本重复性证明。

最终选择的新26项、owner回归26项、deadline回归26项，共78测试通过。纯判定在文件/进程IO被阻断时通过；只读verify在Popen、settrace、exercise被阻断时通过，CLI正确/错误/缺pin返回0/2/2。复制源码、normal历史anchor与文件字节、运行时源码和字节码一致。父审计hook观察到原checkout和/Volumes打开0，但不继承到子进程，不能据此认证来源或OS能力隔离。

当前只是离线候选和受控反例，所有任务/生产/物理权限false。原子spawn/exec、来源、OS隔离、全局nonce、断电、目录原子快照、硬实时、真实SDK/时钟/quiet drain/permit均未认证。旧228 actor和14孤儿回收结论保持未知；23保护文件、实际49/65账本及失败owner/state保持。65已回收/remaining0，81..112未正式保留；USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，生产采集关闭，SDK超时根因未知。

证据：

- review：private/analysis/A23-spawn-boundary-review-20261022-r4
- review SHA256SUMS：ecc5b4bb82815eca77b387b82750e5111fa8ac8f688534f57994d795ccbd49f8
- validation：private/analysis/A23-spawn-boundary-validation-20261022-r4
- closeout：private/analysis/A23-spawn-boundary-closeout-20261022

只读重验：

```sh
/opt/homebrew/bin/python3.13 -B research/usb-ds-iso/tools/audit_a23_spawn_boundary.py --check research/usb-ds-iso/private/analysis/A23-spawn-boundary-review-20261022-r4 --expected-sha256 ecc5b4bb82815eca77b387b82750e5111fa8ac8f688534f57994d795ccbd49f8
```

下一步离线评估预保留进程对象或独立创建者以缩小保存前窗口，并单独验证外层监督者失联；不能据此开放sampler broker、生产或硬件。

前序：[调用者中断与运行时句柄交接](A23_TERMINAL_OWNER.md)。

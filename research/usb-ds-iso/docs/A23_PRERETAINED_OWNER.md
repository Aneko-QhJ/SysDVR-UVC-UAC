# A23 启动前预保留进程对象（2026-10-22）

后续：[原生PID窗口与SIGINT暂缓对照](A23_SIGINT_GUARD.md)完成575来源、两轮9安排与78测试。SIGINT暂缓覆盖指定信号安排，同步异常仍有真实未登记child；child还继承SIGINT屏蔽，尚不能作生产候选。以下保留本阶段。

本阶段新增 tools/a23_preretained_owner.py、tools/audit_a23_preretained_owner.py、tests/test_a23_preretained_owner.py 共3来源，总计572，原569来源逐字节保持。原owner、上一轮隔离管道修正、固定worker/取样器/分类器、实机票据和生产入口不变。

已实现一个绑定本地CPython 3.13.16的离线原型：在原生进程可能创建之前，以Popen.__new__分配Python对象并存入slot.child，再调用Popen.__init__。外层创建表达式仍有STORE_ATTR child，但赋值之前slot已经保留这个同一对象。外层copy的capture只替换创建调用，并保存构造器检查点；原期限、传输、分类与失败策略保持。生成脚本和生成后的完整源码均封存，未动态执行生成代码作为生产入口。

预留对象的存在、构造器是否进入、PID是否登记、是否wait必须分开。原型使用运行时对象自身正整数PID字段判断能否进入Popen的进程方法，不从journal或JSON取PID。PID尚未知时只关闭已能找到的流对象，保留creation_unresolved，绝不对半初始化对象调用terminate/kill/wait。这个状态不证明child不存在，也不证明存在真实待回收child。

| 每轮安排 | 验证结果 |
| --- | --- |
| normal | 历史normal文件逐字节相同，exit0/直接wait/管道关闭，只有模型采样通过 |
| 分配前中断 | 对象0、原生调用0，未创建child，原异常传播 |
| 分配后、初始化进入前中断 | 对象已保存，但原生调用0；可确认尚未启动，不冒认wait |
| 标记初始化进入后、实际调用前中断 | 原生调用0的受控场景，仍保守记creation_unresolved并保留对象，不据缺PID推断不存在child |
| __init__完成后检查点中断 | 原对象已保留，直接清理/wait，原异常保持 |
| 外层STORE_ATTR child前中断 | 已保留同一对象，不再像旧负对照那样丢失进程对象；无需外层救援 |
| 外层STORE_ATTR streams前中断 | 复用上一阶段的对象流发现逻辑，完成wait及流关闭 |
| 包装__init__实际完成后抛KeyboardInterrupt | 同一已初始化对象保留；原异常传播，直接wait |
| 包装__init__实际完成后抛EIO | 接收失败且无缓存，原对象直接清理/wait |
| _execute_child完成后、__init__返回前中断 | PID已登记；原构造器错误分支关闭流，owner仍通过保留对象直接wait |
| PID已登记、_child_created标志赋值前opcode中断 | 实际_child_created仍false但PID有效，保留对象的terminate/wait成功；不能只按该布尔标志断言无child |
| 未登记PID的半初始化模型 | 仪器没有执行原生创建，仍保留未知、不调用PID方法，不当成已回收 |

每轮12安排、实际8个新Python child，全部由原型owner直接wait，无外层句柄救援。两轮16child/16wait，已登记stdin/stdout/stderr流都已关闭。另两轮共4个无PID控制不执行原生创建；它们的保留对象与未知结论属于保守行为验证，不是对真实已创建但未登记child的恢复证明。

测试以当前capture和_execute_child实际字节码定位STORE_ATTR，运行时记录包含subprocess.py字节/SHA256、Python版本、capture源码/字节码摘要及_execute_child字节码摘要。原异常对象在指定KeyboardInterrupt安排中保持，EIO路径返回失败；失败安排没有cache/report/classification。原始wait码保存在报告，跨位置仅把非零退出归一，不把退出码归一当作成功。

新26项、上一轮保存窗口26项、owner回归26项，共78测试通过。单元覆盖未知初始化时PID方法阻断、无PID状态不能改判closed、BOOL退出码拒绝、纯判定无文件/进程IO、未实现handoff明确拒绝。该原型不继承旧handoff去构造旧类，避免静默丢失新状态语义；当前仅同一owner对象继续finish，没有新的交接实现。

572来源搬移在同一运行时回放相同12安排，归一语义一致，历史normal anchor/文件字节保持；inode/时间和响应摘要只在各自证据中核验。只读verify在Popen、settrace和exercise被阻断时通过；正确/错误/缺pin CLI返回0/2/2。父审计hook没有观察到原checkout或/Volumes打开，但不继承到子进程，因此来源与OS隔离不获认证。

原生创建仍有未闭合窗口：本地_execute_child中_fork_exec返回后先把返回值写入self.pid，再置_child_created。对象已提前存在，并不保证原生调用返回至PID保存之间的异步中断可恢复；本轮没有在原生已创建但PID未登记时注入真实中断。初始化中也可能已有尚未登记为流对象的原始FD，当前对象发现机制不证明这些FD全部可回收。所有指定opcode证据均绑定当前CPython，不能外推为任意指令/信号/调度或硬实时保证。

创建者整个进程退出也仍未解决：预留对象和slot都在同一个Python进程里，未引入独立的进程创建者、OS回收能力或持久句柄转移。本轮没有新增实际创建者崩溃实验。前阶段外层直接拥有两子进程只覆盖请求者死亡、外层存活，不能替代实际创建者或外层监督者自身死亡的证明。磁盘状态不恢复清理权限，未知初始化也不得按journal PID发信号。

该类的显式__new__/__init__拆分是研究原型，依赖当前运行时的对象布局/初始化顺序，不是通用subprocess替代接口或生产broker。来源、原子spawn/exec、OS能力隔离、全局nonce、断电、目录原子快照、真实SDK、时钟/quiet drain/permit仍未认证。旧228 actor及14孤儿回收不追认；23保护文件、实际49/65账本、失败owner/state保持。65已回收/remaining0，81..112未正式保留；USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，生产采集关闭，SDK超时根因未知。

证据：

- review：private/analysis/A23-preretained-owner-review-20261022-r1
- review SHA256SUMS：09240df46bad3fddb9c97dd98cd2b1ef63f29bcf1ffa7f72e4551daee967101b
- validation：private/analysis/A23-preretained-owner-validation-20261022-r1
- closeout：private/analysis/A23-preretained-owner-closeout-20261022

只读重验：

```sh
/opt/homebrew/bin/python3.13 -B research/usb-ds-iso/tools/audit_a23_preretained_owner.py --check research/usb-ds-iso/private/analysis/A23-preretained-owner-review-20261022-r1 --expected-sha256 09240df46bad3fddb9c97dd98cd2b1ef63f29bcf1ffa7f72e4551daee967101b
```

下一步离线核对_fork_exec返回至PID登记与信号递送的边界，或评估独立创建者。创建者整进程死亡是另外的责任边界，不能通过继续增加同进程Python引用来宣称解决；不接生产或硬件。

前序：[Popen保存窗口与外层直接归属对照](A23_SPAWN_BOUNDARY.md)。

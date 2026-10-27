# A23 子进程信号恢复与就绪门槛（2026-10-22）

本轮问题是上一阶段SIGINT guard使child继承临时屏蔽。新增独立a23_child_signal_bootstrap.py、a23_child_signal_owner.py、audit_a23_child_signal.py和test_a23_child_signal.py，总计579来源；原575来源逐字节保持，旧取样器、分类器和生产入口保持。

候选在父mask修改前保存目标mask，以固定bootstrap启动child。bootstrap在Python启动后、导入历史取样器前设置SIGINT为default_int_handler、SIGTERM为SIG_DFL，恢复目标thread mask并回读复核。普通目标为空，因此不会持续继承临时SIGINT屏蔽；目标原已屏蔽INT或TERM时照原样保留。原handler并非逐项镜像恢复：TERM继承SIG_IGN时也有意重置为SIG_DFL，原父handler保持。

child通过额外匿名管道报告mask前后、INT/TERM handler前后与恢复前pending INT，绑定本次随机token和完整policy hash。父严格验证固定字段、类型、目标mask、handler、token和digest之后，才发送原取样请求。bootstrap未收到该请求时不能进入目标目录取样；子报告是其自身字节，不是OS认证身份或硬件来源。随机token只用于当前启动绑定，不是正式nonce、权限或序列分配。

就绪正文最多2048字节，读取最多128次、总字节8192；使用独立startup_timeout并受总capture截止时间限制。缺失、部分行、超长、错误token、bool伪装signal数值、mask不一致或TERM仍忽略均拒绝；失败不返回cache/report/classification。单独status FD与标准流在所有最终安排关闭。close抛错时记录不确定，不按同一数字自动重试，以免关闭已复用FD；这不认证任意指令的FD创建至登记原子性。writer关闭再出错也不替换先发生的构造中断。

| 每轮20场景 | 观察与验收 |
| --- | --- |
| normal、原屏蔽INT、原屏蔽INT且child pending | 三例返回相同历史文件字节；原屏蔽和pending保留 |
| 恢复前child INT | 先保持pending，解除后递送，退出130；审计门槛处实际owner wait，未确认就绪 |
| 恢复前child TERM | 默认TERM直接终止，未确认就绪 |
| 恢复后child INT、TERM | 分别退出130、signal TERM，未确认就绪 |
| 就绪后child INT、TERM | 已确认政策仍拒绝已退出child，未发送取样请求，实际owner wait |
| 继承TERM忽略再恢复 | 恢复前TERM被忽略，报告前SIG_IGN/后SIG_DFL；就绪后TERM终止 |
| 就绪后stall，目标TERM未屏蔽 | 总取样期限失败，TERM后wait，无KILL |
| 就绪后stall，目标原屏蔽TERM | TERM不结束child，有限grace后KILL并wait |
| 错token、坏mask、坏handler | 不确认就绪，清理并wait，无取样结果 |
| 部分就绪行、超长就绪行 | 拒绝，不确认就绪，清理并wait |
| 提前退出、注入reset失败 | 无就绪，非零退出；EOF与cleanup可能竞争，原始码分别保存 |
| 恢复前stall | 独立就绪期限到期，TERM并wait，未进入取样 |

最终原位置与搬移回放每轮20实际child，全部由保留Popen对象直接wait，共40child/40wait，没有额外native PID救援。每轮3个允许安排字节匹配；其余17例没有样本产物。所有父mask、TERM handler和pending状态保持；全部policy FD及标准流关闭。SIGINT默认Python处理在指定fixture里捕获并返回130，不能推广到任意Python模块的中断退出码。

审计在before_reset、after_reset及ready_validated检查点只向自己当前保留的child发信号；没有从journal、文件或消息恢复PID。为避免把EOF当作进程已结束，涉及确切INT退出码的场景在审计门槛处调用同一个owner._wait。after-ready wait同样由owner完成。这是指定点的政策验证，不是任意调度/指令覆盖。

新26项和SIGINT guard回归26项、预保留回归26项，共78测试通过。579来源搬移后20场景归一语义一致，历史anchor/文件字节保持，当前Python源码与_posixsubprocess原生镜像一致。各次wire/hash/元数据在各自证据内核验；提前EOF两例跨回放仅归非零，原始码不删除。只读verify在launch/trace/mask/wait阻断时通过；CLI正确/错误/缺失pin返回0/2/2。父审计hook观察原checkout与/Volumes打开0，不继承到child，不能据此认证OS隔离。

开发失败也纳入计数并封存，未追认测试通过：r1执行到第4例，child恢复INT后关闭ready fd，cleanup TERM可能早于退出130，严格130期望失败；前三例有完整观察，第四例直接wait、FD/标准流关闭及父mask断言已通过，但失败前未持久化row，原始退出码未知。随后把审计wait同步到门槛，并改为先归档再验证。r2完成20child/20wait和完整观察，之后只读验证器错误地给已有newline的canonical encode再加一行，导致verify失败；修正纯验证器后建立最终封存。开发共24child，23份完整原始退出码，一份只有失败前断言证据；含最终两轮总64创建者wait，不能声称64份完整raw lifecycle证据。

边界：mask恢复在解释器启动之后，早期加载仍继承临时mask/原忽略handler；不是原子pre-exec政策。当前close_fds=True使此构建走fork_exec；本机构建没有POSIX_SPAWN_CLOSEFROM，不能直接强开Popen的posix_spawn路径而假定FD关闭语义相同。候选没有使用preexec_fn，也未改生产接收器。同步Python异常仍可能打断native返回到PID登记；FD创建至Python列表保存、mask复核自身的任意中断、其他原生线程/信号、创建者或外层监督者整进程死亡、OS身份与来源、全局nonce、断电、原子目录快照和硬实时均未认证。

23保护项、实际49/65账本及失败owner/state保持；旧228actor和14孤儿回收不升级。65已回收/remaining0，81..112未正式保留；USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，生产关闭，首次SDK burst根因未知。

证据：

- review：private/analysis/A23-child-signal-review-20261022-r1
- review SHA256SUMS：7783d784aa4f566184e5b4fe7ffbb9c9c9af3bc70b6a81fca76bbfc469a3f273
- validation：private/analysis/A23-child-signal-validation-20261022-r1，含两份开发失败封存、日志、development-accounting及搬移回放
- closeout：private/analysis/A23-child-signal-closeout-20261022

只读重验：

```sh
/opt/homebrew/bin/python3.13 -B research/usb-ds-iso/tools/audit_a23_child_signal.py --check research/usb-ds-iso/private/analysis/A23-child-signal-review-20261022-r1 --expected-sha256 7783d784aa4f566184e5b4fe7ffbb9c9c9af3bc70b6a81fca76bbfc469a3f273
```

下一步离线核对当前macOS原生spawn的setsigmask能否在解释器执行前设置政策，同时保留close_fds、错误通道和直接owner约束；停在有源码/运行时绑定的能力表与明确缺口，不能因API名字推定原子性。此前同步构造异常和创建者死亡缺口保持，不接生产或硬件。

前序：[原生PID窗口与SIGINT暂缓对照](A23_SIGINT_GUARD.md)。

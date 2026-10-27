# A23 取样独立期限与子进程直接wait（2026-10-22）

后续：[调用者中断与运行时句柄交接](A23_TERMINAL_OWNER.md)完成565来源、两轮74安排和82测试。新增显式owner候选，原deadline监督器与固定worker保持。以下保留原阶段。

已补齐上一步同步取样缺少独立IO期限的离线候选。新增5来源共562，原557来源逐字节保持：监督器、固定worker、故障fixture、审计、测试。源码分别为 tools/a23_terminal_deadline.py、tools/a23_terminal_deadline_worker.py、tests/a23_terminal_deadline_fixture.py、tools/audit_a23_terminal_deadline.py、tests/test_a23_terminal_deadline.py。原取样器和纯分类器、生产入口、硬件票据均未改。

监督器先复核anchor/pin、规范/private/tmp子目录与有限正数时间预算，再以Popen直接创建并持有固定worker。worker复用原NOFOLLOW/18文件白名单/两轮观察取样器，目标读取规则保持。请求≤16384字节、anchor≤8192字节，响应≤262144字节。stdin/stdout为非阻塞管道，selector与直接wait共用从启动前计算的绝对monotonic截止时间；持续输出也逐次检查时间与响应上限。stderr为DEVNULL，错误只作拒绝，不将诊断文本当作成功。

完整响应和EOF只是材料就绪，仍须在期限内直接wait得到exit0。父进程检查规范JSON/base64、白名单、原8192单文件/131072总量限制、报告字段/元数据形状及禁止历史推断的标志，然后用旧纯分类器重新计算结果。取样通过仍可以得到冲突分类，任务与物理权限始终false。缓存/元数据不认证来源或历史进程身份。

期限到期、传输错误或超限后，只通过本次保留的Popen对象请求TERM并有限wait；必要时KILL并再次有限wait。观察分别记录deadline_expired、terminate/kill_attempted、调用是否返回、direct_wait_verified和returncode。发信号返回不证明终止或wait。两次wait都不能认证时，结果保留pending_process实际句柄并设置pending_handle_retained；不声称已回收，不返回缓存。这个无法wait路径用mock覆盖；真实67个子进程/轮均直接wait，没有遗留该类子进程。

| 每轮安排 | 实际观察 |
| --- | --- |
| 58历史快照 | 返回原字节，6关联完整、52不完整；exit0且创建者直接wait |
| 实际阻塞读取 | 取样after_open处持有pipe写端而阻塞read；父亲收到blocked-read检查点，期限后TERM/direct wait |
| 忽略TERM后阻塞 | 先观察TERM后的wait超时，再KILL/direct wait，实际returncode=-9 |
| child不读stdin | 请求发送/响应等待仍有同一独立截止时间，失败并直接wait；小请求未证明实际写端背压 |
| 半响应后阻塞 | 期限失败，无缓存 |
| 完整响应并关闭stdout后阻塞 | EOF不替代wait；期限失败，完整缓存被丢弃 |
| 持续超限输出 | 第262145字节拒绝，清理并直接wait |
| 坏JSON、完整响应后exit7、伪造历史标志 | 各自拒绝，未返回缓存 |

单次故障预算1.5秒、每次清理wait预算0.2秒，历史快照预算4秒。这些是离线工程值，不是生产政策。两次独立位置回放共134个新Python取样子进程、134次创建者直接wait、10次期限失败和2次KILL升级。它们只读取本轮临时目录复制的历史材料，没有新actor/requester/guardian执行或现场job。历史UUID/nonce/anchor和文件字节保持；新取样进程的wait不能追认旧228 actor或14孤儿已回收，全局orphan_reaping_verified保持false。

26项新测试与30项原取样、26项纯恢复回归，共82项无跳过通过。单元mock覆盖发信号错误后仍wait、发信号成功却wait失败、两次wait超时持有句柄、spawn/transport/close失败，以及BOOL/NaN/无效预算、坏pin和外部路径在启动前拒绝。父协议坏件包括路径名/base64/报告BOOL/计数/形状/伪造历史。实际故障fixture仅在临时材料上执行，不启动后代、不写目标文件；_command是受信任审计替换点，不是认证后的执行能力。

562来源搬移回放得到相同67安排归一语义，inode/时间和实际耗时仅作各自观察。成功响应摘要独立绑定归档cache/report；只读verify在Popen与capture均被阻断时通过；CLI正确/错误/缺pin返回0/2/2。父Python审计hook观察到原checkout及/Volumes打开为0，该hook不继承到子进程，不扩写为OS隔离或子进程来源认证。

这不是整个函数的硬实时返回承诺。Popen创建本身不能被此同线程截止时间打断，OS调度、close/信号/wait系统调用也不构成硬实时保证；父进程解析是限长计算并在完成后复核截止时间，没有独立可抢占的解析期限。清理有额外预算。调用者中断、父进程崩溃、任意后代及不可回收的真实OS状态尚未验证，wait失败只做mock，不能把模型结果说成真实不可中断IO的回收证明。

来源、原子exec输入、OS能力隔离、全局nonce、断电、目录原子快照、历史sync/wait、真实SDK、时钟映射、quiet drain与生产permit仍未认证。旧证据封存不变；23保护文件、实际49/65账本和失败owner/state保持。65已回收/remaining0，81..112未正式保留；USB/SD/真实SDK/原生编译/部署/正式记录/保留/消费/claim全0，生产采集关闭。首次SDK burst超时根因仍未知。

证据：

- review：private/analysis/A23-terminal-deadline-review-20261022-r1
- review SHA256SUMS：d94144f0cb66106efaf77ccd3e2b4adc94a9e207c36d83b59a44b6d1498e3696
- validation：private/analysis/A23-terminal-deadline-validation-20261022-r1
- closeout：private/analysis/A23-terminal-deadline-closeout-20261022

只读重验（Python 3.10+，本轮使用/opt/homebrew/bin/python3.13）：

```sh
/opt/homebrew/bin/python3.13 -B research/usb-ds-iso/tools/audit_a23_terminal_deadline.py --check research/usb-ds-iso/private/analysis/A23-terminal-deadline-review-20261022-r1 --expected-sha256 d94144f0cb66106efaf77ccd3e2b4adc94a9e207c36d83b59a44b6d1498e3696
```

下一步离线覆盖调用者中断，以及清理失败时仍持有实际子进程句柄的交接。不能用journal PID重建清理权限，不能自动重启，不接硬件卷或生产入口。

前序：[临时目录只读取样入口](A23_TERMINAL_INTAKE.md)。

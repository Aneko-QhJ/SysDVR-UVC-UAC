# A23 调用者中断与运行时句柄交接（2026-10-22）

后续：[Popen保存窗口与外层直接归属对照](A23_SPAWN_BOUNDARY.md)发现保存前句柄缺失和保存后管道未登记两个负对照。原owner保持；新隔离子类仅修正已保留child的管道发现。以下保留原阶段的指定检查点边界。

已补上一阶段“调用者中断后如何继续持有未清理句柄”的独立离线候选。新增 tools/a23_terminal_owner.py、tools/audit_a23_terminal_owner.py、tests/test_a23_terminal_owner.py 共3来源，总计565，原562来源逐字节保持。原deadline监督器、固定worker、取样器/分类器、旧故障fixture和生产入口均保持。

旧capture虽然会在finally尝试清理，但KeyboardInterrupt穿过清理流程时不返回Observation；若清理也被中断，调用者不一定能取得pending_process。这是本轮代码路径发现，不是实机超时根因。

新接口先构造SamplerOwner，再调用owner.capture。实际Popen、已wait标志和管道保存在共享运行时slot中。主流程捕获BaseException以记录失败并清理；KeyboardInterrupt、SystemExit和其他非预期异常在清理后传播原对象。TERM、wait、KILL和每个close分别包裹，第二次异常另记，不替换第一个主异常。尚未完成的资源仍可从调用者原先持有的owner继续finish；finish只有清理，不启动新采集、不重新接受旧缓存。完整cache/report/classification只在成功wait、管道关闭且无失败后返回，中断安排不输出这些文件。

超时/管道上限仍复用上一阶段规则：规范/private/tmp输入，18文件白名单，单文件8192/合计131072字节，响应262144字节，共用monotonic期限。它仍不是整个函数的硬实时返回保证。

运行时交接只在同一进程、单一调用者中进行。源owner先保留successor引用，然后以slot.holder=successor这一个赋值提交权限；实际Popen从未移出共享slot。准备点中断时源owner仍有效，未提交的successor无权操作；提交点后中断时源owner.successor仍能找到有效后继。提交后源owner的capture/finish/handoff被拒绝。清理操作期间重入也被拒绝。这里的Python对象协议不是OS强制能力隔离，也没有认证恶意代码或多线程竞争。

```python
owner = SamplerOwner()                 # 必须在capture前保留
try:
    result = owner.capture(directory, anchor_bytes, anchor_pin)
except (KeyboardInterrupt, SystemExit):
    observation = owner.observation() # 仍可观察并继续清理
    raise
# 若仍有资源待清理，可显式调用owner.finish()。
# 若handoff()已提交但抛出中断，从owner.successor继续，旧owner已被撤销。
```

只有实际runtime slot的持有者能调用清理；没有从PID、JSON或journal恢复对象的API。handoff不是磁盘恢复、跨进程传递或采集重试。快照是deepcopy，改写观察快照不会改变live slot。观察中所有生产/物理权限仍false；本轮仅清理由调用者直接创建的离线Python子进程。

| 每轮安排 | 已观察范围 |
| --- | --- |
| 58历史快照 | 原字节保持，6关联完整/52不完整；正常采样exit0并直接wait |
| 七个capture中断点 | before_spawn、after_spawn、exchange、after_exchange、wait、after_wait、after_decode；原异常对象保持 |
| 三个清理中断点 | TERM前、TERM后wait前、stdout close前；失败分别记账，仍可显式finish |
| 双中断与SystemExit | 原异常未被清理中的第二次KeyboardInterrupt替换；SystemExit对象与code保持 |
| 真实timer | SIGALRM/default_int_handler在exchange期间实际抛KeyboardInterrupt，恢复原handler并关闭timer |
| 三个句柄交接 | 正常交接、准备点中断、提交点中断；同一Popen身份，源owner撤销，后继清理并直接wait |

每轮74安排，before_spawn没有创建子进程，其余73个新取样子进程均实际wait。两轮共146个子进程、146次创建者直接wait、两次真实timer中断、六次句柄交接。58个历史UUID/nonce/anchor及文件字节复用，没有新现场job或actor/requester/guardian执行。所有中断/交接安排都保持失败，无cache/report/classification。

交接场景使用真实子进程，但故障是受信任仪器：暂时跳过该对象的TERM/KILL实际调用，并让wait抛EIO，确保返回时句柄仍待处理；随后恢复原方法，将同一个对象交给后继owner并真实wait。因此验证了故障后的对象保留和交接，不证明OS曾拒绝wait或存在不可中断IO。单元Mock另外覆盖两次wait超时、wait已成功但之后中断、仅管道待关闭的交接、重入拒绝、无PID/JSON恢复、快照改写以及意外异常身份保持。

新26项、原deadline26项、原intake30项，共82测试无跳过通过。565来源搬移使用同样58历史材料，两轮74安排的归一语义一致；元数据/耗时/响应摘要按各自观察保存，原始负returncode保留在报告，跨回放仅归为“被信号终止”，不要求TERM/KILL竞争结果相同。只读verify阻断Popen与capture仍通过；正确/错误/缺pin的CLI返回0/2/2。父Python审计hook观察到原checkout与/Volumes打开为0，但不继承到子进程，不能据此认证OS隔离或子进程来源。

边界：句柄保护从slot.child成功保存后开始。本轮没有证明Popen创建中、返回后至slot赋值之间或任意Python指令的中断安全；有界清理步骤之间也未穷尽所有异步时刻。owner进程SIGKILL/崩溃、跨进程/多线程交接、任意后代回收、真实不可wait的OS状态、断电恢复和硬实时未验证。单holder赋值只定义本Python协议中的提交点，不是spawn或exec原子性证明。后继对象仍依赖这个进程存活，磁盘记录不能重建其权限。

原228 actor和14孤儿回收未认证结论保持；新子进程wait不追认历史wait，orphan_reaping_verified始终false。来源、OS能力隔离、全局nonce、原子exec、目录原子快照、真实SDK、时钟映射、quiet drain和生产permit仍未认证。23保护文件、实际49/65账本、失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，生产采集关闭，首次SDK burst超时根因未知。

证据：

- review：private/analysis/A23-terminal-owner-review-20261022-r1
- review SHA256SUMS：76fbed18699e1bae5f8055db82e0f838acd785bf46356dc4dac9532f998d409f
- validation：private/analysis/A23-terminal-owner-validation-20261022-r1
- closeout：private/analysis/A23-terminal-owner-closeout-20261022

只读重验（本轮Python 3.13）：

```sh
/opt/homebrew/bin/python3.13 -B research/usb-ds-iso/tools/audit_a23_terminal_owner.py --check research/usb-ds-iso/private/analysis/A23-terminal-owner-review-20261022-r1 --expected-sha256 76fbed18699e1bae5f8055db82e0f838acd785bf46356dc4dac9532f998d409f
```

下一步离线核对Popen创建至句柄保存的窗口，以及owner整个进程退出时的外层归属。不能把当前指定点结论外推到任意指令、崩溃恢复或journal PID清理；不接硬件卷或生产入口。

前序：[取样独立期限与子进程直接wait](A23_TERMINAL_DEADLINE.md)。

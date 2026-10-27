# 两次轮间后台校验的最小接线（2026-10-25）

[队列设计](A23_GUARD_QUEUE_DESIGN.md)已实现为隔离控制器，并接到冻结三轮entry/driver的临时原生fixture。正常路径两次worker返回、两次job/permit复核、两次恢复poll，三轮9216正确字节通过旧模型独立消费者验收。第三轮前改来源或出现interest时，均只提交两轮、整体失败，未补第三轮。

当前是离线接线验证，尚无当前126件基线的正式构建、接收入口或硬件许可。旧644来源不变，新增3件形成647件研究来源束；冻结build内的完整校验仍针对原644来源和120件基线，不假装已经把新增代码、126件基线和完整49..416历史绑定进一个可实测scope。

## 代码与独占权交接

新增host/a23_interepoch_guard.h、host/a23_interepoch_guard.m和tests/a23_interepoch_guard_fixture.m。控制器固定只接受epoch1/2，按顺序各检查一次。busy期间、旧epoch、第3边界和poll内的重入请求均不启动worker。

每次请求绑定job、scope摘要、epoch、generation和递增request ID；worker只执行fullCheck，生成不可变结果。dispatch_group_async块及其autoreleasepool返回后，dispatch_group_notify才在串行队列标记verifier已交回，接着复核回执身份/phase、边界、期限、原job/permit，再次核对边界和停止状态，最多恢复一次poll。result只返回控制器自身字段，不在busy期间访问verifier。

stop只锁存并递增generation，不取消或提前释放worker。observeDeadline到期后禁后续poll，仍保持busy和worker持有状态，直到完成通知实际交回。期限不是阻塞文件调用的硬取消；成功回执也不能清除已经锁存的停止。fullCheck的Objective-C异常转为检查失败；这不处理进程崩溃、任意线程异常或OS无法调度。

## 12个真实文件guard与原生模型permit场景

使用冻结120件build的完整guard核心、原A23SharedSequenceModelPermit和临时simulation namespace。每个进程先同步做一次完整检查并初始化模型许可，再让控制器执行轮间检查。第1024次readFile的固定hook让指定本地交错发生；不作性能比较。

| 场景 | 结果 |
| --- | --- |
| normal-two | 两次完整检查、两次返回/复核/poll；旧epoch与第三边界拒绝 |
| early-receipt | worker仍持有verifier时收到的提前回执丢弃，两次正常返回各恢复一次 |
| duplicate-receipt | 两次交接各丢弃一份重复回执，无额外poll |
| wrong-phase / wrong-request | group返回后身份错误，停止，poll0 |
| exit-in-check | 检查中退出；等worker返回，poll0 |
| boundary-change | 检查中epoch变化；旧结果拒绝，poll0 |
| permit-change | 检查中改临时consumed文件，原job/permit复核拒绝，poll0 |
| source-change | 检查中改临时644来源，完整检查失败，poll0 |
| deadline | 指定安排中到期时仍由worker持有；返回后不poll |
| fault-in-recheck | job复核回调中锁存故障，复核成功值也不能恢复poll |
| boundary-in-recheck | 复核期间边界变为停止，最后边界门拒绝 |

1次ASan/UBSan编译、12个原生进程通过。共有12次启动完整检查、15次worker完整检查、6次本地poll；这些poll不是SDK提交。9个失败安排没有运行后续epoch，错phase/request不进入job复核。检查期间本地通知处理会尝试重复request，确认不会多发worker。最后交回后的job检查使用同一个真实verifier；没有像上次探针那样只返回一个无人继续访问的临时verifier。

## 原entry/driver三轮集成

仅在临时副本生成coordinator接线，原build/接收器不变。首次启动、WAITING、末轮观察和最终导出沿用原路径；只在已保存1/2轮、iso_attempts等于saved_epochs且未停止时交给控制器。busy时跳过会自动arm的entry tick。worker返回后的recheck使用原verifyLiveJob和permit.result，随后直接恢复一次原entry tick，STATUS/frame/ISO/BURST健康检查继续执行。

fixture在外层通过完成通知等待本次worker，串行队列本身不等待worker；临时10秒guard期限是模型安排，不是新实机期限。新接线和生成fixture保存在封存包内，不覆盖旧生成源码。

| 场景 | worker检查/返回 | job复核/恢复poll | ISO/BURST | 最终结果 |
| --- | --- | --- | --- | --- |
| normal | 2/2 | 2/2 | 3/3 | 保存9216正确字节，独立消费者接受 |
| between-third-source | 2/2 | 1/1 | 2/2 | 第二次worker查来源失败，第三轮未提交 |
| interest-close | 1/1 | 1/1 | 2/2 | 原adapter/entry捕获interest，第二次worker未启动，第三轮未提交 |

第二项失败由控制器锁存；interest项由原adapter/entry停止，控制器自身stop字段仍为false，不能将两者说成同一条停止路径。三项sdk_destroys均0，abort均0；失败保留前两轮材料，没有复用存储或主动销毁已触碰lease。原fixture的模型关机补充与进程退出不是本次真实设备关机或资源排空证据。

这部分另1次ASan/UBSan编译、3个原生进程通过。正常独立消费者以simulation=true接受旧冻结模型的传输/回执，不认证新647来源的正式build绑定。完整fixture共24次native完整检查，其中5次是worker；加组件27次，本轮共51次native完整检查。Python侧封存/来源哈希不计入此数。

两组共2编译、15原生场景，创建者均直接wait；组件链接检查确认无IOKit/IOUSBHost。集成fixture沿用原链接库，但provider完全注入、真实SDK对象及USB请求均0，未调用正式采集CLI。共15个临时模型namespace/授权，正式namespace、授权、范围新增均0。未运行ThreadSanitizer，不声称覆盖所有并发交错。

## 尚未覆盖的边界与下一项

后台检查从saved后才开始，没有与上一轮ISO重叠，校验仍位于下一轮提交的关键路径。同步STATUS、日志和保存仍可能阻塞串行队列，末轮250ms观察维持原含义；本轮不证明性能提速、持续流、SDK回调排空、存储复用，亦未闭合最后原子读取至实际SDK调用之间的窗口。

本轮指定交错支持继续准备独立软件候选。下一项只把临时coordinator接线固化成独立生成器，绑定当前126件回收快照、完整49..416消费历史和spent369，保留旧647来源及旧封存，核对必要的来源/基线/scope拒绝。新生成器若增加来源，须纳入新来源束，不能沿用旧647摘要。无需再重复相同三轮模型或扩展通用进程框架；正式硬件仍另需新范围、新授权和当前就绪确认。

## 封存

| 目录（相对private/analysis） | SHA256SUMS摘要 |
| --- | --- |
| A23-interepoch-guard-wiring-20261025-r1 | 首版在来源集合合并时Python优先级错误，编译前退出，原样封存 |
| A23-interepoch-guard-wiring-20261025-r2 | cd09fc823f736c1b1d647ccc57a2b7c125f762d4cac16b4f17d348fd9f994837 |
| A23-interepoch-entry-integration-20261025-r1 | 58de451dea0bbc6bc875f415c9c27687fe434926d7da3cc2d2b754570b965dae |

新增3来源副本、原始命令/输出、模型namespace与三轮host材料均在上述包；旧actual369/321/273、八个正式namespace、全部旧来源保持。126件日志已回收，SD最后记录已弹出、remaining0；当前现场状态未刷新。最终票据和文档交接见private/analysis/A23-interepoch-guard-wiring-closeout-20261025。

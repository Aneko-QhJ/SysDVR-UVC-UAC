# A23 状态管道显式失败候选（2026-10-21）

后续：[局部终态发布中断对照](A23_TERMINAL_PUBLICATION.md)完成546来源、50安排和74测试。两次完整回放48个发布中断，4次在完整exit文件fsync后仍中断；局部退出码声明不等于实际wait状态。原候选保持。以下保留原阶段。

本阶段处理上一轮guardian死亡后状态回报触发BrokenPipeError的路径。新增4个来源：候选actor包装、纯消费者、审计与测试，共541，原537来源保持。冻结requester、worker包装、内部fixture、guardian audit与仪器、原观察包装均未改；历史SDK材料仍是缓存。

候选在actor原进程执行冻结脚本，只拦截传入的status FD，其他FD的os.write直接交还原函数。冻结guardian仍调用原actor文件名，因此临时stage将候选复制到a23_guardian_failure_actor.py这个明确槽位；failure-plan的instrumentation摘要指向候选字节，transport-plan另记候选、原观察包装、嵌套failure-plan及来源review摘要。冻结source目录保留两个不同源码，不覆盖旧证据。

write_status接收非空、最多8192字节的frame，补齐短写，EINTR继续；总系统调用最多16次。零、BOOL、负数或越界进展明确失败；EPIPE立即抛出独立于原actor异常处理的StatusTransportFailure，不再发送第二条失败回报。其他IO错误和预算耗尽也保留错误分类。本轮真实管道仅覆盖EPIPE；短写/EINTR/其他错误/进展异常/预算是mock测试，不能声称这些均已做真实故障注入。

候选恢复原os.write后，以独占文件保存失败原始frame、transport记录和局部exit记录。transport绑定job/nonce/failure-plan、actor PID、frame摘要/长度/消息kind、errno、提交字节与写入次数；delivery_confirmed和creator_wait_observed固定false。退出码91及StatusTransportFailure表示本地观察到状态传输失败；不是guardian收到的回报，也不是实际wait状态。成功actor保持0且不带transport/frame文件。

53种安排为13个真实进程场景和40种缓存坏件。复用冻结guardian故障检查点：normal、requester创建前后、worker已创建未记owner、owner半写/已同步、放行前、4个child发布检查点、worker已wait及双方已wait。仅normal允许模型完成；完整receipt、成功actor状态和已完成的wait都不能覆盖guardian死亡。

| 两次回放观察 | 数量及含义 |
| --- | --- |
| 实际Python进程 | 26 guardian、24 requester、22 worker，共72 |
| witness直接wait guardian | 26；24次SIGKILL、2次0 |
| actor预注册NOTE_EXIT / witness waitpid ECHILD | 46；不属于witness的直接子进程 |
| 原guardian已wait actor | 10：requester4、worker6 |
| actor只确认终止，回收未认证 | 36；与旧基线的wait边界一致 |
| actor局部终态 | 36次91/StatusTransportFailure、10次0；36次EPIPE均提交0、仅写1次 |
| 原始失败frame | 36份，kind属于request/rejected/ready/end |

本次实际原始消息分布为requester request2、rejected18，worker ready2、end14。最早Popen窗口存在调度差异，request或ready也可能在guardian死亡后才首次发送，因此消费者按场景约束允许的kind集合，不把该调度字段纳入跨回放语义相等。worker end失败frame保存guardian_closed/87；这只是未送达消息的内容，没有把87冒认为实际进程wait码。后续阶段不得把局部91冒认为已认证的OS退出状态。

纯消费者先严格验证候选局部终态、原始frame及transport记录，再在内存副本中仅将91/StatusTransportFailure映射为旧消费者要求的1/BrokenPipeError，复用旧guardian/NOTE_EXIT/wait边界检查。实际文件、失败frame、plan pin不被修改。这个兼容投影用于检查相同故障资格，不声称候选仍抛出原BrokenPipeError；正常路径继续使用原内层报告和发布协议验证。

40种坏件包含继承的20种guardian/checkpoint/actor终态观察坏件，另20种针对新失败码/异常、缺transport或frame、errno/原因、BOOL或正提交量、重复尝试、冒认送达/本地wait、frame摘要/BOOL长度/kind/nonce/pin，以及修改frame的job/PID/kind/end码后重算摘要。保持外部plan pin时全部拒绝。

新26项、guardian-failure回归22项和guardian-owned回归22项，共70测试无跳过通过。纯消费者在open/io.open/waitpid阻断下完成缓存分析；只读verify在Popen阻断下完成。541来源搬移使用独立UUID/nonce/PID，53安排确定性语义一致，正确/错误/缺pin的只读CLI返回0/2/2。

26份guardian-use、22份attempt保持；重试/恢复各拒绝26次，证据字节不变，16份accept各一次。10对实际receipt/part核对同inode、nlink=2与字节相同，封存副本为独立普通文件。actor/journal PID信号0；没有额外单元进程。

仍然没有解决的边界：

- guardian死亡后36个actor的wait回收仍未认证，旧14个孤儿也未追认。局部失败文件、NOTE_EXIT和ECHILD不证明系统回收，orphan_reaping_verified始终false。
- 局部三个文件逐个独占写/fsync，没有目录同步，没有本地终态发布中断、缺失/半写或断电恢复验证。候选改善本轮可见记录，不保证记录永远存在或持久。
- witness存活、固定检查点与小报告是离线仪器前提；未认证任意指令崩溃、witness故障、所有后代清理或通用OS supervisor。同步文件IO仍无独立中断期限。
- 外部review/plan pin是调用方信任输入，不是签名。协调修改outer与checkpoint的guardian PID声明仍可模型完成，未认证它与内层实际来源相符；物理、来源与生产授权全部false。
- 搬移审计hook仅覆盖Python父回放，不继承到guardian/actor/CLI，不证明OS隔离或校验到exec输入的原子绑定。单目录独占不证明全局nonce防重放或断电持久性。
- 未执行真实SDK、driver clock/timebase、callback quiet drain或生产permit；生产receiver/collector/broker/permit及原launcher未接入。

证据：

- review：`private/analysis/A23-status-transport-review-20261021-r1`
- review SHA256SUMS：`1308df18cd399f558c37b2305e10803c4b90dab8c8278d5978d71bfb570dfcfe`
- validation：`private/analysis/A23-status-transport-validation-20261021-r1`
- closeout：`private/analysis/A23-status-transport-closeout-20261021`

只读入口：`tools/audit_a23_status_transport.py --check <review> --expected-sha256 <review_pin>`。纯入口：`assess(transport_plan_bytes, plan_pin, job_byte_cache, witness_observation, guardian_checkpoints, actor_exit_notes)`。transport-plan、failure-plan、owned-plan、integrated-plan及launch摘要层级不同；owned-plan/crash-plan兼容别名仍同字节，沿用既有路径、普通文件、节点和字节限制。

23项保护文件、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。

下一步离线覆盖局部终态文件缺失、半写及发布时actor中断，明确保留失败证据与恢复拒绝；不把本地报告/NOTE_EXIT视为wait，不按journal PID清理，不自动重启，不接生产或硬件。

前序：[guardian自身中断与管道失效](A23_GUARDIAN_FAILURE.md)。

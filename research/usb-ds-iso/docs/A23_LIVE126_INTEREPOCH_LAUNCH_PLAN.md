# 126件候选的一次性启动计划审查（2026-10-25）

[651来源/126件候选](A23_LIVE126_INTEREPOCH_READY.md)的一次性启动计划已准备并审查。launcher、专用workflow、生成workflow和原生scope一致；沙箱外仅查询自身进程的上下文通过策略。417..464仍未保留/授权，没有新actual记录、模型namespace、接收器采集、USB/SD访问或部署修改。

候选不重新编译、不改651来源、不重复三轮模型。下一步实际采集需要人类新的单次最多三轮授权，以及当前完全关机/装卡/USB连接确认；本轮“继续”只用于完成离线准备，没有据此制作人工授权回执。

## 计划绑定与执行顺序

计划目录private/analysis/A23-live126-interepoch-launch-plan-20261025-r2，含plan.json与launch-once.py。默认运行仅review；--execute必须读取新的精确人工回执，缺失或不匹配即拒绝。

| 项目 | 计划值 |
| --- | --- |
| build | private/analysis/A23-live126-interepoch-review-20261025-r1/build |
| build SHA256SUMS | abd21e277165bac7aca7145a968459ef004803de234488f63428188404338324 |
| receiver SHA256 | 153f00561d4b5e9adf2b709fd894be319aa409f60a7177aaa37b84a236b6b320 |
| 版本 | 651来源、126件快照、完整49..416消费历史及spent369 |
| scope | A23-live126-interepoch-shared48-scope-1；417..464 |
| 上限 | 一次调用、最多三轮、每轮128项/16包；整个48序号一次消费 |
| 新人工回执槽 | private/analysis/A23-live126-interepoch-human-authorization-20261025-r2.json，当前不存在 |
| 新actual记录槽 | private/analysis/A23-live126-interepoch-once-20261025-r2.json，当前不存在 |
| 新正式namespace | private/sequence-reservations48-417，当前不存在 |

人工回执必须绑定该build/receiver、范围和上限，并明确failure_policy=stop_no_retry及当前完全关机、SD在设备、USB已连接。plan.json中的expected_human_authorization只是待匹配的格式模板；它不等于人工授权文件或已收到的授权。

未来执行顺序为：新授权与当前就绪成立→文件/build/工作流/scope核对→独占写入一次actual外层claim→发行一段范围→capture再次核对真实执行上下文和fresh scope→消费整段→唯一接收器→实际WAITING后才提示CFW开机。创建者持有前台子进程并直接wait；失败不补轮或自动重试。若claim后、采集前失败，也保留该实际记录，不自动重开同一槽。结束后另行只读回收设备日志，不追加USB诊断。

本候选的两次worker校验、10秒软guard期限、退出前等待worker返回、原传输/interest门与失败资源保留保持。一次无故障三轮只能检验严格载荷/状态链及该运行的worker路径；不能认证所有故障交错、持续流、SDK排空、缓冲区复用或最后原子检查到SDK调用窗口。

## 只读执行上下文

先在workspace沙箱查询封存接收器的--inspect-context：系统build26A434、框架UUID B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B及receiver摘要匹配，但sandbox_query_result=1，因此policy_pass=false。它是当前进程环境观察，不是硬件失败。

随后经工具自动审批，在沙箱外只执行同一只读上下文脚本。native子进程的sandbox_query_result=0、errno0，同一系统/框架/receiver，policy_pass=true。脚本核对源束和封存输入后运行inspect分支，读取自身PID/身份/时钟、系统版本、已载入框架UUID和二进制摘要；不匹配IOKit设备、不打开interface/pipe、不访问SD。两个native子进程均由脚本直接wait。

usb_open_permission_proven始终false。该上下文观察既不证明设备可打开，也不能作为未来capture的上下文凭据：真正capture仍会在自己的环境重新调用context_preflight，策略不符则停止。当前设备现场状态没有刷新。

首次脚本名inspect.py遮蔽标准库inspect，import时即失败、native0；改名observe_context.py后完成沙箱内观察，失败说明和缓存保留。沙箱外为另一个独立r2包，不修改r1。

## 审查与反例

最终r2计划review退出0、缺新授权的--execute退出2，明确报new human authorization receipt missing。4个反例均在外层claim前拒绝：

| 反例 | 拒绝位置 |
| --- | --- |
| 旧120外层workflow | launcher/workflow builder mismatch，尚未preview或claim |
| 注入旧generated builder | generated workflow builder mismatch，尚未preview或claim |
| 旧369..416 scope | 原生fresh scope为417..464，与旧计划scope不一致 |
| 临时错误回执 | 临时目录的故意错误首序号回执与精确模板不匹配；同时阻断live写入/issue/capture，未创建真实人工回执 |

r2两个Python CLI进程、4个实际native fresh-scope检查（review、缺授权、旧scope、错误回执）均直接wait。反例中的旧generated builder为明确注入对象；没有把不兼容旧模块真的当作新工作流执行。临时错误回执随后由临时目录上下文清理，正式槽保持不存在。

首版r1计划的review已退出0、缺授权已退出2，错误为基础reader的invalid file path；准备脚本误要求该错误包含授权文件名，导致拒绝后的文案断言失败。无claim/发行/采集。r1原样封存，r2增加明确的缺回执检查并改用新r2人工/actual槽。含r1共4个CLI子进程、6个native freshness进程；加两个context native进程，本轮native只读进程共8，均已wait。没有编译、模型采集或正式授权。

## 当前结论与下一步

离线计划和自进程上下文核对已闭合。651来源、候选build、旧actual369/321/273与八个正式namespace均保持；日志pending=false、SD最后已安全弹出，当前remaining0、采集关闭。两个计划版本对应的人工/actual槽以及正式417 namespace全部不存在；不使用r1计划，不回退旧369..416入口。

下一步可交人类审查的新实测范围是417..464一次、最多三轮，失败即停、不重试。必须另行收到新授权并确认当前Switch完全关机、SD装回、USB连接；再执行r2计划并等待唯一接收器真实WAITING后提示开机。没有这些新输入，不启动接收器或发行范围。

## 封存

| 目录（相对private/analysis） | SHA256SUMS摘要 |
| --- | --- |
| A23-live126-interepoch-context-20261025-r1 | 55c4b1c28f449e6f25284a99c00d15e594b7541b1e27ae2bfae5a2f1e61e3278 |
| A23-live126-interepoch-context-20261025-r2 | 96bc2ea7a5cd5059ef27b4826d275869199a534f8ed864b70885343bc5bca05e |
| A23-live126-interepoch-launch-plan-20261025-r1 | 首版拒绝后文案断言失败，原样封存 |
| A23-live126-interepoch-launch-plan-20261025-r2 | b2185307affcbb18b9198e901649668b60d509a5717d2188c0464f103e9836d0 |

最终票据、八namespace/actual摘要、计划/上下文引用和文档交接见private/analysis/A23-live126-interepoch-plan-closeout-20261025。旧“尚未检查沙箱外上下文”的描述保留为准备阶段历史；当前只确认上述本次自进程观察。

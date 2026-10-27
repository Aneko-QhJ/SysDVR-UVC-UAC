# A23诊断窗口、主机等待与V2材料关联（2026-10-15）

本轮把[独立V2容量候选](A23_CAPACITY_V2_CANDIDATE.md)继续推进到执行条件审查，发现三个
需要先处理的缺口：**主机入口不等待设备出现；窗口跨期后仍可能开始一次请求处理；正常
导出及诊断保存失败时没有REL2落盘路径。** 这些是候选执行与取证限制，不是原SDK超时根因。

新增[审查工具](../tools/audit_a23_execution_readiness.py)、
[材料比较器](../tools/analyze_a23_v2_association.py)及16项检查。生产、主机接收入口、
设备候选和V1/V2格式均未修改；本轮没有新ARM构建、设备部署、USB或SD操作。

## 30秒窗口的实际控制流

从已封存V2的window-30s完整源码逐字提取VideoStreamThread函数体，编译进电脑fixture；
同时使用该候选原始ep0_candidate_window.h。身份、时钟、USB、日志、采集均为注入服务，
不执行Switch线程或ARM。九组native执行通过ASan/UBSan。

窗口在USB ready之前启动，只有WaitReady和ProcessRequests返回之后检查；窗口不是
请求处理的取消器，也不保证URB已经终结。以下时间均为注入的设备本地时钟，零点为窗口
初始化，不是实机延迟测量，也不证明SDK真实调用会持续对应时长。

| 注入场景 | 实际函数体的观察 |
| --- | --- |
| ready恰好在30000ms返回 | 停止，没有ProcessRequests调用 |
| ready到45000ms才返回 | 到45000ms才检查并停止，没有处理请求 |
| 1000ms ready，Process用45000ms | 到46000ms才检查停止 |
| 29999ms ready，Process用5ms | 在30004ms检查停止 |
| 29990ms ready，Process用1ms，再休眠50ms | 第二次Process在30041ms开始，30042ms才停止 |
| 1000ms ready，采集读取用45000ms后失败 | 休眠16ms后又先执行Process，46018ms才停止 |
| Bind耗时321ms | trace_start和window_start相差321tick，不能视为同一时刻 |

另有普通空闲循环和极晚Process返回对照。极晚返回只演示控制流依赖返回，不能推算设备
实际最坏执行时间。未返回的同步调用本来就无法靠此轮后置检查终止。

因此，下个隔离候选应增加**每次Process之前的停止/过期检查**，保留调用返回后的检查；
采集失败休眠等路径回到循环时也必须先检查。这样能避免已过期后新开一次Process，仍不
打断正在执行的同步服务。无需为了本轮诊断改变主机16ms期限、EP0等待期限或HOS补丁。

当前格式没有单独持久化window_start；TRC2的start_tick属于CandidateStart，二者之间
还有SessionBind。不能用freeze_tick-start_tick精确恢复窗口超期量，更不能把Mac与Switch
原始tick相减。窗口预算、实际ready时刻及停止原因的持久化需要独立格式设计。

## 主机提前等待的可执行设计边界

现有io_usb_host_burst_main只调用一次IOServiceGetMatchingServices，然后立即选择；没有
匹配通知订阅。候选数不是1时，entry以missing_or_ambiguous_interface结束。提前启动旧
入口不会等到稍后启动的设备。本轮仅核验源码，未调用IORegistry或接收器。

新的arm_policy是**离线设计状态机**，不是已实现的接收器：

1. 先注册到达通知，再排空初始iterator；存在旧候选时停止，避免误选旧实例。
2. 显式记录进入被动等待；等待阶段不发USB请求、不重置设备、不打开数据pipe。
3. 一次新到达必须唯一且满足身份/描述符条件；模糊、超时、终止和拔出均停止，不重新选择。
4. 单次选择锁定后才进入原有严格准备与单burst流程；保存选择/回调/退出/失败历史。

模型检查覆盖唯一选择、二次到达、未注册先到达、已有实例、模糊到达、等待超时及选择后
拔出。模型本身不校验真实IORegistry身份，也不签发或消耗实机许可。未来实现需在新的
隔离主机源码/构建及采集门禁中验证通知生命周期、对象保留、回调并发与单次领取；当前
入口不能通过增加启动延迟来满足此设计。现有票据remaining0，不具备执行这一步的次数。

主机先等待只能减少启动延迟，不能保证设备启动后30秒内完成；设备窗口早于枚举完成，
主机尚无经认证的对应开始时间。未来一次诊断仍必须接受“窗口用尽，证据不足”的结果。
现有外层20秒wait也只是等待接收器结果，超期保留进程；不是强制结束期限。不能把它和
设备30秒窗口相加/相减，也不能据此强制释放未完成SDK缓冲区。

## 文件保存与失败保留

核验实际main及ep0_session_file入口，不把上一轮独立file adapter成功等同于main会调用它。

| main分支 | 当前实际保存路径与限制 |
| --- | --- |
| 任一线程join失败 | 保留服务/缓冲区；不触碰正常/诊断文件adapter；无REL2文件 |
| exporter身份查询失败 | 内存StartupOnly路径；保持服务，不据此认定有文件 |
| Finish成功 | 尝试OWN2保存，生成内存SessionJoined(false)，**未调用REL2文件保存** |
| Finish失败、DIA2保存成功 | 生成关联，尝试REL2；即使保存成功也不允许资源清理 |
| Finish失败、DIA2保存失败 | 保留失败/部分文件与内存；不调用REL2文件保存，无自动重试 |
| REL2保存失败 | 保留可能存在的文件，不能把可解码或文件存在当作commit成功 |

REL2文件adapter还要求内嵌DIA2、receipt及已确认的commit；**仅在正常分支补一个
SaveJoined调用仍会拒绝**。正常OWN2有recipe、boot/session、writer、账本和trace，但没有
落盘的INI1启动关联。REL2自身也不能在自身字节里认证“本文件最终commit成功”。

下一候选要独立设计正常导出与失败情况下的关联文件/保存receipt策略，保留join与ownership
保护、一次尝试和原失败字节；不得为增加可读证据而允许诊断清理、覆盖旧文件或隐式重试。
正常关联缺口与部分写入材料缺口分开验收，不能只放宽现有DIA2 receipt门禁。

## 新材料比较器能证明什么

输入为静止的原主机目录和指定OWN2/DIA2/REL2文件及预期recipe；不读取SD，不生成collection
许可。调用原严格host审查及独立V2解析器，保留原始文件哈希和错误。它检查：

- 主机原始STATUS回复字节/哈希、固定请求字段及既有完成/失败历史；
- 设备格式、CRC、recipe；多个设备材料的trace及身份一致性，独立DIA2与REL2内嵌DIA2一致；
- 接口2三步SETUP八字节顺序，以及两次status_snapshot的state/sequence；
- 冲突、缺请求、重复请求、坏CRC、错误recipe、缺主机材料等条件保持不确定或拒绝比较。

比较不读取设备STATUS全168字节快照（trace没有这些字节），不声称验证了整个回复payload；
不以形状、CRC、recipe或nonce认证物理来源、同一实机run、跨时钟对齐或USB通过。OWN2与
DIA2混入一个退出会话会被标出；缺接口2 BURST仍不证明事件未到达。

用**刻意无关联**的历史失败主机材料，分别比较V2 healthy/replaced/iso-pending/no-iso-event
四组模拟材料。全部保持不一致/证据不足：healthy虽有完全相同三步SETUP，但后置state2/
seq1与历史state0/seq0不同。旧失败不被改判。另用最大REL2与相同独立DIA2作正对照，
只确认局部关联，内嵌receipt成功仍不认证外层REL2的实际保存或硬件来源。

## 本轮封存、验证与接续

16项新增检查全部通过、0跳过；只针对本轮新增工具与执行边界，不宣称全库通过。
新审查25个条目、原V2候选396个条目、历史run17个条目均核验，七个生产输入和三份票据
哈希保持。原封存不修改，原失败根因仍未知。

- [执行审查](../private/analysis/A23-execution-readiness-review-20261015/audit.json)
- [四组材料比较](../private/analysis/A23-execution-readiness-review-20261015/associations.json)
- [逐字提取的线程函数](../private/analysis/A23-execution-readiness-review-20261015/actual-video-thread.c)
- [新审查封存](../private/analysis/A23-execution-readiness-review-20261015/SHA256SUMS)
- [回归与独立验证](../private/analysis/A23-execution-readiness-validation-20261015/validation.json)

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/audit_a23_execution_readiness.py --output /private/tmp/a23-execution-new
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/usb-ds-iso/tests /opt/homebrew/bin/python3.12 \
  -m unittest test_a23_execution_readiness -v
```

输出必须是新目录。下一步先实现隔离候选的处理前过期检查及正常/失败关联保存设计，
同时把被动等待状态机落到可离线验证的主机候选；之后只核对这些实际可达路径的线程/
TLS、栈与资源成本，再形成一次诊断准备。新格式变动必须独立版本化，原V2和生产保持。

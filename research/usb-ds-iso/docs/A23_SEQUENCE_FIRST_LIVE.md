# 序号49首次实测（2026-10-17）

续接：[SDK初始化与启动标记审查](A23_SDK_INIT_ENVIRONMENT.md)已完成；执行模式差异和外层错误覆盖有证据，实机根因仍未确认。下方保留实测与回收原始结论。

## 已完成只读回收，部署核验保留失败

本次保存59原件（封存61条），SD disk4于2026-10-17 15:49:12.786153+08安全弹出。原件哈希和快照结构全部核验；没有向卡写文件。相对上一轮51原件，新增9份诊断文件：三组EXE3/primary及三份LCP1；logfile.txt变化。8份ERPT及既有crash/fatal报告全部字节保持，没有新增保存错误报告。这不证明运行期间绝无错误。

**发现 `atmosphere/contents/00FF0000A53BB666/flags/boot2.flag` 缺失。** 上一快照它为0字节；本次同目录只剩旧AppleDouble伴随文件，不能替代标记。NSP、toolbox.json和IPS三项仍字节匹配。缺失原因及发生时间未确认，本次未修复或重新部署，也不据此断言SDK错误的原因。

回收工具在完成只读快照和安全弹出后，以deployment_files_match=false拒绝接纳完整回执；原失败结果保留在job/failure.json，job封存。实际记录仍failed_no_retry/remaining0，增加card_snapshot_saved=true/ejected=true/device_log_pending=false；recovered=false、recovery_receipt_accepted=false表示部署核验未通过，**不是尚未读卡或需要自动再读**。下一动作是离线审查。

## 新增设备记录

| EXE3前缀 | primary/EXE3字节 | trace记录/请求 | 匹配LCP1前缀 |
| --- | ---: | ---: | --- |
| 36f67 | 1120 / 2176 | 18 / 3 | f528 |
| 4e305 | 2976 / 4032 | 56 / 9 | dbf8 |
| e688b | 1120 / 2176 | 18 / 3 | c8de |

三份EXE3均通过CRC、recipe、内外身份和primary逐字节核对；primary保存phase9/result0、commit_acknowledged=true。三份LCP1均27条、main_return/result0，保存返回记录存在，按各自boot/session与上表EXE3对应。trace中的全部SETUP均为010b000001000000，没有序号49的BURST、STATUS或ISO post。它们是新增的三个设备上下文，缺少本次主机独有序号的关联；不挑选其中一个作为本次物理会话证据，也不把旧成功日志并入本次结果。

计数范围说明：旧主机报告的control_requests=0只表示未进入采集协调器、未调用其显式A23控制路径，不是整条USB总线零控制请求的证明。新增设备原件记录了SETUP=010b000001000000；这些常规请求的发起者未认证，总线控制请求总数未知。

本次默认沙箱中的diskutil无法使用DiskManagement；经允许访问系统磁盘服务后完成只读回收。这仅证明该读卡命令的执行环境受限，不能证明此前IOUSBHostInterface初始化失败由同一原因引起。后续优先离线核查采集命令的执行权限/沙箱与以往成功环境，再核实启动标记差异；不直接重试、改预算或放宽材料绑定。

## 回收封存

| 材料（private下） | 条目 | SHA256SUMS摘要 |
| --- | ---: | --- |
| `card-cycles/20261017-154709-sequence-first-live-read` | 61 | `5295dbfa00a9c9ad48e3e53e5797b4966f2f36d6f31f679600ef406023a37ca4` |
| `analysis/A23-sequence-first-live-device-analysis-20261017` | 15 | `ce3d69f74c607141a240dc0c2a8d440d3d158fd75df9dfcc96c5245599cf6f89` |
| `analysis/A23-sequence-first-live-recovery-job-20261017-154709` | 6 | `956eb5b2b2ac444e953ac1343b36c9859b1917af2d99210aedbca5263d50a3a6` |
| `analysis/A23-sequence-first-live-host-20261017` | 5 | `79aa835a48b8f6ce1c3a512899b3c8dcb1568d2ef2ef6068d6042519c24a07e1` |

272来源及全部旧保护记录再次核验保持；49..64保留回执仍匹配。续接 `private/analysis/A23-sequence-pending.json`，stage=evidence_saved_deployment_mismatch；主机旧结果及下方“待读卡”均保留为历史语境。

用户明确确认装卡、USB连接、完全关机并开始唯一一次新测试。正式发行先永久保留49..64，再写新记录；主机进入WAITING后通知开机，用户回复已开机。

本次失败在SDK初始化。等待器记录新的高速接口，device_id4298053092/interface_id4298053104，领取一次权限后尝试创建IOUSBHostInterface。结果为IOUSBHostErrorDomain，code=-536870199（0xE00002C9），description=Failed to create IOUSBHostInterface.，failure_reason=Failed [super init]，preparation_stage=sdk_init。当前本地SDK的IOReturn.h将0x2c9命名为kIOReturnInternalError；名称本身不提供根因，不能据此归因为接口占用、权限或设备问题。

entry.finished=true、waiter_closed=true、unresolved=false、started=false、host_result=null。未进入SDK采集协调器，ISO提交、BURST触发和该接收器的控制请求均0；因此没有序号49的STATUS或载荷样本，不能判定序号方案成功或失败。该一次记录仍为failed_no_retry/remaining0/acquisition_enabled=false，保留文件不可释放、补次或用于其他记录。

主机运行封存为 `private/runs/A-sequence-waiting-20261017-074442-869c4534`，session755262D7-7981-4B6A-97BD-AB5844921468。独立分析 `private/analysis/A23-sequence-first-live-host-20261017` 保存消费记录、等待器结果、逐项时序、判读和272来源核验。原构建、77项离线检查、旧成功原件及历史记录保持。

设备日志和新增错误报告尚未回收。当前不能推断设备没有运行错误，也不能把旧日志算作本次结果。准备job仅含plan.json，未访问SD卡。收到完全关机接卡确认后才动态识别、只读回收全部原件、核对四部署文件及新增日志/ERPT，再安全弹出。续接 `private/analysis/A23-sequence-pending.json` 和 `A23-sequence-first-live-pending-recovery.json`。

后续优先离线比较本次SDK初始化失败与此前成功的同入口路径，保留错误原文和资源领取顺序；不直接改变预算、重试、复用49或断言根因。下一序号/接收器或实测另行准备。

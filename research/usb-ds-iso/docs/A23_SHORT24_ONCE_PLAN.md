# 一次24字节短包诊断问题卡（已执行并回收，次数已消耗）

## 本轮更新：短包主机观察通过，设备文件保存失败，已收尾

已完成[首次短包实测与回归修正](A23_SHORT24_FIRST_LIVE.md)。配套NSP/IPS部署核验后，
用户确认物理条件，实际WAITING后开机；唯一一次513..528范围已消费。收到连续16×24字节
共384字节，IS24/STATUS与128项原生状态核验通过，control/ISO回调为0，abort=0。
关机后只读回收145件并安全弹出：新recipe的27条LCP1记录显示capture和EXE3创建均失败
`0xD401`，末态retain(reason5)，没有本轮完整trace/EXE3。整轮不判严格通过，不补试。
漏带已有路径缓冲修正的构建基线回归已确认；新离线14对象ELF的5个路径各769字节，
控制器不变，7个CPU/ASan专项场景通过。新修正版未打包、绑定接收器、部署或实测。
状态`private/analysis/A23-short24-once-20261027-state.json`为
`host_valid_device_save_failed_no_retry`，remaining0、acquisition_enabled=false、日志pending=false。
主机PID22208 / exec session2564继续驻留；关机后provider interest另存later-0001，
不覆盖采集时观察，也不授权自动kill/释放/复用。旧票据和消费namespace不变。
封存：`private/analysis/A23-short24-first-live-20261027-r1`，清单`e21b3aec…`。
下一步仅离线准备路径修正版配套包与新recipe入口；另定硬件范围，不恢复本轮次数。
下面未授权/未部署表述属于本轮启动前的历史说明。

## 启动前记录


| 字段 | 本次范围 |
| --- | --- |
| 问题 | 在HS interval1、MPS256、16个独立TD及lead32保持时，24字节载荷能否形成完整的主机/设备观察？ |
| 变化 | 每TD192→24字节，总长3072→384；新IS24图样/诊断标记及配套新NSP/IPS；标准UAC仍为后续独立问题 |
| 部署 | 完全关机后核对卡身份及当前内容，再配套替换exefs.nsp和对应IPS，逐文件回读。只对这两个文件写入；旧四文件回退材料已备 |
| 拟次数/范围 | 一次调用、一个burst，最多16个连续包；拟513..528，未保留/签发。失败不重试、不补轮或重启补试 |
| 接收 | 一次128×24字节ISO请求，保存全部3072字节raw和3584字节transaction表；BURST独立control回调，before/after STATUS完整保存 |
| 时间 | 等设备最多120秒；控制/ISO软件期限16ms/2s，runtime五秒poll预算。同步调用可超过预算，不是硬截止 |
| 启动 | 新授权及当次完全关机/SD装回/USB确认；独占消费在注册表/SDK访问前。实际WAITING后才提示开机 |
| 停止 | 错误、超时、interest、额外/缺失包、错误原生状态、未知归属、容量或写盘失败；最多一次ISO异步abort，停止后无新提交 |
| 主机收尾 | 原生打开后保留进程与对象，不自动退出/释放；SIGINT/SIGTERM仅请求停止。保存后可驻留，清理需另行处理 |
| 回收 | 明确完全关机后只读回收设备trace/EXE3/生命周期，核验部署字节与新recipe，安全弹出；不借回收追加测试 |

采集内容与判别：先报告实际SDK选择/打开、control/ISO返回及每项原生结果，再核对16个
IS24包、sequence/URB、设备384字节post及零长度IN ACK。完整材料还需设备终态、日志及
来源绑定；只收到正确raw不足以严格通过。材料缺失或观察矛盾时保留部分结果并说明无法
区分的分支，不自动补试或改判旧失败。

本次是短包可行性的有限诊断。成功也不证明持续音频、设备时钟同步、缓冲复用、SDK排空、
UAC生命周期或旧超时根因。主机驻留是有意保留资源，不代表已完成安全交还。

产物及摘要见[配套包与入口](A23_SHORT24_PACKAGE_AND_ENTRY.md)。卡最后回收基线为138件，
旧actual465和消费namespace保持；当前remaining=0、acquisition_enabled=false、日志pending=false。
没有真实授权文件、正式513..528 claim或新run。需要用户明确授权上述部署和一次实测，
再合并核对当次物理条件；本文和模型授权文件本身不构成该授权。

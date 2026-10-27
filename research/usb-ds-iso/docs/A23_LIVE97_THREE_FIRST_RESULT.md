# 三轮候选首次实测与读卡结果（2026-10-24）

本次一次许可及177..224整段已耗尽，整体失败、不重试。前两轮177..192、193..208保存了6144正确字节，STATUS/ISO7及设备URB关联一致；第三轮尚未提交，主机因`paired_resource_fault`停止，lease记录`interest_seen=true`。具体通知类型未留存，不能据此推断断线、设备崩溃或其他唯一原因。

用户确认完全关机后，原创建者通过已有保留对象通知接收器正常失败退出，native exit1并直接wait；没有从磁盘PID恢复控制权。随后按用户“读卡”要求以只读方式回收103原件并安全弹出，未写SD或追加USB测试。

## sysmodule 为什么退出

唯一与177/193两轮请求、状态/序号、Post及URB387/403链一致的新execution，记录`stop_reason=expired`，设备窗口为30.003024秒。关联的同boot/session生命周期有27条有效记录、closed/zero tail，末条`main_return/result0`。因此本次关联sysmodule按30秒诊断窗口正常结束；这组材料没有显示其异常崩溃。

但设备的正常到期不能直接解释主机第三轮为何没有启动：主机从第一次BURST意图到检测资源故障约1.006899秒；设备从sequence177到窗口到期约29.328564秒。这是两个各自时钟域的相对区间，没有做跨时钟校准，也没有interest通知的到达时刻/类型，不能把30秒到期写成该主机故障的已证实原因。

设备trace169条、无丢失/无效，除两轮预期请求外还记录一次额外SET_INTERFACE alt0广播，约在设备窗口4.641秒。其来源和与主机通知的关系未确认，不能补作interest类型或故障根因。

## 本次严格边界

| 项目 | 观察 |
| --- | --- |
| 实际ISO/BURST | 各2次；两组ISO/控制回调均各1次，abort0 |
| 保存序号 | 177..192、193..208；各3072正确字节 |
| URB | 387、403，设备均status3 |
| STATUS留证 | 四份原件与两轮保存文件一致，失败字段为空 |
| 第三轮209..224 | 未提交；仍随整段许可耗尽，不可补轮 |
| 主机终态 | stopped，`paired_resource_fault`，interest_seen/poisoned；无live-final接受回执 |
| 失败保存 | 两组已有owner快照及live-failure保存；计数不证明排空 |
| 进程结束 | 用户明确关机后exit1，实际创建者直接wait |
| 整体验收 | 失败；完整三轮收集器拒绝缺失的live-final，部分正确数据不追认为三轮通过 |

匹配execution为`ep0-365e6cc5576f1f2dc1c479255ea5f63126a857bbef14cd2acaecda63945152c9.execution.bin`，同boot/session的生命周期为`ep0-life-66626efde030f362b5a196cfdf7cb9ff.bin`。外部primary与内嵌副本相同。设备关联核对请求/状态/序号/URB链，没有认证物理来源或逐字节绑定设备端完整STATUS。

本次另新增一个trace0、无ISO的execution及其正常返回生命周期；它不匹配本次采集，保持独立上下文。不能据新增文件数量推断用户启动次数。两份旧recipe不匹配生命周期继续排除，不追认。

## 只读回收

卷UUID`37614F76-3E12-3470-B5C8-52B5A449C213`与既有SD一致，动态解析为disk4s1。沙箱内diskutil无法使用DiskManagement后，改用沙箱外身份检查；没有在错误环境下尝试读卡内容。实际回收重新核对UUID/外置物理盘/FAT32，必要时卸载并以readOnly/nobrowse挂载，复制后再次核对身份和全部字节，最后安全弹出。

相对97件基线新增6件，仅`logfile.txt`变化；96件既有非日志原件不变，未删除文件、无新增ERPT。四项部署文件匹配。新快照103原件已封存，旧97件build的现场新鲜度前提由此失效，只可归档验证，不能重启或续次数。

## 续研入口

下一项先离线审查真实IOUSBHost interest适配路径，明确它接收哪些message、当前为何任何interest都会污染lease，以及缺失的消息类型/参数/到达时刻应如何最小留证。保持失败关闭；在有证据前不忽略通知、不延长设备30秒窗口，也不追加同形测试。

若后续实测能增加信息，须绑定当前103件基线、623及后续新增来源、完整49..224消费历史和新范围，审查后再取得新的单次授权。当前177..224已耗尽、remaining0、日志已回收且SD已弹出。第三轮能力、持续流、长期稳定、quiet drain与此次主机故障根因仍未确认。

## 证据位置

以下相对`research/usb-ds-iso`，各目录有SHA256SUMS/COMMITTED。

- run：`private/runs/A-three-epoch-d17498c1-9d08-4898-89e0-8695db23b842`
- 读卡原件：`private/card-cycles/20261024-live97-three-first-read`
- 读卡作业：`private/analysis/A23-live97-three-first-live-read-20261024-r1`
- 分析：`private/analysis/A23-live97-three-first-live-analysis-20261024-r1`
- 最终票据、来源和文档快照：`private/analysis/A23-live97-three-first-live-closeout-20261024`

actual record及授权文件沿用准备时固定的20261023文件名；实际授权、采集、读卡均在2026-10-24，日期不据文件名推断。

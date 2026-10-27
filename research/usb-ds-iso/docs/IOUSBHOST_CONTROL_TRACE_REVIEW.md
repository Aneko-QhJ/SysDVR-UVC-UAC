# A23 控制广播日志离线重审（2026-10-12）

已修正no-TD审计对EP0方括号字段的解释：实机字段是interface_index，Mock字段是请求序号。
原4411byte完整设备日志、主机run和读卡collection未变；重审observation_complete=true，failure_reasons为空。
960条原生状态0/实际长度0，overall0、raw全零的观察保持不变。原两行规则的拒绝报告仍在读卡周期中。

实机模式明确使用A23-interface-dispatch格式，保留原4条vendor记录，不去重、不自动切换格式。
只接受完整连续8行：接口0 STATUS/ignore、接口1 STATUS/ignore，重复两组。
所有vendor字段必须是c1/51/0/2/168，ignore须绑定紧邻的错误接口请求。
任意缺失、重复、错序、额外vendor、错误字段、孤立ignore、组间插入控制或连接事件均拒绝。
两行旧Mock日志在实机模式下拒绝；Mock模式仍保留原有规则。
标准枚举请求可存在于STATUS块前后，因此完整启动中的多次连接不会被误算为额外STATUS。
本规则依赖当前A23处理顺序；日志若交错应保守拒绝，不能无条件按文本去重。

来源：uvc_device.c的_handleSetupPacket、_handleIsoSetup和UvcDevice服务循环；当前源码与读卡时冻结源码相同。
主机journal已验证两个独立原始回复。广播形状与这两个回复一致，但日志没有总线请求ID，
inferred_status_requests=2只为解释；request_count_verified和bus_capture_verified保持false。

121项相关Python回归通过，无跳过；新增7项广播边界测试。原4个硬件格式Mock collection
在临时目录转换为接口分发格式继续验证成功/失败及政策边界，旧冻结Mock原件不改。
实际CLI对保存的collection重审exit0；USB请求0、SD访问0。未改设备/接收器代码，无新部署包或入口次数。

baseline_accepted、allow_next_burst、empty_status_policy_verified、callback_drain_verified、
hardware_verified、usb_strict_pass、bus_phase_verified均false。
下一步在电脑上核对IOUSBHost transaction的status/completeCount/timestamp语义，明确空槽政策证据要求。
本次观察不能解释旧接口Underrun/NotSent分歧或证明长期稳定性，无需重跑同一空窗口。

重审目录：private/analysis/A23-IOUSBHost-control-dispatch-20261012-200013
原始collection：private/collections/A23-IOUSBHost-no-td-20261012-195405/
原始读卡周期：private/card-cycles/20261012-195405-A23-IOUSBHost-read/

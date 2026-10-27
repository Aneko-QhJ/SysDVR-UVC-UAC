# A23：逐次原生状态核验与最多16次串行验收

2026-10-09实机最多16次测试在第1次原生错误后停止；完整设备日志已核验。
停止机制已观察到生效，串行成功和环回绕未验收。该旧工具阶段已停止；新同backend工具已在第4轮失败后停止，见[新串行验收](MATCHED_SERIAL_VALIDATION.md)。
旧失败记录保留；
事实及后续条件见[当前状态](STATUS.md)和[测试计划](TEST_PLAN.md)。

## 目的与冻结条件

`microframe-audit-1`曾在两次独立启动各一次严格通过，完整2631/2391byte设备日志匹配。
为检查同一设备会话连续使用和真实环回绕，`native-guard-serial-1`保留卡上A23、
host64/request192/40ms/960槽，单个接收器进程最多16次burst；每次严格通过才允许下一次。
设备保持HS/interval1/MPS256，每burst16个192byte独立TD，只有一个URB在途。
本阶段不覆盖SS、UAC或长期稳定性。

## 逐轮停止机制

工具复用微帧观察版的原静态库/backend，不增加总线查询，不修改原生返回码或公开状态映射。
每次callback保存raw后，从wrapper传入绝对路径的native stderr文件读取本轮证据。
按文件身份和读取位置仅消费本次记录：必须完整960条、indices0..959，overall全部0，
request192和公开长度一致；16个有效槽actual192且native0，公开actual逐槽匹配。
空槽`E00002E7`原样保留，不归一化为成功。

缺失、格式错误、乱序/重复、截断/替换文件或raw保存失败都会关闭下一次提交条件。
设备完成另须自己的URB/report ID匹配、status3/3072以及ISO7 terminal1/FFFF/actual3072。
原submit/wait/control/status/cancel逻辑及各次末尾50ms等待保留；CLI上限为16次。
完成URB不取消，失败不自动重试；pending/retained先保存证据再按DMA所有权流程处理。
callback新增本地文件读取会延长处理，不能视为与微帧观察版时序完全相同的因果对照。

## 本地验证

构建工具为`tools/build_native_guard_receiver.py`，冻结产物在`private/host-A23-native-guard-serial/`。
实际SDK编译及11个真实callback场景通过，包括公开成功但原生错误、overall错误、
request/actual不符、缺少/重复/损坏记录、文件缺失和截断；各场景保留raw。
3个真实CLI模拟场景确认第二轮native失败或位图不完整时，不进行第三次提交或trigger，取消数为0。
3项无效参数在USB访问前拒绝；3个独立分析器场景匹配保存原始文件。
原backend/库SHA256相同，receiver移除新增核验后与微帧观察版逐字节一致。
这些模拟验证不能代表16次串行已实机通过。

## 2026-10-09 16:44实机结果

fresh IDLE/HS/interval1/MPS256预检通过；目标16次，实际只有1次提交/trigger/callback，
退出1、无超时，无第2次提交。16包seq1..16/exact192 raw正确、indices566..581连续，
但有效包native E00002ED/public错误、overall E000400E；逐次核验读齐960条并阻止继续。
自己的URB387/status3/3072及ISO7 terminal1/FFFF/actual3072完整终结，首两ED标签匹配，
没有取消或重投。环推进和回绕均未到达，不能标记16次通过或稳定性通过。

16:52回收完整3365byte设备日志：A23/HOS22.5.0/目标BuildID、runtime result0/22条、
唯一seq1/URB387、首控制字0AE01411和正常终结匹配主机；四文件不变，无新增错误报告。
16:53:16.212464+08:00安全推出SD。本轮读卡未改写文件或执行新USB采集。
run为`private/runs/A-A23-HS-native-serial-20261009-164428/`，collection为
`private/collections/A23-interval1-20261009-165246/`。

## 入口与独立验收

本旧工具的受版本控制入口为`tools/experiment.py test`和`tools/workflows/capture_native_serial.py`。
旧采集脚本要求`native_guard_serial_prepared`；旧阶段已停止，不能重用失败状态绕过次数限制。
当前`experiment.py test`按新准备阶段路由到`capture_matched_serial.py`，见[新串行工具](MATCHED_SERIAL_VALIDATION.md)。
`private/test-A23-native-serial.py`作为冻结历史文件保留，不用于绕过当前阶段检查。
wrapper在准备完成后先核验包/部署/工具哈希及fresh状态，再运行有界接收器，并保存全部证据。

`tools/analyze_native_serial_run.py`独立核验raw的sequence+ordinal、native/public和设备终结，
核对247可用TRB槽的两个ED标签、跨次环位置及cycle、至少一次可观察回绕。
每burst推进32个槽，单个起点不算环推进或回绕通过。
分析器只处理主机证据，其初始输出的`switch_log_pending`不代替后续collection及
`switch-log-evidence.json`的完整设备日志核验；最新日志已核验，以当前状态和收集记录为准。
CLI会写`serial-evidence.json`，不要在冻结run中重跑覆盖校验文件。

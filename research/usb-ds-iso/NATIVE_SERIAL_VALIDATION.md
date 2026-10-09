# A23：最多16次串行采集，逐次原生状态核验

microframe-audit-1 的两次独立启动单次HS严格通过，完整2631/2391字节设备日志均已回收。
本轮日志确认A23/HOS22.5.0/目标BuildID、runtime result0/22条、唯一seq1/URB387/
status3/3072及首控制字50F01411。16包raw正确且567..582连续、native/public0、overall0。
四文件仍匹配A23，15份旧错误报告无新增/变化。设备handler至ACK0.463073ms。
本轮首TRB虚拟地址5CB777E000、模块base5CB7600000，偏移17E000；此前常见17D000。
旧收集脚本固定偏移的检查已修正：`iso_burst_context.S`从端点结构载入环指针，并不写死
模块偏移。本轮按模块范围、页对齐、配置及两条自己的ED标签匹配核验，不能将偏移变化
解释为传输错误根因。第一次检查中止时保存的原日志及原因保留在单独的未完成收集目录。

两次单次成功不构成持续稳定性验收，四次API返回读数均为8的倍数，真实微帧相位仍未解析。
下一步检查同一设备会话的连续使用与环回绕。保留卡上A23、host64/request192/40ms/
960槽；一个接收器进程最多16次burst，各次先完成独立native/raw/URB验收再提交下一次。
任一失败停止。实验只针对HS，UAC/SS及长时间稳定性仍未验收。

新主机工具`native-guard-serial-1`复用microframe-audit-1的原静态库和backend。
不增加总线查询，不修改原生返回码或公开状态映射；每次callback将raw保存后读取本轮
native stderr证据文件（由wrapper传入绝对路径）。按文件身份和读取位置只消费本次记录：
必须完整960条、indices0..959、overall全部0、request192与公开长度一致；16个有效槽
actual192且native0，公开actual必须逐槽匹配。空槽E00002E7仍原样保留。
缺失、格式错误、乱序/重复、截断/替换文件或无法保存raw都会关闭下一次提交条件。
设备完成还必须为ISO7、terminal1/bitmapFFFF/actual3072及自己的URB3/3072。

原有串行循环在payload/completion失败时停止；新增核验收紧这一条件。最多16次的CLI上限
避免无意无限验证。已有submit/wait/control/status/cancel逻辑及每次末尾50ms等待不变。
新增本地文件读取会延长callback处理，仍不是主机时序完全相同的因果对照；不得把成功
直接归因于interval1、查询或文件读取。

本地验证通过：实际SDK编译、11个真实callback场景（包括公开成功而native错误、overall错误、
请求/actual不符、缺少/重复/损坏记录、缺少文件、截断，均保留raw）；3个真实CLI模拟USB传输
场景确认第二次native失败或位图不完整时第三次提交和trigger均为0、取消数为0。
3项无效参数在USB操作前拒绝；3个独立分析器场景与这些原始文件匹配。
原backend/库SHA256相同，receiver逆向移除新增核验后与microframe-audit-1逐字节一致。
这些都是本地模拟验证，本轮没有执行任何USB测试，新主机工具尚未实机验收。

工具构建：`tools/build_native_guard_receiver.py`。
交付证据：`private/host-A23-native-guard-serial/`、manifest及SHA256SUMS。
下一次用户“测试”：`private/test-A23-native-serial.py`先核验文件哈希和fresh IDLE/HS/interval1/
MPS256，再运行一次`--burst --repeat16 --packets960 --trigger-delay-ms40`。
原生stderr路径由wrapper设置，不能复用旧文件。独立分析器`tools/analyze_native_serial_run.py`
验证每次raw与seq+ordinal、native和设备终结，核对247可用TRB槽的两个ED标签、跨次环位置/
cycle变化和至少一次可观察回绕；完整设备多次提交/ticks仍须随后读卡核对。
不得提前标记16次通过、ring wrap通过或稳定性通过。完成URB不取消，不自动重试失败采集。

2026-10-08 02:05已回收第二轮主机诊断的完整2391byte日志，安装result0/22记录及唯一
seq1/URB387/3072正常终结与主机一致；无新增错误报告。两轮microframe-audit-1单次严格
成功均已完整日志核验。17E000环偏移按端点动态环指针/模块范围和ED标签验证，修正旧脚本
固定17D000假设；原检查中止时的日志也保留。稳定性、真实微帧相位和根因未确认。
已构建[逐次原生状态核验的串行工具](NATIVE_SERIAL_VALIDATION.md)，本地11个callback、
3个完整CLI模拟、3个分析器及3项参数拒绝验证通过；每次native/raw/ISO7完整终结
通过后才可提交下一次，最多16次，任一失败停止。本轮没有实机执行该阶段。
SD四文件保留A23，未重复拷入；02:20:17.555537+08:00正常推出disk4并确认挂载消失。
下一步重启、关闭视频、USB2/HS，执行一次最多16次串行的接收器会话以检查环回绕。

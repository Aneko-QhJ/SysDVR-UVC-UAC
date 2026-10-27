# A23：主机微帧观察（microframe-audit-1）

本专题工具已在两次独立启动各完成一次严格成功采集，完整设备日志均已核验。
后续串行测试首轮失败，最新阶段见[当前状态](STATUS.md)；五次逐槽分析及无TD诊断方案
见[原生错误分析](NATIVE_ERROR_ANALYSIS.md)与[测试计划](TEST_PLAN.md)。

## 研究依据

原A23接收器两次独立启动呈现不同原生状态，raw均正确连续；完整5228/4551byte日志均已回收。

| 原接收器独立启动 | 00:01成功 | 00:39失败 |
| --- | --- | --- |
| 有效包native / overall | 0 / 0 | E00002ED / E000400E |
| 原始16包槽 | 连续456..471 | 连续522..537 |
| 相对FrameID声明窗口的参考槽偏移 | 0 | +2 |
| 发布前context八字 | 两轮相同 | 两轮相同 |
| 首两ED软件MFI差 | 1tick | 1tick |
| 设备handler至ACK | 0.321094ms | 0.330885ms |
| 主机控制请求耗时 | 45.932ms | 51.865ms |

这些观察不能定位根因：设备快照非原子，原主机调度记录只有整帧，两端没有独立同步。
因此保留A23/host64/request192/40ms/960槽/repeats1，只增加主机只读观测。

## 工具与测量边界

`tools/build_host_microframe_audit.py`从已核验libusb1.0.30归档隔离构建，在冻结backend上
增加`GetBusMicroFrameNumber`观察：ISO请求入队前后、vendor0x41/0x54 burst请求入队前后。
不为STATUS/预检额外查询，不增加USB请求，不改变原生返回码和公开状态映射。
记录原生返回码、valid、microframe、AbsoluteTime、查询前后mach ticks及timebase。
失败返回值原样保留、valid=false，不以失败读数计算相位。

本机SDK的IOUSBDeviceInterface197声明该API，atTime与取得总线帧号时刻的差可达1ms。
入队后观察不等于ACK或总线完成；额外查询/打印可能扰动定时，不能当作修复或严格因果对照。
[Apple USB说明](https://developer.apple.com/library/archive/documentation/DeviceDrivers/Conceptual/USBBook/USBOverview/USBOverview.html)
提供接口背景，不能证明HOS控制器行为。

实际SDK ABI、成功/失败返回和64bit AbsoluteTime拼接验证通过；新backend链接下4项真实
接收器测试通过、无跳过，覆盖callback、原生错误、960槽末端raw及参数拒绝。
移除五处插入后backend逐字节等于冻结版，receiver源码/header相同；47项设备侧验证沿用。
初次构建的UnsignedWide初始化错误已修正，失败构建记录保留；未替换Homebrew或系统库。
冻结工具、manifest及SHA256SUMS在`private/host-A23-microframe-audit/`。

## 两次独立单次实机结果

| 时间（2026-10-08） | 主机结果 | 完整设备日志 |
| --- | --- | --- |
| 01:41 | seq1..16/exact192，indices536..551连续，native/public0、overall0 | 01:49回收2631bytes，A23/runtime result0/22条、唯一提交与终结匹配 |
| 01:59 | seq1..16/exact192，indices567..582连续，native/public0、overall0 | 02:05回收2391bytes，A23/runtime result0/22条、唯一提交与终结匹配 |

两轮URB387/status3/3072、ISO7 terminal1/FFFF均完整终结，无取消或重投；四文件仍匹配A23，
15份既有错误报告无新增/变化。四处微帧查询均成功，但读数全是8的倍数，真实微帧相位未解析。
01:59的首FrameID1295推导首槽568、实际567，参考delta为-1；不能当作总线服务偏移结论。
成功轮的软件post/handler耗时也可比失败轮更长，尚无足够证据建立耗时与失败的因果关系。

01:59轮模块base5CB7600000、首TRB5CB777E000、模块内偏移17E000，早期样本为17D000。
`patches/iso_burst_context.S`从端点结构读取动态环指针，不写死模块偏移。
按模块范围、页对齐、配置和两条自己的ED标签核验通过；旧收集检查的固定偏移假设已修正，
第一次中止检查时的原日志和原因仍保留。

run为`private/runs/A-A23-host-microframe-20261008-014103/`和
`private/runs/A-A23-host-microframe-20261008-015927/`；collection为
`private/collections/A23-interval1-20261008-014910/`和
`private/collections/A23-interval1-20261008-020514/`。
02:20:17.555537+08:00已安全推出SD，未重复拷入相同文件。

两次单次通过后准备了[逐次原生核验的串行工具](NATIVE_SERIAL_VALIDATION.md)。
10-09该工具在第一轮原生错误后停止；两次单次成功仍不构成串行回绕或稳定性验收。
历史`private/test-A23-microframe.py`只作为冻结脚本保留，当前不安排用它继续采集。

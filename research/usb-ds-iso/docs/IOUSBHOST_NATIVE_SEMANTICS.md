# IOUSBHost 原生空槽与时间戳语义核验（2026-10-12）

已离线核对本机SDK、此前冻结反汇编和本次原始960条记录。没有实机请求、SD访问或新增凭据。
结论：status0/completeCount0可以作为本次驱动完成且传输字节数为零的原始观察，不能解释为192bytes有效数据，
不能据此恢复原始硬件CC、DATA PID或认定历史故障根因。无TD空窗口完整性已通过；原生政策仍未接受。

## 字段和调用边界

| 字段 | 本机SDK及源码含义 | 本次证据 |
| --- | --- | --- |
| status | 每笔交易的完成IOReturn；初始化Invalid，完成时更新；IOReturn.h定义success=0 | 960条均0，不是初始化零值：owner提交前显式写Invalid |
| requestCount / offset | 请求字节数和raw中的位置，由调用方设置 | 192 / 槽号×192，全匹配 |
| completeCount | 实际传输字节数，与完成状态分开 | 全0，raw184320bytes全0，无有效ISO包 |
| timeStamp | uint64_t AbsoluteTime，交易完成观测值；允许多个交易同值 | 全部非零，但只有120个不同值，每8槽共用一个 |
| overall | 完成回调单独的IOReturn | 0，不会证明每笔有192bytes数据 |

28byte packed布局与SDK及已冻结接收器的静态断言一致。owner先初始化Invalid并清零actual/timestamp，
在自己的回调内整份复制交易数组，不改status或overall。用户态framework完成回调也没有逐槽改写。
交易终结标志表示没有Invalid；它不是成功载荷或总线交易成功的证明。

Apple在线文档确认[IOUSBHostTime为绝对时间](https://developer.apple.com/documentation/iousbhost/iousbhosttime)。
transaction页面公开链接目前通过抓取工具无法返回字段说明，因此字段细节依据本机完整SDK头文件，
已随核验冻结；不使用第三方绑定替代本机SDK。

## 新旧接口差异的静态解释

旧UserClient完成路径0xfffffe000b361ad4比较内存描述符direction是否恰为In。
0xfffffe000b361bf0..0xb361c18在内部status0且direction==In、actual<requested时生成0xe00002e7 Underrun。
新transaction完成路径0xfffffe000b3a776c不包含这段旧frame兼容转换，用户态block回调也不做转换。
这些局部规则与旧空槽Underrun、新空槽0/0的差异相容，因此不能把旧Underrun要求直接套给新API。
本机27.0.1/26A434匹配静态输入版本，kernelcache SHA已复核；仍未核验历史失败时的驱动实例/描述符方向，
也未证明本次控制器的每个硬件事件。结论限于核验过的静态路径，不把相容解释称为完整根因。

## 原始时间测量

使用本次frame_sample保存的numerator125/denominator3，以整数/Fraction精确换算AbsoluteTime差值，
不读取当前timebase替代历史值，不把ticks直接当ns。新工具只测量保存的已通过观察审计的collection。

| 量 | 结果 |
| --- | --- |
| 不同非零时间戳 | 120个，120组，每组8槽 |
| 相邻槽相同值 | 840个重复值；不能要求960个唯一时间戳 |
| 第一个至最后一个时间戳跨度 | 118.992208333ms |
| 相邻槽时间差范围 | 0..1.022583333ms |
| 相邻槽差值平均 | 124.079466458µs；平均值不证明125µs线缆服务相位 |
| 第一个时间戳相对frame_time | 64.740041667ms |
| 最后一个时间戳至用户callback | 0.499291667ms；仅观察的软件时间差 |
| 提交到callback | 184.082541667ms |
| 倒序/早于提交/晚于callback | 均0，仅为本次数据特征 |

8槽成组与frame级完成采样解释相容；SDK明确允许中断延迟/系统负载导致同值。
时间戳不是总线捕获，不能判断每个槽实际服务时间、首包准确相位或队列排空。
不把唯一性或精确125µs间隔加为验收要求，不从平均值反推出真实总线微帧。

## 已完成验证和下一步

新增5项时间分析测试覆盖125/3精确分数、同值、缺失、倒序、边界异常以及非法单位/类型。
126项相关Python回归全部通过、0跳过，实际时间分析CLI exit0。
新工具analyze_io_usb_host_timestamps.py始终保持baseline_accepted、allow_next_burst、
callback_drain_verified、bus_phase_verified、hardware_verified、usb_strict_pass为false。
原始run/collection、旧拒绝报告和两次离线重审分别保留，不改写原始证据。

后续电脑工作：定义独立single-burst的诊断验收和停止条件，分别检查16个有效192byte包的内容/状态、
944个空槽原始状态、overall、唯一设备URB和ISO7终结；空槽状态不套旧Underrun条件。
还须核对生命周期/回调排空证据，明确哪些仅软件模型验证、哪些需独立实机验证。
本轮不把单次空观察升级为长期稳定基线，不安排重复空窗口或自动放行burst。

核验目录：private/analysis/A23-IOUSBHost-native-semantics-20261012-205827
原始collection：private/collections/A23-IOUSBHost-no-td-20261012-195405/

```sh
PYTHONDONTWRITEBYTECODE=1 python3 research/usb-ds-iso/tools/analyze_io_usb_host_timestamps.py \
  research/usb-ds-iso/private/collections/A23-IOUSBHost-no-td-20261012-195405
```

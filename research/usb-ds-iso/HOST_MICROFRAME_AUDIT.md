# A23 主机微帧观察（microframe-audit-1）

2026-10-08 第二次独立启动的4551字节日志已完整回收，A23启动标记、HOS22.5.0、
目标BuildID、runtime result0/record21（22条）及唯一seq1/URB387/status3/3072均匹配。
四文件SHA256仍匹配A23，15份旧错误报告无新增或变化。第二次严格验收失败，首次成功
证据保留；本轮没有执行USB测试，也不重新拷入相同SD文件。

| 独立启动 | 第一轮 | 第二轮 |
|---|---:|---:|
| 有效包native / overall | 0 / 0 | E00002ED / E000400E |
| 原始16包 | 正确、连续456..471 | 正确、连续522..537 |
| 相对FrameID声明窗口的槽偏移 | 0 | +2 |
| 发布前context八字 | 相同 | 相同 |
| 首两ED软件MFI差 | 1tick | 1tick |
| 设备handler至ACK | 0.321094ms | 0.330885ms |
| 主机控制请求耗时 | 45.932ms | 51.865ms |

这些观察尚不能定位根因。设备MFI快照非原子，主机调度只记整帧，没有独立同步。
下一步保留A23模块/IPS和host64/request192/40ms/960槽/repeats1，增加主机只读观测。

新工具`tools/build_host_microframe_audit.py`从已核验官方libusb1.0.30归档隔离构建，
只在冻结backend上增加`GetBusMicroFrameNumber`观察：ISO请求入队前后，以及vendor
0x41/0x54 burst控制请求入队前后。不会为STATUS/预检额外查询，也不提交额外USB请求。
记录原生返回码、valid、microframe、AbsoluteTime、查询前后mach ticks和timebase。
失败返回值保留且valid=false，不用失败读数计算相位，不更改传输返回码。

本机SDK的IOUSBDeviceInterface197声明该API，SDK说明atTime与取得总线帧号时刻
相差不超过1ms。这一精度不足以单独证明2个125µs槽的偏移；API也可能返回不支持。
入队后读数不是ACK或总线完成时间。额外查询/打印会扰动主机定时，仍需保存实际submit/
wait/trigger时间；不能把本次主机工具调整当作修复或严格因果对照。
[Apple USB说明](https://developer.apple.com/library/archive/documentation/DeviceDrivers/Conceptual/USBBook/USBOverview/USBOverview.html)
提供HS帧/微帧及等时接口语义背景，不能证明HOS控制器行为。

本地验证：实际SDK ABI编译、查询成功/失败及64bit AbsoluteTime拼接校验通过；
新backend链接下4项真实接收器测试通过、无跳过，涵盖callback/原生错误/960槽末端raw/
参数拒绝。移除五处诊断插入后backend逐字节等于冻结版本；receiver源码/header完全相同。
初次构建发现AbsoluteTime为UnsignedWide，已修正为结构初始化及hi/lo拼接，失败构建
记录单独保留。没有替换Homebrew或系统库；新工具尚未实机验证，47项设备侧既有验证沿用。

构建产物与SHA256位于`private/host-A23-microframe-audit/`；原A23构建包、两个实机run
及第一轮成功记录保留。下一次用户“测试”使用`private/test-A23-microframe.py`，先核验
原始包/部署及新工具hash，再做fresh IDLE、HS/interval1/MPS256预检，随后仅一次burst。
测试时视频关闭；任何失败停止，不串行重投。保留全部native/raw/JSONL/STATUS与四条
观察，按独立逐包native/public0/overall0、连续exact192、完整URB终结标准验收。
完整URB不取消；若异常未终结，先保留证据再按已有DMA所有权流程取消。
观察缺失或query失败不能声称诊断验证通过。随后读卡核对新的完整设备日志。

2026-10-08T01:37:28.095740+08:00再次核验四文件和4551byte日志后，正常推出disk4，
确认挂载消失。本轮SD写入0、USB测试0；下次重启后使用主机微帧观察工具单次测试。

2026-10-08 01:41主机microframe-audit-1单次HS采集严格通过：16包seq1..16/exact192，
indices536..551连续、有效包native/public0及overall0；URB387/status3/3072完整终结，
无取消/重投。四处只读微帧查询均成功，但读数均为8的倍数，真实微帧相位未解析。
新backend增加只读观察，不能将本轮视为原冻结backend的纯复现。稳定性和根因未确认；
本轮完整设备日志待读卡，当前下一步读卡，停止继续提交。

2026-10-08 01:49本轮2631byte完整日志已回收并SHA256核验，A23/HOS22.5.0/目标BuildID、
runtime result0/22记录、唯一seq1/URB387/status3/3072及首控制字51A01411与主机匹配。
模块base743E400000、首TRB偏移17D000匹配；四文件仍为A23，15份旧错误报告无新增/变化。
设备prepare0.049375/post0.374427/post至ACK0.000417/ACK0.117708/handler至ACK0.541927ms。
本次单次严格成功得到完整设备日志支持；post和handler时间比上一失败轮更长，
现有少量样本不能建立这些软件耗时与native失败的因果关系。主机四查询读数均为8的倍数，
真实微帧相位、总线服务时间和根因仍未确认。
下一步保持A23及同一microframe-audit-1工具/host64/request192/40ms/960槽/repeats1，
重新启动后做一次独立复现并停止提交，继续读卡核验。失败立即保留证据，不串行重试。
已重验原主机工具/receiver/backend/library/helper哈希，沿用通过的本地验证，不重复构建或测试。
本轮SD写入0、USB采集0；01:49:44.085333+08:00正常推出disk4并确认挂载消失。

2026-10-08 01:59同一microframe-audit-1工具第二次fresh IDLE/HS单次采集严格通过：
16包seq1..16/exact192/raw正确且indices567..582连续，native/public0、overall0。
URB387/status3/3072与ISO7 terminal1/FFFF完整终结，无取消/重投。四查询成功且计数均为8倍数，
FrameID1295推算首槽568而实际567，参考delta全-1，仍不能解析真实微帧相位。
工具/参数哈希与前轮相同，已有两轮严格成功；前轮2631byte日志已匹配，本轮完整设备日志
待读卡，暂不继续提交。稳定性与根因仍未确认，当前下一步读卡。

2026-10-08 02:05已回收第二轮主机诊断的完整2391byte日志，安装result0/22记录及唯一
seq1/URB387/3072正常终结与主机一致；无新增错误报告。两轮microframe-audit-1单次严格
成功均已完整日志核验。17E000环偏移按端点动态环指针/模块范围和ED标签验证，修正旧脚本
固定17D000假设；原检查中止时的日志也保留。稳定性、真实微帧相位和根因未确认。
已构建[逐次原生状态核验的串行工具](NATIVE_SERIAL_VALIDATION.md)，本地11个callback、
3个完整CLI模拟、3个分析器及3项参数拒绝验证通过；每次native/raw/ISO7完整终结
通过后才可提交下一次，最多16次，任一失败停止。本轮没有实机执行该阶段。
SD四文件保留A23，未重复拷入；02:20:17.555537+08:00正常推出disk4并确认挂载消失。
下一步重启、关闭视频、USB2/HS，执行一次最多16次串行的接收器会话以检查环回绕。

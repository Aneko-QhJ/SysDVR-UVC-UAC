# A23主机帧时间戳诊断

最新3350byte失败设备日志已核验：A23安装及唯一URB正常终结，raw16包精确，但主机
native/public报错。防自动休眠条件下仍复现，根因未知；首次16轮和实际回绕的完整验收保留。

## 本次离线推进

同backend22轮现有记录显示：入队前总线计数余量63..64帧，入队后62..64帧；失败轮为64/63，
与成功轮重叠。没有观察到应用侧的过去起始帧，不能将NotSent直接解释为应用迟交。
这些是查询时刻的软件观察，不能证明内核安排TD的时间、总线实际服务或设备侧微帧相位。
证据：`private/analysis/A23-bus-frame-margin-review-20261011/review.json`，冻结SHA256。

本地SDK及[Apple IOUSBLib接口定义](https://github.com/apple-oss-distributions/IOUSBFamily/blob/main/IOUSBFamily/Headers/IOUSBLib.h)
说明`GetBusFrameNumber`返回帧号和AbsoluteTime，时间关联精度约1ms。当前backend取出了atTime，
却没有保存。SDK中的GetBusFrameNumberWithTime是另一接口，说明的精度不同；本轮不替换API。
[Apple NotSent错误说明](https://developer.apple.com/documentation/iokit/kiousbnotsent1err)带有旧OHCI
控制器语境，不能据此认定现代Apple控制器的具体硬件原因。

## 新工具：只补充观察

`clock-audit-1`保留A23、ReadIsochPipeAsync、GetBusFrameNumber、lead64、40ms等待、960槽、
192byte请求、HS interval1/MPS256和全部原生错误处理。不增加USB查询，不改变设备环或FrameID。
只保存既有GetBusFrameNumber返回的atTime/帧号，并增加几个mach_absolute_time读数，记录
原有查询前后、入队前后、原生callback入口；新增JSON在完成时输出，不在入队之前打印。
receiver与原单次burst源码逐字节一致，静态库因观察字段及记录增加而改变，不能称为同backend纯复现。
时钟读取和输出仍可能影响时序，本工具不作为已验证修复。

新记录把帧号、API时间戳及入队时刻放进同一Mach时基。分析器使用mach_timebase的numer/denom
换算，要求字段齐全、时间有序、API成功、lead64、atTime符合1ms关联界限。
估计起始时间为atTime加64ms，再与入队前后比较；保留±1ms接口不确定度，不能称为硬件deadline。
它不会用CLOCK_MONOTONIC数值直接减Mach ticks，不会把有效raw覆盖native错误。

## 已验证范围

冻结工具：`private/host-A23-clock-audit-1/`，301文件SHA256。
源码生成：`tools/build_clock_audit_receiver.py`；分析：`tools/analyze_clock_audit.py`。
本地验证未访问USB：3个真实接收器模拟（成功、native失败、bitmap失败），4项参数拒绝，
8个时钟判定场景，3个完整分析模拟，2个防休眠入口生命周期场景，4项既有流程检查，
两层未准备入口拒绝。合成时间戳仅验证分析器，不能作为实机或总线时间证据。
冻结旧库、host、run及collection未修改；旧样本缺失的atTime不能事后补造。

## 本次测试入口（已消耗）

将SD放回Switch，重新启动A23，连接USB2/HS并关闭视频开流。fresh IDLE/seq0/URB0预检通过
后，只运行一个16包burst；本次不运行16轮串行。临时防休眠断言核验后才允许进入采集，结束后释放。

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py verify
python3 research/usb-ds-iso/tools/experiment.py test-clock
```

准备时普通`test`也路由到本次时钟诊断。现clock_audit_remaining=0；执行前先核验工具、分析器、
既有基线、完整失败日志和部署哈希，再消耗唯一次数并预检。失败即停，不自动重试、不取消已完成URB。
保存全部960条native、184320byte raw、STATUS、时钟记录和防休眠证据，随后读卡匹配完整设备日志。
串行next_test_repeats仍为0；前一个串行失败状态不会被该单次诊断改写成串行成功。

准备阶段只做离线核对、主机工具构建和本地模拟，USB采集0、SD写入0；卡上A23无需重部署。
若继续出现NotSent但观察余量充足，应继续区分内核/控制器调度与完成状态，不直接延长lead或改设备补丁。
若本次通过，也不足以证明错误修复、长期稳定性或上次失败由休眠引起。

## 2026-10-11 22:50实机结果：主机通过，待读卡

fresh HS/IDLE预检通过，防休眠断言采集前后有效且已释放。只运行一个trigger及callback，
16包550..565连续、3072byte精确，native/public/overall0；URB387/status3、ISO7 terminal1/FFFF，
首控制字55801411，context及own ED标签匹配。
唯一Mach记录有效：queried_frame197541075，start_frame197541139，lead64；
估计起始时间减入队前/后为63.955875/63.445917ms，接口不确定度±1ms。
未观察到应用侧迟交；这是成功样本，不能解释此前NotSent失败或确认内核/控制器安排及总线服务。

run：`private/runs/A-A23-HS-clock-audit-20261011-225058/`（10项SHA256）；
防休眠：`private/analysis/A23-awake-clock-20261011-225057/`（9项SHA256）；
只读重分析一致，工具301项SHA256核验通过。独立审计另存
`private/analysis/A23-clock-audit-result-20261011-225058/audit.json`，冻结证据未改写。
awake记录的backend_changed=false表示执行期间未再改工具；相对此前匹配backend，
clock-audit-1包含观察代码变化，仍不能作为纯复现或已验证修复。
次数0，完整设备日志待读卡；严格完整验收、长期稳定性和根因均未确认。

## 2026-10-11 22:55完整日志核验与安全推出

回收7676byte完整日志，SHA256 `cdedb7ae3ee49c0edf1ccce8a66cc908ff1181b12e1964d2d17facc7ee319871`。
A23/HOS22.5.0/目标BuildID，runtime result0/record21；唯一seq1/URB387/3072提交及
status3/3072终结、首控制字55801411、module至环偏移17d000与主机匹配，单次完整验收通过。
设备post0.265104ms、handler至ACK0.423750ms，落在此前成功范围内；成功样本不能解释此前NotSent失败。
日志23对connect/disconnect不等于23次ISO提交，也不能单凭记录判定重置原因。
四个A23卡文件匹配，21份报告无新增、删除或内容变化；本轮SD写入0、USB测试0，无设备更新依据。
22:55:54.816491+08:00安全推出disk4并确认挂载消失。
collection：`private/collections/A23-clock-audit-20261011-225522/`，29项SHA256核验通过。
冻结run及awake中的pending字段保留为采集时点记录；当前已完成核验。
下一步候选为有界串行Mach帧时间戳观察，需完成实现、本地验证和停止条件后才能准备实机；
当前次数0、入口未准备。根因、修复、独立串行重复性及长期稳定性仍未确认。

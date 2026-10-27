# 同backend单次burst对照（2026-10-09）

`burst-window-1`已在20:34完成一次fresh HS burst，主机侧验收通过；20:43完整2630byte设备日志核验匹配，单次完整验收通过。
16包连续且raw正确，native/public/overall成功，设备URB及ISO7终结、自己的首两ED标签匹配。
唯一次数已消耗，该单次入口保持停止。设备补丁保持A23，未新部署。
后续独立串行已在第4轮失败后停止、待读卡，见[同backend串行验收](MATCHED_SERIAL_VALIDATION.md)。

## 对照目的与边界

18:50无TD主机基线收到960个Underrun空槽，overall0，raw全零，无NotSent前缀。
读卡取得7005byte日志，确认A23/HOS22.5.0/目标BuildID、runtime result0/record21，
三个STATUS请求与主机预检及前后检查数量一致，没有burst请求或设备TD提交。
这一次无TD基线的完整日志核验通过；不排除间歇性问题，不证明根因或稳定性。

下一次对照复用该无TD工具的同一冻结libusb静态库、backend和时间记录，而非原串行backend。
主机新工具把无TD窗口换为一次burst：TD0显式FrameID、后续15个SIA由原A23设备实现。
保留HS/interval1/MPS256、lead64/request192/960槽、要求等待40ms。
burst控制请求及其原有微帧观察会新增到本次路径；两轮不同fresh启动，不能宣称控制流量与TD
已分别隔离。成功只证明这一次传输，失败保留原生错误并立即停止，不追加第二轮。

## 工具与验证

冻结工具：`private/host-A23-burst-window-1/`，32个文件SHA256。
源自已验证串行接收器，仅允许`--burst --repeat 1 --packets 960 --trigger-delay-ms 40`，
拒绝无TD、cancel、frames、其他重复数和参数组合。fresh状态预检与接收器内检查同时保留。
原生960条、raw、public、设备URB和ISO7必须一致；完成URB不取消，pending按既有所有权流程处理。

本地检查：3个真实接收器mock场景（成功、native失败、设备bitmap失败）、5项CLI拒绝、
3项独立分析结果核对、未准备入口拒绝，以及4项现有流程检查，共16项通过。
所有检查未访问USB；原设备包、无TD工具及实机run的冻结内容保持不变。

独立分析器`tools/analyze_burst_window.py`核对唯一次trigger/callback、16包raw及连续性、
native/public/overall、自己的URB、ISO7/context、首两ED自己的环标签和IOKit时序。
主机通过后仍要求读卡核验完整A23安装、唯一提交和终结；不会把target1算成串行或回绕通过。

## 运行入口

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py verify
python3 research/usb-ds-iso/tools/experiment.py test-burst
```

`test-burst`先检查独立准备字段及工具/分析器哈希、已核验无TDcollection和相同backend，
消耗唯一次数后再预检。预检失败也停止，不自动重试或重置设备。`test`为独立串行入口，当前已准备同backend最多16轮阶段。
需使用主机USB访问权限；沙箱中的“设备不可访问”不能单独判断实际连接状态。
当前无剩余次数，`test-burst`会在USB操作前拒绝，不应手动重新准备以追加重复。

## 20:34单次主机验收

run：`private/runs/A-A23-HS-burst-window-20261009-203446/`。
fresh HS/interval1/MPS256/IDLE/seq0/URB0预检通过，接收器退出0，trigger及callback各1。

| 观察 | 本次结果 |
| --- | --- |
| native | 16个有效槽status0/actual192；944个空槽Underrun/actual0，overall0 |
| raw与public | 索引618..633连续，seq1..16逐字节正确；公开transfer及有效包status0 |
| NotSent/NotResponding | 均未出现；错误前缀0 |
| 自己的设备终结 | URB387/report387/status3/requested=raw-count3072；ISO7 terminal1/FFFF/actual3072 |
| 首两ED | CC1/192bytes，自己的环标签匹配，handler MFI9184/9185 |
| context/首控制字 | 配置字段匹配；`47C01411`，FrameID1148，环起点`0000000B9AD7D000` |
| 取消、重投、第二次提交 | 均无，未发生串行环推进或回绕 |
| 时间记录 | frame查询0.003ms，IOKit队列调用0.433ms，submit0.512ms，等待43.004ms，控制请求65.662ms |

FrameID换算首槽616，实际618，差+2槽；原失败也曾出现+2，不能用该差值判断native通过或失败。
submit至原生IOKit callback入口183.427ms，同一CLOCK_MONOTONIC软件时基；不证明真实总线相位。
独立重分析与`single-burst-evidence.json`一致，10个run文件SHA256匹配。
复核：`private/analysis/A23-burst-window-result-20261009-203446/audit.json`。

无TD与burst在这一backend下各有一次主机成功；不能因此排除间歇性错误，或把新增时间记录当成修复。
20:43回收完整2630byte日志：A23安装、runtime result0/record21，唯一seq1/URB387提交、
3072byte正常终结及首控制字47C01411与本run匹配，完整单次验收为true。
collection：`private/collections/A23-burst-window-20261009-204302/`，20个文件冻结SHA256。
设备prepare0.051771/post0.201250/handler至ACK0.395260ms；不证明总线相位或错误因果。
四个卡文件SHA256匹配，15份报告内容无变化，20:51:21+08:00已安全推出，写卡0、USB采集0。
原run的待读卡字段保留为冻结时点记录，后续完整验收以collection和当前状态为准。

根因、总线相位、DATA PID、串行回绕及长期稳定性仍未确认。依据见[无TD诊断](NO_TD_WINDOW_TEST.md)。

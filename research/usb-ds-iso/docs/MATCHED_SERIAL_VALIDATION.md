# A23同backend最多16次串行验收

20:34的单次burst已通过主机验收；20:43读卡取得完整2630byte日志，确认A23运行安装及
唯一seq1/URB387/3072提交、终结和首控制字`47C01411`均匹配，完整单次验收通过。
SD四文件匹配、15份报告无新增或内容变化，20:51:21+08:00已安全推出。本轮SD写入0、USB采集0。

`native-guard-serial-2`最新于2026-10-11 21:07防休眠重试16轮主机验收全部通过，
观察到一次真实环回绕及cycle翻转；完整23382byte设备日志核验通过。
当前已准备[第二次独立启动复核](INDEPENDENT_SERIAL_REPEAT.md)，一次最多16轮，尚未执行。10-09第4轮失败与非fresh预检拒绝的原始证据保留。
设备保留A23，接收器链接成功无TD窗口和单次burst使用的同一冻结libusb静态库及backend。
它检查同一会话多轮传输与真实环回绕，不能仅因单次成功认定原生错误已修复。

## 逐轮条件与停止机制

先要求fresh HS、视频关闭、IDLE/seq0/URB0、interval1/MPS256。
保持host lead64/request192/960槽/40ms等待，每轮16个独立TD、合计3072bytes，一个URB在途。
下一次提交前必须同时满足：

- 960条原生记录完整；16个有效包native/public/overall0，raw保存成功且逐字节正确、连续有序。
- 自己的URB/report匹配，status3/requested=raw-count3072；ISO7 terminal1/FFFF/actual3072。
- context有效且配置匹配，TD0为显式FrameID、device lead32；首两ED均为endpoint7、CC1、192bytes，标签属于本次环。
- 页基址一致，247个可用槽每轮推进32，cycle仅在跨越Link时翻转，sequence逐轮递增。

任何条件失败都关闭后续提交。已完成URB不取消、不重投；pending/retained保留证据后按既有
DMA所有权流程处理。保存`serial_ring_gate`逐轮结果；检查不会写设备环或归一化原生错误。
最终主机验收还要求16轮全部通过、至少一次实际环回绕，以及每轮IOKit时序记录完整。
随后必须读卡匹配全部A23安装、提交及终结记录，才算完整串行验收通过。

## 本地验证与产物

工具：`private/host-A23-matched-serial-2/`，87个文件冻结SHA256。
源码生成入口为`tools/build_matched_serial_receiver.py`；独立分析器为`tools/analyze_matched_serial_run.py`。

本地验证通过，均未访问USB：247个起点×两cycle×16轮，共7904次有效推进；10种错误拒绝且
不推进状态；11种真实callback证据场景；5个CLI模拟场景，包括16轮及环回绕、3轮部分成功、
native/bitmap/ED错误在第2轮停止；5个分析场景、缺失时间记录和失败ring gate拒绝；5项CLI参数拒绝。
分析器时间记录为明确标记的合成fixture，只验证判定逻辑。另有未准备入口拒绝和4项流程检查。
这些结果均不代表实机串行、回绕或稳定性已通过。

## 已消耗的测试入口

以下为本次使用的入口；当前次数已消耗，`test`会在USB操作前拒绝。下一步读卡，保存完整四轮设备日志：

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py verify
python3 research/usb-ds-iso/tools/experiment.py test
```

入口先核验冻结工具、分析器、设备包、部署记录以及已验收的无TD和单次burst collection，
消耗唯一串行调用次数后进行fresh预检。预检失败同样停止，不自动重试。
接收器退出后保存所有native/raw/STATUS/JSONL及SHA256，转为待读卡状态，不追加测试。
需使用主机USB访问权限；沙箱访问失败不能单独说明设备未连接。

根因、真实微帧相位、DATA PID、视频共存、长期稳定性、SS及UAC/PCM仍未确认。
原`native-guard-serial-1`首轮失败证据保留，见[历史串行工具](NATIVE_SERIAL_VALIDATION.md)。
当前事实见[STATUS.md](STATUS.md)，单次验收见[BURST_WINDOW_TEST.md](BURST_WINDOW_TEST.md)。

## 22:34实际结果

4次trigger/callback，前三轮各16包严格主机通过，环槽0/32/64、cycle1。
第4轮slot96/cycle1仅收到14包、2688bytes，indices542..556中缺546；
设备URB435/status2/raw-count0，ISO7 retained80000017/bitmap000F/actual768，
匹配错误CC23/ED=false/TD index4。任一失败停止条件已生效，无第5次提交、取消或重投。
未到达环回绕，完整串行验收不通过，运行A23身份及四轮设备日志待读卡核验。
run：`private/runs/A-A23-HS-matched-serial-20261009-223428/`，13文件SHA256及只读重分析一致。

## 2026-10-09 22:41防休眠重试：预检停止

用户提出自动休眠可能造成第4轮失败并明确要求再试一次。保留上次冻结run，复用相同
接收器/backend，重新授权唯一有界调用；用caffeinate -dims临时防止自动休眠，
pmset断言确认在预检期间生效，结束后释放，未更改持久电源设置。
预检发现设备仍seq4/URB435/state3/status4，ISO7 retained80000017/bitmap000F/actual768，
不满足fresh IDLE/seq0/URB0。接收器调用0、ISO提交0，未取消或重置设备。
防休眠假设尚未实测，不能据此解释或推翻上次失败；先保存完整设备日志并重新启动Switch。
预检run：`private/runs/A-A23-HS-matched-serial-20261009-224150/`；
防休眠及重试证据：`private/analysis/A23-awake-retry-20261009-224149/`。

## 2026-10-11 21:07防休眠重试：16轮主机验收通过

用户重新启动设备后要求测试。相同工具/backend，fresh HS/IDLE预检通过，临时caffeinate -dims
在采集前后断言验证通过，结束后释放。16次trigger/callback，每轮16个192byte包连续、
有序、raw逐字节正确、native/public/overall0；URB/ISO7/context及首两ED自己的标签均匹配。
第8→9轮环槽224→9，cycle1→0，真实环回绕一次，16轮主机串行验收通过。
接收器退出0，无超时、无追加提交；完整串行验收仍需回收设备安装及全部16轮提交/终结日志。
本次成功不能证实上次CC23由主机休眠引起，也不代表长期稳定性已验收。
run：`private/runs/A-A23-HS-matched-serial-20261011-210736/`，25文件SHA256验证通过。
防休眠证据：`private/analysis/A23-awake-retry-20261011-210735/`；独立重分析与冻结证据一致。

## 2026-10-11 21:11完整设备日志验收

完整23382byte日志匹配A23/HOS22.5.0/目标BuildID、runtime result0/record21，
唯一seq1..16各自URB、3072bytes提交和status3正常终结、首控制字均与主机一致。
16轮串行与一次实际回绕完整验收通过；长期稳定性、根因及睡眠原因未确认。
collection：`private/collections/A23-matched-serial-20261011-211120/`，27文件SHA256冻结；
日志SHA256 `91be0c379ee171bcdb22bc5794275ca2d34bba224cac07bad7f8cd075584df24`。
21份报告含6份新增，崩溃日志指向hbloader/DGLAB-NX，未新增USB模块崩溃日志。
四文件哈希不变，21:13:16.061476+08:00安全推出，写卡0、USB采集0。
下一步[独立启动复核](INDEPENDENT_SERIAL_REPEAT.md)，复用相同工具和设备包。

## 2026-10-11 22:12第二次独立复核首轮失败

fresh HS/IDLE预检通过，caffeinate断言在采集前后有效、结束后释放。
实际1次trigger/callback，raw 16包543..558连续正确，URB387/status3/3072及ISO7
terminal1/FFFF/actual3072正常终结、context/ED匹配，但native有效包E00002ED、
overall E000400E/public报错，开头293个空槽NotSent，严格主机验收失败。
没有第2次提交或环回绕；10文件SHA256及独立只读重分析通过。
run：`private/runs/A-A23-HS-matched-serial-20261011-221215/`；防休眠：
`private/analysis/A23-awake-serial-20261011-221214/`。完整设备日志待读卡，次数0。
首次16轮及回绕完整验收保持有效；第二次完整独立验收未通过，稳定性与错误根因未确认。

## 2026-10-11 22:15失败日志核验与离线对照

完整3350byte日志SHA256 `8b5ae35b30695279733f1f75280ece83712c6bcf099bca8bf1dca006d01b301f`。
A23/HOS22.5.0/目标BuildID、runtime result0/record21，唯一seq1/URB387/3072提交及
status3正常终结、首控制字25501411与主机匹配，没有第2次提交。原生失败结论不变。
collection：`private/collections/A23-matched-serial-20261011-221535/`，27文件SHA256冻结。
四个A23文件匹配，21份报告无新增或内容变化；22:17:41.499720+08:00安全推出disk4，
确认挂载消失。本轮写卡0、USB采集0，无新设备包或补丁部署。

同backend四个run共22轮离线对照：20轮严格通过；一次CC23设备不完整、一次native/public
错误但raw与设备终结正确。本轮293个NotSent空槽前缀，20个成功轮均无该前缀。
本轮IOKit队列调用0.393ms、submit0.494ms、wait45.012ms、control61.053ms，
queue至callback183.269ms；这些软件时间不代表总线服务或125µs微帧相位。
设备post7.005625ms，比此前16成功轮的0.055417..1.034531ms长；但handler至ACK
7.198490ms仍落在成功轮0.203854..7.528646ms范围，不能从总耗时直接判定失败原因。
比较：`private/analysis/A23-matched-backend-review-20261011-221215/comparison.json`，
原始run只读核验，另存JSON和表格，未修改冻结证据。

防自动休眠条件下仍复现错误；根因和睡眠原因未确认。保持次数0，不重复相同串行，也不根据
单个慢post样本改变FrameID、SIA或设备环。下一步优先定位主机ISO调度时基、完成状态和
NotSent前缀；候选诊断必须先明确变量、补齐验收条件和本地验证，再准备新采集。
本轮没有足够依据形成已验证修复或下一项USB诊断，保存研究进度并安全推出。
首次完整16轮及实际回绕验收保持有效，独立启动重复性与持续稳定性仍未通过。

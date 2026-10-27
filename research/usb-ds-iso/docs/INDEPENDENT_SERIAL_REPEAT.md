# A23第二次独立启动串行复核

2026-10-11第一次完整串行验收已通过：16轮各16个192byte包、raw/native/public/URB/ISO7/
context及自己的ED标签匹配，实际环槽224→9、cycle1→0，完整23382byte设备日志与所有16轮一致。
此前同backend串行曾在第4轮CC23失败。一次成功不足以证明问题已消失，先在另一fresh启动
复核重复性，再进入视频共存和长期运行回归；主机休眠原因仍未确认。

## 本次复核已执行并失败，当前停止

复用冻结的A23卡文件、`native-guard-serial-2`接收器及相同backend，不改设备或传输参数。
本次要求fresh HS/IDLE已满足，首轮native/public错误后停止；当前测试次数0，下一步读卡。
保持interval1/MPS256、host lead64/request192/960槽/40ms等待，每轮16个独立TD。
只允许一次接收器调用、最多16轮；逐轮严格验收及环检查，任何失败立即停止，完成URB不取消。
实际运行期间用临时caffeinate -dims防止自动休眠，断言核验通过后才允许调用采集流程，结束后释放。

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py verify
python3 research/usb-ds-iso/tools/experiment.py test
```

`test`路由到`tools/workflows/capture_awake_serial.py`，核验自身哈希及上次完整collection已验收、
已推出，再以防休眠包裹既有`capture_matched_serial.py`。后者核验冻结包/部署/backend和次数，
消耗唯一调用后fresh预检，预检失败也停止。没有自动重试、取消或重置设备。
保存独立run、原生960槽×实际轮数、raw、STATUS、主机JSONL、休眠断言及SHA256。
工具新增入口在未准备状态拒绝；两个模拟验证断言成功时只调用一次、断言缺失时不调用，
两种情况下都释放防休眠并冻结证据；另有4项流程检查通过，均未访问USB。

主机16轮及至少一次实际回绕通过后，还需读卡匹配本次启动、A23 runtime及所有提交/终结日志。
目标为两次独立启动的完整16轮验收，目前完成1次；连接次数和同一日志中的STATUS次数不能代替
独立启动。第二次成功仍不自动证明长期稳定性、视频共存、SS、DATA PID或音频通过。

上次新收集的6份报告已归档，其中两份10-10崩溃日志指向hbloader/DGLAB-NX，未新增USB模块
崩溃日志；二进制erpt原因未解码，不推断与ISO测试的关系。旧第4轮失败的主机证据保持冻结。
卡上四文件SHA256与原A23包一致，未重复部署；10-11 21:13:16+08:00已安全推出，写卡0、采集0。

完整验收证据：`private/collections/A23-matched-serial-20261011-211120/`，27文件冻结。
详细机制见[MATCHED_SERIAL_VALIDATION.md](MATCHED_SERIAL_VALIDATION.md)，事实见[STATUS.md](STATUS.md)。

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

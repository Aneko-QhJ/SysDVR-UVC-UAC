# A23有界串行Mach时间戳诊断

此前防休眠串行失败中，raw16包及设备URB正常终结，但native/public报错，开头293个NotSent空槽。
当时没有保存GetBusFrameNumber返回的atTime，不能事后恢复。22:50单次clock-audit-1主机及完整
7676byte日志验收通过，Mach记录有效、入队后估计余量63.445917ms（±1ms）。这是成功样本，
不能说明此前失败时的时钟余量。下一项诊断因此是收集有界串行成功或失败当轮的同类观察。

## 变量与证据边界

新工具`serial-clock-1`链接冻结clock-audit-1的同一静态库，backend源码及库SHA256一致；
receiver源码与已验证的native-guard-serial-2串行源码逐字节一致，改变链接库以补齐时间记录。
设备A23、lead64、40ms等待、960槽、192byte、HS interval1/MPS256和16包burst均保持。
不增加USB查询，不改变ReadIsochPipeAsync调用或设备FrameID/SIA。相对旧串行backend，
Mach观察仍有新增代码和时序开销；不是同backend的纯重复，也不是已验证修复。

最多16轮，一次入口调用；原生/public/overall、raw、device terminal、context、own ED及环
校验沿用已有失败即停规则。无取消或自动重试；完成URB不取消。每轮完成时保存一条Mach记录。
分析器要求每个callback对应一条clock和schedule，帧号一致、记录跨轮有序、时基一致及±1ms
关联界限；缺失/多余/乱序记录拒绝主机完整验收。时间戳质量在采集后的分析中检查，
不额外作为接收器运行时停止条件；传输失败停止由原有native/ring gate负责。
保留原生失败及raw，时间估算不解释成内核入队时刻、硬件deadline或实际总线服务。

## 本地验证及冻结

冻结工具`private/host-A23-serial-clock-1/`，87文件SHA256；链接库由另一个301文件冻结工具保存。
真实C接收器模拟7项：环守卫、原生回调、3轮成功、native失败、bitmap失败、ED标签失败及
16轮实际环逻辑回绕；5项基础分析场景、5项CLI拒绝通过。
`tests/test_serial_clock.py`包含5个测试方法/14个场景：完整16轮、3类失败停止、6种时钟拒绝、
2种防休眠生命周期、2种入口场景（旧哈希阻止USB及预检失败消耗次数并阻止第二次调用）。
4项流程检查与未准备的两层入口拒绝通过。全部时间记录为显式合成测试数据，USB访问0。

## 已准备的一次实机诊断

SD已推出，卡上A23无需改写。将卡放回Switch，重新启动A23，连接USB2/HS并关闭视频开流。
必须fresh IDLE/seq0/URB0；工具及基线哈希核验后消耗一次入口，预检失败也不会自动重试。
临时caffeinate断言核验后才采集，结束释放，不修改持久电源设置。

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py verify
python3 research/usb-ds-iso/tools/experiment.py test-serial-clock
```

普通`test`也路由到本项；serial_clock_remaining=1，serial_clock_max_bursts=16。
旧单次clock及旧匹配串行次数均0。仅准备工具，本轮实机采集0、SD写入0。
随后读卡关联完整安装、每个seq/URB、控制字和终结；主机通过仍需完整设备日志才形成验收。
即便16轮均通过，也不能认定原生失败根因或修复；若出现失败，则用当轮Mach记录与成功轮
比较，保留±1ms界限，继续区分应用观察、内核安排及原生完成状态。

## 2026-10-11 23:51串行Mach诊断：主机16轮通过，待读卡

已消耗唯一次数；fresh HS/IDLE预检通过，接收器一次调用，无watchdog超时。
16个trigger/callback均严格主机通过，每轮16包连续、3072byte精确，native/public/overall0，
设备STATUS为正常URB/ISO7终结，context及own ED匹配。环slot0/32/…/224→9/…/233，
第8→9轮cycle1→0，实际回绕一次。16条Mach记录与各轮schedule匹配、跨轮有序且时基一致。
提交完成后估计起始时间余量62.114000..63.632167ms（±1ms）；这些仍是软件观察，
不是内核入队或总线服务证据。此次没有失败样本，不能解释此前NotSent或认定修复。
防休眠断言采集前后有效且已释放。run25、防休眠9、工具87及引用库301项SHA256通过；
只读重分析一致，冻结证据未改写。本轮SD写入0，无第二次接收器调用。
run：`private/runs/A-A23-HS-serial-clock-20261011-235126/`；
防休眠：`private/analysis/A23-awake-serial-clock-20261011-235125/`；
审计：`private/analysis/A23-serial-clock-result-20261011-235126/audit.json`。
完整设备日志待读卡匹配；当前阶段host_serial_clock_captured_logs_pending，剩余次数0。
串行完整验收、根因、修复及长期稳定性未确认；旧匹配backend独立通过数量不因本轮而增加。

## 2026-10-11 23:55完整串行日志核验及独立复核准备

回收16352byte完整日志，SHA256 `fd43ef2284f55bea703154c79e3cf747a951ec44a6656f31d1141a5ee0fcc49b`。
A23/HOS22.5.0/目标BuildID、runtime result0/record21；全部seq1..16提交、对应URB/3072、
status3正常终结及各轮首控制字与主机匹配，完整串行及真实回绕验收通过。
本次module base4746800000、环基址474697e000；实际偏移17e000，不要求与上次分配17d000一致。
收集器首次固定旧偏移的断言失败，部分证据另存并明确标记incomplete；修正为本次环基址、
模块范围及每轮slot/cycle匹配后完成核验，原始日志未改写。

设备post0.047240..2.530625ms，handler至ACK0.237604..2.780208ms。第8轮post2.530625ms
仍成功，超过此前成功串行post最大1.034531ms；单凭慢post不足以解释失败。
16条Mach记录都是成功样本，先前失败缺少atTime，不能事后补造或确认因果。
四文件匹配、21份报告无新增/删除/变化，日志connect/disconnect各1次；
23:56:58.345567+08:00安全推出disk4，确认挂载消失。本轮SD写入0、USB测试0。
collection：`private/collections/A23-serial-clock-20261011-235558/`，29项SHA256通过。
冻结run中的pending字段保留为采集时点记录；当前已完成设备日志验收。

同serial-clock-1完整独立通过1次，目标2次；旧backend通过数量单独保留。
已准备一次相同receiver/backend/device的独立fresh HS/IDLE复核，最多16轮、失败即停、
临时防休眠。入口新增强制核验本次完整collection及哈希；5项诊断测试/4项流程测试通过。
无需新设备文件，不重复写卡；剩余入口一次，普通test和test-serial-clock均路由到本项。
根因、修复与长期稳定性仍未确认；两次通过也仅支持这个诊断配置的有界重复性。

## 2026-10-12 00:02第二次独立串行Mach复核：主机通过，待读卡

相同serial-clock-1接收器及backend、A23设备，fresh HS/IDLE通过；一次调用、16轮
trigger/callback全部严格主机通过，每轮16包连续、3072byte精确，native/public/overall0，
context/own ED及设备STATUS终结匹配。环slot0/32/…/224→9/…/233、cycle1→0，真实回绕一次。
16条Mach记录与schedule匹配、跨轮有序，提交完成后估算余量59.742292..63.621167ms（±1ms）。
防休眠采集前后有效且已释放，无watchdog超时，无第二次调用，SD写入0。
run25、awake9、host87及引用库301项SHA256通过，只读重分析一致。
run：`private/runs/A-A23-HS-serial-clock-20261012-000235/`；
防休眠：`private/analysis/A23-awake-serial-clock-20261012-000234/`；
审计：`private/analysis/A23-serial-clock-result-20261012-000235/audit.json`。
同工具独立主机通过2次，完整日志匹配仍1次；本轮完整设备日志待读卡。
当前阶段host_serial_clock_captured_logs_pending，剩余次数0；根因、修复及长期稳定性未确认。

## 2026-10-12 00:07第二次完整读卡核验：两次独立验收目标完成

完整15545byte日志SHA256 `11a49b5deeef873324e4e57bc6708d04bd042296973bc8b94958c456faa10514`。
A23/HOS22.5.0/目标BuildID，runtime result0/record21；seq1..16全部提交、对应URB/3072、
status3/3072终结及首控制字逐轮匹配；本次实际环偏移17d000、slot与cycle匹配并真实回绕一次。
设备post0.060625..0.663906ms，handler至ACK0.191302..0.837969ms。
四文件与21份报告无新增、删除或内容变化；日志connect/disconnect各2次。
00:07:48.550024+08:00安全推出disk4，确认挂载消失；本轮SD写入0、USB测试0。
collection：`private/collections/A23-serial-clock-20261012-000707/`，29项SHA256核验通过。

serial-clock-1相同接收器/backend，两次独立启动各16轮完整验收通过，共32轮、98304byte
有效payload及2次实际环回绕。32条成功Mach记录的提交后估算余量59.742292..63.632167ms
（±1ms）。2次完整独立验收目标已达到；只支持此配置的有界重复性，不是长期稳定性证明。
旧backend历史失败仍保留；新观察代码会影响时序，本轮无失败时刻样本，根因和修复未确认。
两次对照另存本collection的device-timing-review.json；冻结run的pending字段保留采集时点。
当前stage=host_serial_clock_logs_verified_target_met，剩余次数0，不安排第三次相同复核。
下一步离线明确新的诊断或稳定性目标、停止条件及证据，再实现和验证对应入口。
无新设备包、无需重复拷卡，不直接外推视频共存、SS/reset恢复或UAC可用性。

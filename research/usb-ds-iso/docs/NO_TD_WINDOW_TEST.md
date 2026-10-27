# 无TD窗口诊断（2026-10-09）

最新18:50一次fresh HS无TD窗口的主机基线通过：960槽全部Underrun、overall0，
无NotSent前缀，184320byte raw全零；设备在窗口前后均IDLE/seq0/URB0。
一次接收器调用、一次callback、没有burst控制请求、取消或第二窗口。
完整7005byte设备日志已回收，A23安装及无TD记录核验通过；根因与稳定性仍未确认。
[同backend单次burst对照](BURST_WINDOW_TEST.md)已在20:34完成一次主机验收，2630byte完整设备日志已核验通过；
后续[同backend串行验收](MATCHED_SERIAL_VALIDATION.md)已在22:34执行4轮，第4轮失败后停止、待读卡。

## 18:45预检历史

`no-td-window-1`已隔离构建并完成本地验证。18:45的一次预检返回`Device inaccessible`，
未运行接收器、未提交ISO窗口或设备TD。随后在具备主机访问权限的只读USB注册表检查中，
没有枚举到`1209:ca57`，也没有任何`1209`厂商设备。因此本次没有实机窗口结果。
不能把沙箱内的首次失败单独解释为设备状态错误；独立注册表检查确认当时目标未枚举。

该次失败后要求设备fresh IDLE、USB2/HS连接。18:50按再次测试请求重新准备，预检已通过并
完成一次窗口。保留当前A23文件，没有新NSP/IPS部署。当时串行采集阶段停止、次数0；后续新串行工具已准备，实机未执行。

## 工具与入口

新工具位于`private/host-A23-no-td-window/`，冻结323个文件SHA256，原包和旧接收器未改。
冻结记录包含源文件、隔离libusb静态库、接收器、预检、构建日志、本地验证及入口副本。

- 只允许`--receive-only --packets 960 --trigger-delay-ms 40`，repeat固定1；
  拒绝burst、cancel、frames、post-completion空窗口及其他参数组合。
- 强制HS、interface2/EP83/alt0、interval1/MPS256、fresh IDLE。
  运行时控制请求白名单仅允许STATUS，阻止0x54与其他设备提交请求。
- 保留lead64/request192/960槽及原有微帧观察；提交后等待40ms再pump。
  窗口内不轮询STATUS，结束后核对状态不变；raw必须保存且全零。
- 在同一CLOCK_MONOTONIC时基记录frame查询、IOKit队列调用前后、调用结果及原生callback入口。
  新记录在完成处理时格式化输出；原有观察仍可能扰动时序，不能作为修复证据。
- 独立`test-no-td`入口校验准备字段、工具及入口哈希，再进行fresh预检；
  每次入口消耗唯一执行次数，失败不重试。最多一次窗口，正常完成不取消；超时先保存并等待取消callback。
  外部watchdog记录异常终止，不把缺失证据当作通过。

统一入口从仓库根目录执行：

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py test-no-td
```

当前唯一次数已由18:50采集消耗，后一个命令会在USB操作前拒绝；不得手动把串行stage改成prepared。
重新准备应先检查上述设备条件、冻结产物和本次失败，独立记录新的预检/单次run。

## 本地验证

| 检查 | 结果 |
| --- | --- |
| 真实接收器在USB mocks下的12个场景 | 通过；有效空窗口、原生NotSent、记录缺失、格式损坏、非零raw、状态变化、非fresh、SS、错误MPS、超时取消、native路径缺失、raw保存失败 |
| 6项CLI拒绝 | 通过；日志文件及USB上下文创建之前拒绝错误参数 |
| 6项独立分析检查 | 通过；正常主机基线、原生错误、缺失native、缺失时间记录、非零raw、设备状态变化 |
| 4项现有流程检查 | 通过；串行失败gate仍阻止采集 |
| 原包/旧工具/最新burst run/collection/deployment的117个哈希 | 匹配 |

模拟场景验证无burst请求、最多一次提交、无额外窗口；超时场景仅取消一次并等callback后释放。
本地检查不能替代实机。分析器区分主机空窗口基线与完整设备日志验收：即使主机基线通过，
仍需完整A23启动/runtime日志确认没有设备TD，不能直接恢复串行测试或宣称根因解决。

## 证据与当前限制

- 预检run：`private/runs/A-A23-HS-no-td-window-20261009-184510/`；
  receiver_invocations0、device_trigger_count0、iso_submission_invocations0，preflight exit2。
- 具备主机权限的注册表检查：
  `private/analysis/A23-no-td-access-check-20261009/usb-registry-check.json`，目标未枚举。
- 本地验证：新工具目录的`validation.json`及`validation/`。
- 独立分析器：`tools/analyze_no_td_window.py`，只读输入、标准输出JSON、不访问USB。
- 构建/验证：`tools/build_no_td_receiver.py`、`tools/validate_no_td_receiver.py`；
  新目录构建，既有目录不能覆盖。
- 最新实机结果：18:50的一次主机空窗口基线通过，见下节；没有设备TD终结或稳定性结论。

## 18:50无TD主机基线

run：`private/runs/A-A23-HS-no-td-window-20261009-185001/`。
使用主机USB访问权限运行冻结入口；fresh HS/interface2/EP83/interval1/MPS256预检通过。
没有重复18:45沙箱内不可访问的预检，没有变更设备补丁。

| 观察 | 本次记录 |
| --- | --- |
| 接收窗口/原生记录 | 1个窗口，960条，全部requested192/actual0/status E00002E7 |
| overall/public | overall0，公开transfer及所有空槽status0 |
| NotSent前缀 | 0槽；未见E000400E或E00002ED |
| raw | 184320byte，全零，独立核验与callback保存一致 |
| 设备状态 | 前后IDLE/seq0/URB0，diagnostics全零，未变化 |
| callback/取消/设备trigger | 1/0/0；没有第二窗口 |
| host参数 | lead64、960槽/request192，名义120ms窗口，要求等待40ms |
| 实际等待 | 45.013ms |
| frame查询/IOKit队列调用/主机submit | 0.002/0.383/0.458ms |
| submit至原生IOKit callback入口 | 184.423ms；同一CLOCK_MONOTONIC时基 |

raw SHA256：`dd493585bde88d5307e760b29cdd3a721ad9fa8fa5cb16618c77889c0d6be401`。
原生时间排序、IOKit调用返回0、960条记录、公有状态及raw完整性均符合主机基线条件。
两个微帧查询成功，读数均99030024；仍不能证明真实125µs相位。
独立只读重分析与保存的`no-td-evidence.json`一致，run的10个冻结文件SHA256匹配。
复核产物：`private/analysis/A23-no-td-result-20261009-185001/audit.json`。

本次仅说明未发burst请求及设备TD的一次fresh空窗口没有复现错误前缀。
它不能排除间歇性主机问题，也不能把原失败直接定位为设备TD或控制请求错误。
新工具的时间记录会扰动观察，后续burst对照需要保持相同backend及观察，另行准备接收器与入口；
现有无TD工具不允许burst，旧串行工具也不是同一观察条件。

以上采集时没有SWITCH SD挂载，原run的日志待回收字段是冻结时点记录，保留不改。
后续读卡结果补充如下，不自动增加空窗口或恢复16次串行。

## 完整日志核验与安全推出

collection：`private/collections/A23-no-td-20261009-195940/`。
完整7005byte日志SHA256：`e421a6bccb88491949b52c7b01f4e0f4452b7aa7d305bb3a1c4c3b4fdc48ab3c`。
A23唯一启动标记、HOS22.5.0、目标BuildID、runtime result0/record21均匹配；
三次STATUS请求与主机预检和窗口前后检查数量一致，没有burst请求或设备TD提交。
结合主机fresh前后状态及卡文件一致，这一次完整无TD基线核验通过；后续核验另存collection，
不改原run的`switch_log_pending`或原始SHA256。

日志有23次连接/23次断开，没有同步采集时间戳，不能把它们算作独立启动次数或重连稳定性通过。
四个A23卡文件读回匹配，唯一目标BuildID IPS；15份报告无新增或元数据变化，
本次完整保存并记录其SHA256、推出前再次读回核对。未向SD写入文件。
20:05:07.283114+08:00正常推出disk4并确认挂载消失。
后续仅改变主机对照工具，20:34一次burst主机验收通过，详见[单次burst对照](BURST_WINDOW_TEST.md)。

原始推理与后续对照边界见[原生错误分析](NATIVE_ERROR_ANALYSIS.md)，当前条件见[测试计划](TEST_PLAN.md)。

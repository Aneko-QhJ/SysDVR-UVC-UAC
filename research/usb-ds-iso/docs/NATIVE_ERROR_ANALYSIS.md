# A23原生错误分析（2026-10-09）

五次独立启动记录中，三次单次严格通过、两次失败。新的共同特征是：两次失败的接收窗口
开头分别有271、314个空槽报`E000400E`，三次成功均没有这一段。五次的16包raw都连续且
逐字节正确，设备自己的URB和ISO7也正常终结。当前应优先检查接收窗口调度及其与控制请求
的交互；设备侧原因仍未排除，根因未确认。串行、回绕、稳定性均未验收。

本次只读分析，没有访问USB、读写SD或改动设备/接收器。冻结run共105个文件SHA256全部匹配。
它们分属不同主机工具，不能合并成某一工具的成功率或单变量实验。

## 逐槽证据

所有run都是HS/interval1/MPS256、host lead64、request192、960槽，burst16包。
每槽名义125µs，接收窗口120ms。索引从0开始；每行数量总和都是960。

| run时间与主机工具 | 开头空槽E000400E | 其他空槽E00002E7 | 有效槽与native | overall | 严格单次 |
| --- | ---: | ---: | --- | --- | --- |
| 10-08 00:01，原接收器 | 0 | 944 | 456..471，16×0/192bytes | 0 | 通过 |
| 10-08 00:39，原接收器 | 271：0..270 | 673 | 522..537，16×E00002ED/192bytes | E000400E | 失败 |
| 10-08 01:41，microframe-audit-1 | 0 | 944 | 536..551，16×0/192bytes | 0 | 通过 |
| 10-08 01:59，microframe-audit-1 | 0 | 944 | 567..582，16×0/192bytes | 0 | 通过 |
| 10-09 16:44，native-guard-serial-1 | 314：0..313 | 630 | 566..581，16×E00002ED/192bytes | E000400E | 失败 |

失败窗口在错误前缀后还分别有251、252个空槽，然后才是有效数据。
这里的“开头/然后”描述接收槽顺序；native记录在完成处理时输出，没有逐槽错误发生时间戳。
不能把表中的索引边界直接当成实时中断时间。

原生码含义已核对本机macOS SDK的`usb/USB.h`与`IOReturn.h`：

- `E000400E`：`kIOUSBNotSent1Err`，事务未发送。
- `E00002ED`：`kIOReturnNotResponding`，设备未响应。
- `E00002E7`：`kIOReturnUnderrun`，数据不足。无TD的空槽与有效数据槽分别统计。

Apple的[IOReturn定义](https://github.com/apple-oss-distributions/xnu/blob/main/iokit/IOKit/IOReturn.h)
支持后两项的数值及名称。错误名称不能独自证明断开、CRC、错误DATA PID或实际接收为0；
这两次失败的有效槽actual确为192，raw也正确。`E000400E`与SDK中的CRC/PID专用码不同。

## 设备侧与停止机制

五次均为自己的URB387/report387/status3，requested/raw-count3072，ISO7
terminal1/bitmapFFFF/actual3072；完整设备日志匹配唯一提交。
首两ED均CC1、192bytes、自己的环标签匹配，两个handler MFI读数相差1。
这只覆盖首两ED和软件观察，不能替代全部总线事务验证。

八个context dword在五次记录中一致：

```text
00010001 0100002E 80023001 00000000
01000C00 00000000 000C0000 00000000
```

它们支持已观察的HS ISO配置一致，不能排除快照之外的动态行为。
模块内环偏移17D000和17E000都出现在成功及失败记录中，不能按偏移直接解释错误。
观察首槽相对FrameID换算槽的差值依次为0、+2、0、-1、+6；不应据此硬编码相位修正。

最新run只有一次提交、trigger和callback，随后停止，没有第二轮、取消或重投。
因此本次没有发生串行回绕，不能将失败解释为回绕验收结果。
接收器每次提交前清空raw；最新失败是新传输的第一轮，不符合“上一轮残留状态/数据”的解释。
更早的原接收器已有同类错误，排除了“仅由新串行guard引入”的解释。

## 时序线索与限制

以`submit_before`为近似零点，用`64ms + 错误前缀槽数×0.125ms`估算前缀结束：

| run | 提交至控制请求返回ms | 名义错误前缀结束ms | 两者差ms | 设备handler至ACK ms |
| --- | ---: | ---: | ---: | ---: |
| 00:01成功 | 89.309 | 无前缀 | — | 0.321094 |
| 00:39失败 | 97.987 | 97.875 | +0.112 | 0.330885 |
| 01:41成功 | 99.671 | 无前缀 | — | 0.541927 |
| 01:59成功 | 103.070 | 无前缀 | — | 0.463073 |
| 16:44失败 | 102.836 | 103.250 | -0.414 | 0.452135 |

两次失败的边界接近控制请求返回，值得后续区分主机排队、控制请求和ISO首次调度的关系。
但frame查询精度为1ms，查询点晚于submit_before，两个时钟未同步，也没有总线抓包；
表中0.112/-0.414ms不能宣称亚毫秒一致或因果。成功样本的返回同样越过64ms，且耗时交叠，
“控制请求越过窗口起点必然失败”不成立。

设备测量从收到setup后的handler开始，不能覆盖主机请求提交至setup到达的过程。
0.3..0.6ms设备耗时与46..59ms主机控制调用耗时的差值不能直接算成设备或驱动阻塞时间。
增加微帧查询可能扰动时序，两次查询版成功不足以证明查询是修复。

## 源码核对

本次核对冻结接收器及其Darwin backend，而不是推断未公开的当前内核驱动实现。

- backend在`GetBusFrameNumber`之后加64，提交`ReadIsochPipeAsync`。
  现有记录没有该IOKit调用前后及原生异步callback入口的完整时间戳。
- IOKit异步callback先保存原生overall；完成处理输出全部960条native，再调用接收器。
  guard保存raw后读取这些记录，不能把callback读取文件解释为本轮初始native错误的产生点。
- libusb有独立的Darwin CFRunLoop事件线程；主接收循环的40ms等待并不等于整个IOKit事件处理停止。
  “改成持续pump即可修复”目前没有证据支持。
- `--receive-only`已有fresh IDLE检查、无TD、raw全零和状态不变核对，但会立即pump，
  没有burst路径的40ms等待。原样运行会同时改变事件处理时序，不能当成严格对照。
  此分支退出0只说明采集流程完成，不能当成native成功。

源码指针及SHA256保存在下述`source-audit.json`；对公开backend流程可参考
[libusb v1.0.30 Darwin源码](https://github.com/libusb/libusb/blob/v1.0.30/libusb/os/darwin_usb.c)。
本地版本另有保留原生错误及raw的诊断改动，不能以upstream替代冻结版本。

## 下一项诊断：一次无TD接收窗口

选定优先方案为保留A23设备与HS描述符，仅准备主机无TD诊断，不先改FrameID/SIA或环发布。
目标是回答：没有burst控制请求及设备TD时，fresh接收窗口是否也出现`E000400E`前缀。
这一次采集不能单独区分控制请求与TD的贡献，也不验收burst成功。

准备条件及方案：

1. 新主机诊断版本及独立入口；保持960槽/request192/lead64，保留现有查询和fresh IDLE预检。
   接收提交后仍等待40ms，再pump，省略0x54 burst控制请求；窗口内不额外轮询STATUS。
   提交前后及窗口结束后的STATUS核对seq0/URB0/IDLE，不制造设备TD。
2. 增补主机frame查询、`ReadIsochPipeAsync`返回及IOKit callback入口时间记录；使用同一
   monotonic时基，延后格式化输出，标记诊断的观测扰动。该版本用于后续对照也必须保持一致。
3. 本地验证无burst请求、不会提交第二窗口、超时保全及取消所有权、证据缺失拒绝与原生码保留。
   冻结工具另目录构建，不覆盖当前包；不能手动修改失败阶段绕过串行gate。
4. fresh启动、视频关闭，最多一次120ms名义窗口，取得960条完整native及184320byte全零raw。
   device状态保持不变，完整设备日志确认无提交。正常完成不取消；pending超时先保存再按所有权取消。

分析口径为独立的空窗口诊断：overall0或Underrun、各空槽0/Underrun且actual0记为无新增异常；
任何NotSent/NotResponding等原生异常照实分类，禁止套用需要16个有效包的burst通过条件。
任何缺失、状态变化、非零raw或超时使采集无效；程序退出0不替代上述核验。

若无TD也出现同类前缀，说明不需要本次burst TD就可复现，应优先定位接收调度；
若一次无TD无异常，只取得一次基线，不排除间歇性问题。随后评估同一诊断版本、另一次fresh启动
的一次burst对照，才有资格继续区分控制/TD交互。两者均不能直接恢复16次串行。

本分析形成时诊断工具尚未准备。随后工具及独立入口完成本地验证，18:45预检目标未枚举，
18:50再次准备后一次fresh空窗口及完整日志核验通过，详见[无TD诊断](NO_TD_WINDOW_TEST.md)。
[单次burst对照](BURST_WINDOW_TEST.md)已在20:34完成一次主机验收，2630byte完整设备日志已核验通过；
后续[同backend串行验收](MATCHED_SERIAL_VALIDATION.md)已在22:34执行4轮，第4轮失败后停止、待读卡。
当前阶段为`native_guard_serial_matched_failed_logs_pending`，次数0，下一步读卡。
推进条件见[测试计划](TEST_PLAN.md)。

## 可复核产物

五个明确run目录依次为：

```text
A-A23-HS-interval1-20261008-000112
A-A23-HS-interval1-20261008-003952
A-A23-host-microframe-20261008-014103
A-A23-host-microframe-20261008-015927
A-A23-HS-native-serial-20261009-164428
```

逐槽ranges、原始状态数量、raw独立核验、时序、context/ED及输入哈希保存在
`private/analysis/A23-native-error-review-20261009/comparison.json`；源码指针见同目录
`source-audit.json`。旧run缺失时只读`.git/experiment-artifacts/`归档，不恢复或改写冻结run。

从仓库根目录重新分析，标准输出JSON，不写输入、不访问USB：

```sh
python3 research/usb-ds-iso/tools/analyze_a23_native_errors.py
```

`--output`只允许创建新目录，拒绝覆盖既有分析。单次严格结果与旧证据分别核对一致。

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

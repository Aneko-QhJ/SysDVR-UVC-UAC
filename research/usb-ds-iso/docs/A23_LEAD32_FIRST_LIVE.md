# lead32 首次有效实测及只读回收（2026-10-17，Asia/Shanghai）

一次 lead32 ISO burst 收到 **16×192=3072 字节，逐包内容和序号均匹配**。主机、EXE3、primary 和显式上下文匹配的 LCP1 所供证据链完整，设备报告保存和正常返回。这支持接收窗口覆盖方向；尚未证明独立根因、重复性、长时稳定性或完整 UVC/UAC 功能。

## 两条独立记录

首次授权记录 `private/analysis/A23-lead32-once-20261017-interface2.json` 于13:07进入等待，120秒内未见新设备到达。没有领取SDK权限、提交ISO或发出触发；用户随后确认仍关机。记录已消费为 `failed_no_retry/remaining0`，不属于一次零载荷的ISO测试。最初一次相对路径调用在记录读取、消费和启动前被入口拒绝；改用规范绝对路径后仅启动一次等待接收器。

用户另行明确确认“已装卡接线并关机，可以开始新的一次”，才签发第二条 `private/analysis/A23-lead32-once-20261017-interface2-ready.json`。13:12:30启动，先观察到WAITING，再提示开机；随后捕获唯一新HS到达，只提交一次ISO和一次触发，没有自动重试。继续使用同一path-span设备包，没有新建或部署固件。

## 主机与设备观测

| 项目 | 本次结果 |
| --- | --- |
| 主机结果 | 退出0；无abort/超时；overall/native状态0 |
| 数据 | 960事务中索引4..19连续有效，16包各192字节，序号1..16及内容精确匹配；其余载荷为零 |
| STATUS | seq0/state0 → seq1/state2 |
| ISO URB | ID387，requested=transferred=3072，status3，report_count0 |
| ISO7 | terminal1，bitmapFFFF，actual3072；自己的TD/ED标签、上下文及ring指针检查匹配 |
| 完成时间 | 控制0.408375ms，ISO151.922042ms |
| 调度实值 | 查询4334ns；帧年龄159042ns；入队312834ns；触发间隔90125ns，触发年龄562000ns |

主机首帧26960666=current26960634+32，低11位794与设备目标FrameID794相等。仅在两端帧号可比较的条件下，目标落入接收窗口；有效事务索引4..19不能直接解释为物理总线上的“目标后4槽”。两端帧域没有独立对齐，SDK观察也不等于物理提交时刻。

旧lead64三个有效SDK样本均为零载荷、首TD CC23，本次则有准确载荷及完成报告。除lead外，候选也收紧了入队和触发预算；本次实测耗时同时满足旧、新上限，因此未观察到预算门槛拒绝造成差异。这使窗口覆盖成为优先方向，但前后对比不是严格单变量因果实验，也没有确认设备CC23的底层语义。

## 只读回收与显式关联

用户确认完全关机并接卡后，动态识别同一SD，进行只读回收，保存45个原件；四项部署文件仍匹配，未写卡，**13:15:07.401930+08安全弹出**。相对前次38原件，新增7件、无删除，既有原件仅 `logfile.txt` 改变。两个新增EXE3/primary组合、两个新增LCP1及一个新增系统报告全部保留，不根据文件数量推断开机次数或用户操作。

三份EXE3中，只有 `ep0-698c…execution.bin` 的三条接口2目标SETUP顺序、前后状态及序号与本次主机一致；对应primary为ownership4384字节、EXE3为5440字节，嵌入与外置primary匹配，保存receipt phase9/result0、读回及commit确认成立。启动44条API结果均0；7条URB均报告status3，无未匹配URB。静默轮询历史未完整记录，不能把trace_window_complete提升为true。

仅 `ep0-life-1ff8…bin` 的boot/session上下文与上述EXE3匹配：27条有效记录，zero tail，join成功、owner完成、两次create返回0、primary及EXE保存成功，最后main_return。另一新增 `c34…` 组合没有本次接口2目标请求，虽有自己的匹配LCP1，也不能关联本次主机。

分别冻结三份收集包，避免选择后掩盖歧义：

| 收集包后缀 | bound执行链完整 | 所供完整链 | LCP上下文关联 |
| --- | --- | --- | --- |
| all-lifecycle（全部6份LCP1） | true | false | false |
| context-associated（显式1ff8） | true | true | true |
| unassociated-new（另一个新增组合） | false | false | true，仅其自身上下文 |

`supplied_chain_complete=true` 表示所供字节、身份比较与顺序自洽；physical/source/hardware/root_cause/usb_strict_pass等认证仍false。设备报告正常返回也不能替代独立稳定性验证。

## 新增系统报告的限制

新增ERPT原件870字节，字面ErrorCode为 `2162-0004`；已保存原件、完整28字段解析及解析器。报告未提供ProgramId或boot/session关联，不能确定它来自SysDVR或这次受控采集，也不解释错误码的底层含义。此项保持未归因，不宣称本轮“没有任何错误”或系统稳定性已通过。

## 封存与续接

以下路径相对 `research/usb-ds-iso`；SHA256为各自 `SHA256SUMS` 摘要。

| 材料 | 条目 | SHA256SUMS摘要 |
| --- | ---: | --- |
| `private/runs/A-A23-lead32-waiting-20261017-050754-20b6477c` | 8 | 见该包manifest（等待超时） |
| `private/analysis/A23-lead32-first-live-host-20261017` | 7 | `0ce25ad89749da2e9d90762621bc63ff1a5812848d696c387dbc660620dff23a` |
| `private/runs/A-A23-lead32-waiting-20261017-051230-52dbb0b2` | 18 | `1761788675b6a66724139621cc0dfdfdb0d64bee68dba6647e4f022f45fb66da` |
| `private/analysis/A23-lead32-ready-live-host-20261017` | 见manifest | `9ad9b2ac76695c218921867f62d9d383e75c94d8fa3191aef3dca76a04721be9` |
| `private/card-cycles/20261017-131426-lead32-ready-live-read` | 47（45原件） | `03cb6005d370c99471c2f21388538f34c47d6457ad5af1e687832f2bedcff455` |
| `private/analysis/A23-lead32-ready-live-device-analysis-20261017` | 30 | `ec95daa964e85a49d8c72550212a127a4a7dca441593a33810145f96c463ba8e` |
| `private/collections/A23-lead32-ready-live-20261017-all-lifecycle` | 35 | `12185e4c0ef5ce23927ecc445cd8aa39d3623425469ca68809aff116a96de826` |
| `private/collections/A23-lead32-ready-live-20261017-context-associated` | 30 | `81103d1bd65c23a35eae62ed0da8a34b356785fca285c480ee6c4793156d4dff` |
| `private/collections/A23-lead32-ready-live-20261017-unassociated-new` | 30 | `ddf3f359b91dbdab7fb2d1936972bb37567e20541efafcd8427ec43ad5bb04c2` |

251项来源、7生产源、3旧票据、3旧离线记录和3旧实机记录哈希保持。此前80项离线检查通过；本轮没有改代码，因此未重复运行。首条过期待机记录和第二条有效记录均remaining0/acquisition_enabled=false。第二条保留采集时stage=`captured_logs_pending`，当前恢复状态以 `recovered=true/device_log_pending=false` 和续接pending的 `single_burst_recovered` 为准，不可因历史stage而再次采集。

先读取 `private/analysis/A23-lead32-pending.json` 及本页。下一研究优先级：

1. 保持固件和lead32参数，设计独立fresh开机复现，逐包、URB/ISO7、保存退出采用同一验收；保留所有旧文件并按上下文关联。正式执行需新的明确开始指令及全新记录，不能补次或复用当前记录。
2. 同时查清未关联ERPT的来源，再评估稳定性；不能以这次成功替代错误报告归因。
3. 复现成立后，再分别研究窗口边界、连续串行提交、ring所有权及UVC/UAC持续流；每次只引入可审查的变化。根因认证仍需要独立帧域/事件来源证据。

本轮结束于只读回收、分析和封存；没有启动后续测试，也没有新的部署或写卡。

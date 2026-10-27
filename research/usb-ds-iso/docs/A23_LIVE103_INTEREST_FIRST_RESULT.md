# 103件基线候选首次三轮实测（2026-10-25）

本次一次授权采集完成225..272三轮，主机严格分析和独立重读均通过，共9216正确字节。设备日志唯一匹配三轮请求、状态及URB；关联生命周期确认正常返回。接收器exit0，创建者直接wait，SD已只读回收并安全弹出。本次未观察到interest消息，旧177失败根因与持续流仍未确认。

| 项目 | 第一轮 | 第二轮 | 第三轮 |
| --- | --- | --- | --- |
| 序号 | 225..240 | 241..256 | 257..272 |
| 有效槽 | 6..21 | 0..15 | 5..20 |
| 正确字节 | 3072 | 3072 | 3072 |
| 新URB | 387 | 403 | 419 |

每轮960项transaction、16个有效载荷槽、前后STATUS及ISO7通过。共3次ISO、3次BURST、6次STATUS，ISO和control回调各为[1,1,1]，abort0。三轮共享同一session及接口，三个URB各不相同。SDK与入口证据、导出前后检查和接受回执一致，原生进程成功与独立消费者接受分别留证。

interest trace为claimed0、committed0、pending0、overflow=false、latch=false、rows空、complete=true；provider未poison。此处complete仅描述已观察前缀，不是原子快照或未来无事件的证明。本次没有真实故障消息可供分类，新的准备期/失败及关机后补充导出分支仍只有此前注入验证。旧177..224失败和未知消息类型保持。

## 执行与边界

用户于2026-10-25明确授权一次最多三轮并确认完全关机、装卡和USB连接；实际WAITING后提示开机，随后用户确认已进入CFW。按封存r2计划执行；授权/actual文件名沿用计划中的20261024标识，执行日为2026-10-25。

225..272整段已消费，remaining0，不再启动此入口。没有修改来源或固件，没有向SD写文件。632来源及旧保护项/四个旧namespace保持，新增namespace225及actual记录已留副本。三轮成功证明本次有界串行路径可完成；持续流、长期稳定、所有回调排空、跨时钟对齐和物理来源认证均未获得新证明，广义hardware_verified保持false。

## 设备关联与只读回收

109份原件中，唯一新增execution `ep0-857bcbf6c30f37118f3ede31f36478ecd964bfb8e2e5fc0ab8c88898bc536f44.execution.bin`与三轮链匹配：六次STATUS和三次BURST顺序一致，序号225/241/257，三次Post各3072字节、URB387/403/419 status3。216条trace无丢失或无效记录，外部capture与内嵌primary逐字节一致，primary回执报告commit已确认。

同boot/session唯一关联 `ep0-life-b8663d96aeae18098c6054c5abac3111.bin`：27条有效记录，reported_closed、zero_tail、无解码错误，writer和频率与execution一致，末条main_return/result0。设备窗口stop_reason=expired，实际30.006451秒，表明本次sysmodule按窗口到期正常返回。请求、状态、序号及URB关联不等于跨时钟对齐或物理来源认证，也未逐字节绑定设备端完整STATUS。

另新增一份无ISO trace/URB的execution及其生命周期，保留为独立上下文；不按新增文件数量推断用户开机次数。两份历史recipe不匹配生命周期仍被排除，不因本次成功追认。

SD UUID `37614F76-3E12-3470-B5C8-52B5A449C213`匹配，成功回收使用readOnly/nobrowse挂载，109份原件复制与哈希回读后安全弹出。相对103件基线新增6件，仅logfile.txt变化，102件既有非日志原件不变；四项部署匹配，无新增ERPT。没有写SD或追加USB测试。

首次读卡r1在普通卸载时被loginwindow否决，四个命令均已退出、未复制原件，失败保持封存。用户明确解锁并继续后，r2在锁内核对旧owner/失败凭据，记录解除并重新核验身份，正常卸载、只读挂载及弹出成功；未强制卸载或终止系统进程。新快照使旧103件build只能归档验证，不能再按current103执行。

本次有界三轮主机与设备链一致，设备正常返回；旧interest类型和根因依然未知。后续研究以新增信息为目标，不自动再测，若扩展实验需当前109件基线、完整消费历史、新范围与新授权。

## 封存材料

路径相对research/usb-ds-iso，摘要为SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| private/runs/A-three-epoch-4fb0204e-b8ab-4fc8-8fac-c5e3879aa5a0 | 0ac1458cbc1e24e475f64a6338e8d0a79853014b841f7692939e255e2c827759 |
| private/analysis/A23-live103-interest-first-host-20261025 | fdeeea4a4512549b0f9ca125f49c67022b77f0942dfc659d9bc960f5e584279e |
| private/card-cycles/20261025-live103-interest-first-read | b47f9e2f8598285e7d20bc0a3790572476e80c6a7f9437080381d4476271f3cd |
| private/analysis/A23-live103-interest-first-read-20261025-r1（卸载失败） | 3d41890cf44c7feaaff14a60f74a520e108a974c059614c06f6243f7de6224d8 |
| private/analysis/A23-live103-interest-first-read-20261025-r2 | 9d86dcaa764d225c96ed7952f220f01bb63d53dc678afce240e73416224476f6 |
| private/analysis/A23-live103-interest-first-analysis-20261025-r1 | e82fe9124743c05140e2a22eb743fa04a7cdc86303d39ef1c45675df7fdfaeed |

人工授权留于private/analysis/A23-live103-interest-live-authorization-20261025。主机阶段交接保持在private/analysis/A23-live103-interest-first-closeout-20261025；回收后最终交接副本、ticket、actual与五个namespace摘要见private/analysis/A23-live103-interest-first-recovered-closeout-20261025。所有历史候选准备描述均以本页已消费状态为准；不得重复执行一次脚本。

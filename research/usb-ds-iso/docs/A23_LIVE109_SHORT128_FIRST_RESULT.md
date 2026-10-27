# 128项候选首测：等待超时与启动卡图标排查（2026-10-25）

一次273..320许可已经整段消费。本次接收器实际WAITING后，用户报告开机卡在Nintendo Switch图标；主机等待约120.310611秒后超时，未选中目标、未打开SDK、未提交ISO或BURST，收到0字节。接收器exit1且创建者直接wait，没有未决保留进程或重试。128项传输与名义48 ms回调尚未得到验证。

用户随后明确确认完全关机并把SD接入电脑。112份原件及启动配置/boot2标记已只读回收、哈希回读并安全弹出，四项实验部署文件匹配；相对109件基线新增3件，仅logfile.txt变化，108件旧非日志不变，无新增crash/fatal/ERPT。卡logo根因仍未知，未修改卡、启动配置、固件或来源，也未追加USB测试。

## 主机边界

entry保留wait_poll_failed，adapter末条reason2对应冻结策略的A23_W_REASON_TIMEOUT，候选数0。selection_claimed=false、prepared=false、started=false、driver=null、provider_failure=null、resources_retained=false，缺少sdk-claim、session及epoch目录。不是ISO提交失败或128项载荷验收失败；本次没有运行到这些阶段。

outer launcher对所有失败尝试interest消费者，留下provider preparation failure differs字符串。该消费者要求已有driver或带interest的准备期provider_failure，不能表示此处无SDK的被动等待超时；这个解析错误保留为原始证据，不是启动卡logo原因。无interest消息可从本次恢复。

## 新设备记录

唯一新增execution为ep0-ea35de6f06c4e18ed0cdd8ae7895f3f64d2992082c9906a75ccf89565c2b3075.execution.bin，与新增ep0-life-af1ad8661750e054fa69ceb28eb07f18.bin的joined_context唯一一致。外部capture与execution内嵌primary逐字节一致，primary回执报告commit已确认。

启动journal44条完整，无未完成调用或失败API结果；日志包含USB enable、video/audio启动返回成功。设备窗口stop_reason=expired，30.000247秒。27条生命周期reported_closed、zero_tail、无解码错误、writer/频率一致，末条main_return/result0，说明新增记录中的sysmodule正常到期返回。它不证明该程序与卡logo无关，也不排除其他未留报告的故障。

trace56条，无丢失或无效项。三个SET_INTERFACE alt0、wIndex1请求分别约在设备窗口0.284、7.305、29.395秒出现，每次广播到三个接口，共9组；仅有channel2的三个URB status3，没有channel8 ISO URB、iso_post、sequence或vendor STATUS/BURST。接口广播记录不等于9次独立总线请求，也不能单独证明重新枚举、请求发送者或卡logo原因。

新context只是相对上次快照的新增设备记录，没有本次主机USB请求链可匹配，也未校准主机与设备绝对时钟；不得把30秒设备退出直接对齐为120秒主机超时的唯一原因。用户没有提供卡图标持续时间，不用主机等待时长替代该信息。

## 启动配置的可核对线索

首次补充回收了hekate_ipl.ini、emummc.ini、system_settings.ini、override_config.ini以及6个boot2.flag，并保存缺失路径和目录标记清单。此前没有这些配置的基线，不能声称它们本次发生变化，也未采集/验证Hekate、package3、hoc.kip或外置secmon的二进制版本。

配置为autoboot=1、autoboot_list=0，第一项CFW emuMMC使用package3、额外kip1=atmosphere/kips/hoc.kip及secmon=atmosphere/exosphere.bin。第二项CFW emuMMC (No HOC)保留同一package3和emummcforce，但同时省去kip1和secmon。用户随后明确确认，本次实际使用CFW emuMMC（默认项）。这是用户报告的选择，不证明额外二进制的版本、兼容性或执行细节。

Hekate官方文档说明autoboot选择启动项、kip1添加/替换KIP，secmon覆盖security monitor。因此现有No HOC入口是两个配置差异的启动路径对照，不能作为单独HOC变量或HOC故障证据。[Hekate配置说明](https://github.com/CTCaer/hekate/blob/master/README.md)

实验模块及另外五个title目录具有boot2.flag；标记含义是要求boot2阶段启动，不证明本次实际执行或正确性。记录只用目录ID，不猜测其他模块名称或归咎于其中任何一个。[Atmosphère配置说明](https://github.com/Atmosphere-NX/Atmosphere/blob/master/docs/features/configurations.md)

上述官方当前文档用于解释配置键，不认证机器安装的版本。USB3强制项与GPU调度项的原值已保存，缺少变更前对照，不将其直接列为根因，也未自动修改。

## 后续与停止条件

用户在上述No HOC建议之后回复“不卡”。按对话上下文补充记录为No HOC入口不再卡logo；入口名称由上下文承接，用户未另行报告进入HOME、用时或其他操作细节。该观察由用户报告，尚无本次设备日志关联；助手未启动接收器、追加USB采集或改卡。原先封存计划中的“尚未执行”保留为该报告前的历史状态，当前观察见private/analysis/A23-short128-nohoc-user-observation-20261025。

用户随后补充“现在默认启动路径又不卡了”，并质疑是否错发数据。默认路径已有卡住和不卡两种报告，No HOC特有改善的解释因此下调，不能用此前两次观察指向HOC或外置secmon。当前原因未知，也不把默认恢复解释成长期稳定或配置无关。

复核了实际run/receiver摘要与冻结源码：等待阶段只注册IOKit matching通知、读取通知Mach消息；其绑定没有sendDeviceRequest、enqueueDeviceRequest、enqueueIORequest、IOServiceOpen、setConfiguration或pipe打开调用。entry须先到SELECTED、完成claimSelection并保存sdk-claim，之后才调用provider openCandidate。本次仍是selection_claimed/prepared/started=false、driver/provider_failure=null，且没有sdk-claim/session/epoch目录，和零实验请求/提交的记录一致，没有发现错发实验数据的证据。

这不证明USB总线上没有流量，也不是完整动态总线调用跟踪。三次标准SET_INTERFACE仍见于设备trace，发送者未认证；不能把它们归给本次接收器，也不能绝对排除macOS枚举、其他驱动或通知注册的间接影响。发送路径审查和用户默认恢复报告见private/analysis/A23-short128-send-path-audit-default-recovered-20261025。本轮未接触当前设备或SD，未重跑接收器。

128项接收研究仍未获得新传输数据，暂不重复；不因启动恢复自动恢复USB采集或安排更多启动。此前对No HOC线索的强调不足以支持因果判断，当前记录以默认路径也恢复、原因未定为准。

原观察计划是完全关机装卡后手动选择CFW emuMMC (No HOC)，其他设置保持，从选择入口起最多观察120秒，HOME或未成功后即停止、不补试。用户没有提供实际时长，不推定遵守了该时间上限，也不把它变成系统启动期限。后续如需要进一步定位，应先离线核对已知两项配置差异；新读卡、修改配置或实机对照须按相应范围另行执行，不修改本次已封存数据。

先前对照计划用于比较启动路径；已有默认路径也恢复的报告，当前不再把No HOC启动成功当成唯一差异，也不安排自动重试或额外改卡。更早已封存的boot分析和closeout保留“实际入口未知”的历史状态，用户默认入口确认见private/analysis/A23-short128-default-entry-confirmation-20261025，后续默认恢复与发送路径复核以新增审查为准。

273..320即使零提交也全段耗尽、remaining0，不能重启旧launcher。SD最后已安全弹出，日志不再待回收；新112件快照使109件build只能归档验证。未来采集需当前基线、完整消费历史、新范围及新授权，不能以插卡排查授权代替采集授权。

## 封存材料

路径相对research/usb-ds-iso；摘要为SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| private/card-cycles/20261025-live109-short128-first-read | 28e62453fb6ee2628a10775205a7bb49f98f73bbee8a666e29f5405c751ca54f |
| private/analysis/A23-live109-short128-first-host-failure-20261025 | b8d873d640f290fd979af344017e438b0a29fa3b27c7d0998c83df77af022592 |
| private/analysis/A23-live109-short128-first-boot-analysis-20261025-r1 | aa6820730c285a226af27767baf008a9cd165f19dbd3b3005f0139f7e4c000b1 |

run、读卡job、授权证据、636来源、六个namespace、actual273及最终ticket/交接副本见private/analysis/A23-live109-short128-first-result-closeout-20261025。原候选准备材料与此前成功三轮保持，不把本次失败升级为传输成功。

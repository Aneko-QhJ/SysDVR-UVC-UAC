# 120件基线lstat三轮首测主机结果（2026-10-25）

本次369..416单次三轮的主机链通过，共9216正确字节，接收器exit0且创建者直接wait，外层启动脚本也exit0。独立消费者重读与原collect输出一致，无abort、interest为空观察前缀。保存至下一轮的间隔为262.108/328.678 ms，较上次492.663/438.798 ms下降；ISO回调仍约47 ms。设备日志现已只读回收：唯一216条trace对应三轮，关联27条生命周期确认约30秒正常到期返回。持续流、回调排空及广义hardware_verified仍未证。

## 三轮数据与时间

| 项目 | 第一轮 | 第二轮 | 第三轮 |
| --- | --- | --- | --- |
| 序号 | 369..384 | 385..400 | 401..416 |
| 正确载荷 | 3072字节 | 3072字节 | 3072字节 |
| 有效槽 | 6..21 | 5..20 | 7..22 |
| 新URB | 387 | 403 | 419 |
| ISO提交至回调 | 47.500542 ms | 47.041500 ms | 47.223917 ms |
| BURST至控制回调 | 2.653334 ms | 2.696542 ms | 2.923042 ms |

各轮均保存全部raw24576字节和128项transactions3584字节，不过滤空槽。16个192字节包、全部transaction、前后STATUS/ISO7、URB唯一性及同一session/接口资源检查通过。ISO和控制回调各[1,1,1]，三次ISO/三次BURST/六次STATUS，无abort、无poison；interest完整空前缀、pending0/overflow=false，但不证明未来没有消息或回调已排空。

真实SDK导出前后完整检查与接受回执、独立重读一致。归档分析中physical_run_authenticated等保守标志保持false；本次命令执行、native进程及直接wait来自另行保存的实际workflow/外层记录，不用纯格式校验结果替代进程事实。

## 与上次固定128项结果对照

| 区间 | 上次321..368 | 本次369..416 |
| --- | --- | --- |
| 第一轮saved至第二轮before_intent | 492.662917 ms | 262.108417 ms |
| 第二轮saved至第三轮before_intent | 438.797917 ms | 328.678375 ms |
| 第一至第二轮BURST间隔 | 546.624084 ms | 317.455500 ms |
| 第二至第三轮BURST间隔 | 502.107917 ms | 385.853625 ms |
| 第二轮arm前完整检查 | 483.413417 ms（163号） | 258.663292 ms（342号） |
| 第三轮arm前完整检查 | 432.690250 ms（164号） | 325.169208 ms（343号） |

saved/before/BURST时间来自同一Mach域；完整检查来自CLOCK_MONOTONIC_RAW，序号归属由冻结串行调用顺序推定，不把两域绝对时间直接相减，也不精确归因两种时长的残差。各Mach区间按tick分段相加，显示向上取整最多差2 ns。

本次iso窗口、lead32、三轮、期限、每轮完整guard及设备部署保持；改为lstat后guard和轮间间隔同时下降，与先前本地剖析相容。但基线112→120、来源640→644、实际负载和开机时序不同，未随机化，不能唯一量化lstat的因果收益或保证以后相同比例。等待期总检查数348不是性能对照指标，不能和上次169直接比较。

344号末轮观察poll前检查292.996125 ms仍超过250 ms观察阈值，且检查/回调在同一串行主队列上；观察完成不证明持续处理或排空回调。最终导出前/后检查347/348号为319.506375/280.434625 ms，不当作轮间guard。continuous_streaming_verified、callback_drain_verified、hardware_verified保持false。

## 单次执行与用户观察

用户独立授权本次一次最多三轮，并确认完全关机、SD装回、USB连接。已封存的r1计划核对launcher/workflow/generated-workflow及native scope后，发行并消费唯一369..416许可；接收器实际WAITING后才提示默认CFW emuMMC开机。用户回复“已进入 CFW／HOME”，未单独重复入口名称，不补造确认。

job为68e29f36-c52d-4a97-b377-5be7be3443e3，receiver PID62908；前台创建者exec session94945已完成exit0，不再保留待退出的接收器。原WAITING观察和进行中ticket副本是历史记录，最终状态以workflow退出/直接wait及本次closeout为准。此次没有启动失败、重试、额外轮次或第二个接收器。

新范围整段369..416已耗尽、remaining0；新namespace17文件已留证。644来源、旧actual321/273及七个旧namespace保持。设备日志现为pending=false/recovered=true；126原件已回收并安全弹出，四项部署匹配。此次读卡未补造人类明确关机确认，回执如实记录false，物理卡身份和只读挂载已核实。采集阶段无SD访问，本次回收不写卡或改部署。

## 只读回收及设备关联

SD UUID37614F76-3E12-3470-B5C8-52B5A449C213核对通过，普通卸载后只读挂载，复制/哈希回读并安全弹出。相对120件基线新增6件，仅logfile.txt改写，119件旧非日志逐字节不变，无删除；旧9份ERPT和其他既有报告保持，无新增ERPT。启动配置文件哈希、缺失项和boot2清单与上次相同，标记不认证模块执行或实际入口。

唯一匹配本次369/385/401、六次STATUS、三次BURST、Post(3072, URB387/403/419)的新增execution为ep0-12768c4364bf2773113a9c9a40dccc168a02619df246d3fca83d723b964894a5.execution.bin。216条trace、丢失0、无效0，外部capture与嵌入primary逐字节一致。boot/session身份关联ep0-life-a0c61db4316551f2f76ee6713988a751.bin：27条有效记录、闭合标志/零尾/无解析错误，writer与频率一致，末条main_return/result0。设备窗口expired、30.000453750秒，首条序号到停止29.338369115秒；设备与主机时钟未跨域校准。

另有新增execution ep0-6dcad5a130142508ea6e06a8039b9bcbab3ce9b2557add51f8a9160f15c63368.execution.bin，与ep0-life-b9647d46b46fe8aae41e31fd5aa8295a.bin关联：trace0、无本次序号/ISO、ready_tick未记录；44项启动journal无失败，27条生命周期也以main_return/result0闭合，但名义30秒窗口实际elapsed为68.687652865秒。该上下文属于哪次启动/入口、超时原因均未知，不能分配给本次三轮。

冻结部署来源只在主循环边界、同步UvcDeviceWaitReady/请求调用前后检查期限，没有抢占式终止保证，且窗口开始后也有日志调用。无单次等待/日志阻塞或调度历史，不能把额外38.7秒唯一归因于usbDsWaitReady或断定USB从未就绪。它体现名义窗口不是硬实时上限；不修改本次关联三轮30.000秒的正常到期结论。以前的quiet_enter四条未闭合前缀保持原字节，不因新增正常记录而追认其原因。

本次r1在任何新卡命令之前，被新增预检查将10月18日保留的失败owner视作活动作业而拒绝。核对旧作业封存、终态failed_no_retry及8条正常退出命令后，r2只对该确切历史owner保留只读回收例外；旧owner/旧失败作业原字节保持，仍不释放旧修复权限。r1失败原样封存；r2重新核对身份后成功。未强制卸载、重试旧修复、写卡或增加USB采集。

## 后续与封存

本次回收闭合，SD已弹出，remaining0；不追加测试。下一项只离线评估剩余轮间校验开销和持续采集约束；旧卡logo/interest、ERPT与未闭合前缀根因保持未证。未来实测需126件新基线、新范围及新授权，旧120件build只作归档验证。

| 材料（相对research/usb-ds-iso） | SHA256SUMS摘要 |
| --- | --- |
| private/runs/A-three-epoch-68e29f36-c52d-4a97-b377-5be7be3443e3 | 5f808ba87e8ce81dc7c11dbff44d51e3fe1324ab38e7490842b25a38bf636aba |
| private/analysis/A23-live120-lstat-first-host-20261025 | c553dbdb92eecf1c3d9f932d3a4421003f73fd480e265e7cc0502cba1d9249bb |
| private/analysis/A23-live120-lstat-live-authorization-20261025-r1 | 76410b042679b0fb9353b356edd36521562ba45a2049cd6f08c13d97ab37f440 |
| private/analysis/A23-live120-lstat-WAITING-observation-20261025-r1 | 8667f2ec015f2554d612eeb74817b9416394363647850dde3a4ecf3f60064838 |

build与准备材料见[候选准备](A23_LIVE120_LSTAT_READY.md)。最终实际记录、644来源、八个namespace、ticket和交接副本见private/analysis/A23-live120-lstat-first-result-closeout-20261025；旧封存保持原样。

本次回收快照private/card-cycles/20261025-live120-lstat-first-read，摘要929edc4ebd1ab6b16898990556b6f083692bf97b7e26edfb15455ef2ac955d7a；成功回收job A23-live120-lstat-first-read-20261025-r2摘要b43d376fdc81e6f31f3e5405ab8fd67bbf3f465f4785aa1fc5f582c5ff214c51；设备分析A23-live120-lstat-first-analysis-20261025-r1摘要72c441af4f1685cacf74ad02ed613fc202d5f124e3c0045d304254a37073f213；补充分析A23-live120-lstat-first-supplement-20261025摘要a1bda1118decb40f2f11d928a9e5f9d847597b3c8f2ebbdfb291bcba4f9b0672。最终回收交接private/analysis/A23-live120-lstat-first-recovered-closeout-20261025保留r1拒绝、旧owner核对、来源644、八个namespace与actual/ticket；旧主机阶段pending描述只为当时历史。

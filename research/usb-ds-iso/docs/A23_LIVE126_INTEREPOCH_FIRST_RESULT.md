# 126件候选：轮间worker三轮实测及读卡结果（2026-10-25）

本次单次最多三轮417..464已完成，主机和设备链一致：417/433/449三轮各3072正确字节，共9216，URB387/403/419；唯一新增execution含216条trace，无丢失/无效，关联27条生命周期末条main_return/result0，30.000382917秒正常到期返回。

两次完整校验位于between_epochs，worker返回/job复核/恢复poll均为2，最后verifier已回到串行队列，未停止、无重复回执或interest。接收器和外层均exit0，前台创建者直接wait，exec session18021已结束。本次范围已整段消费、remaining0，不重试、不补轮。

132件原件只读回收、哈希并安全弹出，四项部署匹配；125件旧非日志不变，仅logfile.txt改写，新增6件，无删除/新增ERPT。当前126件build只能归档验证，未来采集须132件新基线、新范围、新授权。

## 授权、唯一入口与用户观察

用户在明确417..464一次最多三轮的范围后请求“测试”，并对启动前问题回复“三项均已就绪，保持关机”。据此记录新人工回执并执行已审查r2计划一次。scope/来源/候选/旧namespace复核后，整段先消费，再启动唯一接收器。

job为12a1bc53-025a-4810-a2ed-4ac5a9490a44，receiver PID69858，run为private/runs/A-three-epoch-12a1bc53-025a-4810-a2ed-4ac5a9490a44。核对原生stdout实际WAITING之后才提示CFW emuMMC默认项开机，用户回复“已进入 CFW／HOME”；没有另行重复入口名称，不补造入口认证。

主机退出后，用户又明确回复“继续读卡，已完全关机并将卡插入 Mac”。本次回收的human_power_off_explicitly_confirmed=true源于此直接回复，不是软件观察到Switch电源状态。没有第二个接收器、失败补次、额外USB测试、SD部署或写卡。

## 主机独立验收与时间

重新调用专用消费者simulation=false，逐字节等于原采集器的entry_analysis；原生STATUS六份、ISO7/URB、全部128项transaction和完整24576字节raw均留存。ISO与control回调各[1,1,1]，abort0，interest为空前缀、无pending/overflow。三组16包分别落在槽7..22、8..23、8..23。

| 项目 | 第一轮 | 第二轮 | 第三轮 |
| --- | ---: | ---: | ---: |
| 首序号 | 417 | 433 | 449 |
| ISO提交到回调 | 47.629 ms | 47.453 ms | 47.273 ms |
| BURST到control回调 | 2.791 ms | 0.372 ms | 1.197 ms |
| BURST到saved | 53.269 ms | 51.996 ms | 52.811 ms |
| saved到下一before_intent | 287.538 ms | 288.684 ms | — |
| 两次BURST间隔 | 343.167 ms | 344.197 ms | — |

这些区间直接使用同一Mach域差值及125/3 timebase。完整校验233/234号耗时281.064/282.307 ms，phase明确为between_epochs；两次worker返回/job复核/恢复poll计数均2。最后回执的request ID2、epoch2、generation1、job和scope摘要一致；其RAW起止包住234号完整检查。验收前后guard快照完全一致，最后busy=false、verifier_on_serial_queue=true、next_epoch3、reasons空。

此前369..416的轮间saved空档为262.108/328.678 ms；本次一段较长、一段较短，不是随机化A/B，基线/来源/负载也不同，不能唯一归因队列变化或宣称提速。校验仍从saved后开始，处于下一轮关键路径；本次约288 ms空档没有被消除。

实际239次完整检查全部通过。末轮观察前235号before_tick仍278.471 ms，超过250 ms；因此仍不证明连续处理回调或排空。此次无故障/迟到回调，不能借两个成功worker计数追认真实故障交错；operator power-off退出门未在本次正常运行中触发，其证据仍限于此前模型测试。主机RAW和Mach绝对值没有跨域相减。

## SD只读回收与设备关联

核对预期外置物理SD UUID37614F76-3E12-3470-B5C8-52B5A449C213，本次为disk4s1/disk4；普通卸载后readOnly/nobrowse挂载，WritableVolume=false，复制后哈希/回读并安全弹出。16条磁盘命令全部由创建者wait、exit0，无强制卸载、命令重试或历史repair操作。旧失败owner及旧8条命令证据保持。

新增execution ep0-0e7a09b0712f180a569347e10c57b71e939b7a97c1c455519a15f7da008f9362.execution.bin唯一对应本次六次STATUS、三次BURST、序号417/433/449及三个Post(3072, URB387/403/419)。216条trace，dropped0/invalid0；外部capture与嵌入primary一致。其上下文关联ep0-life-52e56cd6571f4e71fbf4fe2f869264cd.bin：27条有效记录、闭合/零尾/无解析错误，writer/频率一致，末条main_return/result0。窗口expired、30.000382917秒，首条序号到停止29.234880885秒；没有主机/设备时钟校准。

另有新增execution ep0-8dd4575f47c50cad577c19e9c6aa86ca02926f6031d117bd913359cda0dc3f27.execution.bin，关联ep0-life-0fe917e9df8be02c36fa08ff6316949e.bin：trace0、无本次序号/ISO，ready_tick未记，44项startup无失败；自身27条生命周期也正常main_return/result0，expired、30.041145677秒。属于哪次启动/入口未知，不因时间接近或随机上下文标识将其分配给本次三轮，也不把ready_tick缺失当作USB从未就绪。

旧9份ERPT保持、无新增ERPT；旧未闭合前缀和旧未知原因不升级。启动配置文件/缺失项和boot2清单与上次相同，标记不认证模块实际执行或选中入口。132件快照中新增6件均为上述两个上下文的capture/execution/lifecycle原件。

## 当前结论与边界

本次限定三轮的主机/设备载荷、状态、URB和正常返回一致，两次worker交接成功；源束651和八个旧namespace保持，新增417 namespace17文件留证。主机与设备证据不认证全面物理来源、所有竞争窗口、SDK排空、复用、持续流或旧故障根因，广义hardware_verified保持false。

日志pending=false、SD已弹出、remaining0；本次许可耗尽，当前设备现场不再推定。下一项仅离线评估本次worker/尾部观察的证据增量和持续采集约束，不重复已通过的相同三轮。若将来有明确新问题要实测，须132件新基线及新范围/授权。

## 封存材料

| 材料（相对research/usb-ds-iso） | SHA256SUMS摘要 |
| --- | --- |
| private/analysis/A23-live126-interepoch-live-authorization-20261025-r1 | 101838b72f9c7d0c64c2f4fa69b462cc757c86e6907016a7c6ebbd70e0349b12 |
| private/runs/A-three-epoch-12a1bc53-025a-4810-a2ed-4ac5a9490a44 | 49bd8e309bb2f6c0739fd6859bba911c73b3e9ca2ed4d59168fc1efa1f262bcc |
| private/analysis/A23-live126-interepoch-first-host-20261025-r1 | 65934801d3520bce8285b3c2b532156b104dba928ae266a6889130ad7db38e8a |
| private/card-cycles/20261025-live126-interepoch-first-read | c6aa7954e0c338ff4038e6bb75dbabaa20c643dc53c2fc738a50b8dba22e12be |
| private/analysis/A23-live126-interepoch-first-supplement-20261025 | 6c1aeeed1e927a61e7acdabc7f73ca9fb257ac29222f1c39176d0433b6d87b6b |

回收命令/boot上下文见A23-live126-interepoch-first-read-20261025-r1，设备逐项分析见A23-live126-interepoch-first-analysis-20261025-r1。最终actual/ticket、九个namespace和交接见private/analysis/A23-live126-interepoch-first-recovered-closeout-20261025。旧阶段“尚未授权/日志待回收”副本仅为当时历史。

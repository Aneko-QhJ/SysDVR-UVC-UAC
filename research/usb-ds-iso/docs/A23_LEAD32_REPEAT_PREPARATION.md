# lead32 独立复现准备与ERPT比较（2026-10-17，Asia/Shanghai）

同固件、同lead32接收器、同预算的独立复现材料已核验，**没有创建新正式记录、启动接收器或读写卡**。当前仍只有[一次有效成功burst](A23_LEAD32_FIRST_LIVE.md)，重复性与稳定性尚未验证。

## 错误报告比较的新增结论

最新只读快照中共有8份ERPT：7份在前次快照已经存在且字节保持，只有1份新增。全部为870字节、28字段、相同字段名集合、字面错误码 `2162-0004`，均缺少ProgramId及boot/session关联。新增错误码并非本次首次出现；这不证明新增报告无害，也不确认其与SysDVR有关。8份完整解析及原件哈希全部保留。

核对了Atmosphère官方实现，固定参考提交 `6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8`，原始源码及来源哈希随审查封存。该参考实现会为缺省字段补入AbortFlag=false、HasSyslogFlag=true；两个标志位本身不能证明进程未异常或已有可回收syslog。其保存syslog辅助函数没有向srepo:u转发报告ID。本次没有核验卡上ERPT二进制对应此提交，因此这里只用于限定字段解释，不认证部署行为。[官方Reporter实现](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libstratosphere/source/erpt/srv/erpt_srv_reporter.cpp)

参考实现的报告时间来自Switch用户/网络时钟，OccurrenceTick采自系统tick。新增报告时间字段转换为北京时间为13:12:07；主机run目录标记13:12:30，两端时钟偏移没有测量，不能以此判定报告发生在受控测试之前。若借用EXE3的19.2MHz频率，8份报告tick约为7.847..8.014秒，新增报告tick也早于所选EXE3窗口tick；但ERPT没有boot/session关联，不能将它们放进同一次启动时间轴或据此排除采集关系。[官方时间字段来源](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libstratosphere/source/erpt/srv/erpt_srv_reporter.cpp#L564)

本轮没有确认错误码的具体产生者或语义。后续通过新旧原件差异继续收窄来源，不为定位ERPT而更换固件、清理旧文件或放宽ISO验收。

## 可执行的复现方案

1. 继续使用当前path-span设备包和lead32接收器，不改固件、参数、USB配置或保存路径。已核验原部署回执和最新13:15只读回收/弹出回执；无需重写卡。
2. 现场确认SD已装回、USB已连接且Switch完全关机，明确开始此次新测试后，才创建全新记录。先主机WAITING，再提示启动CFW，不等SysDVR初始化完成。等待超时也消费该记录，不自动另开窗口。
3. 一次ISO提交、一次触发。要求16包、每包192字节、序号从1开始且逐字节匹配、有效槽连续；不要求重复落在旧索引4..19或相同帧号。要求自己的URB/ISO7完整、3072字节、terminal1/bitmapFFFF；退出0本身不足以验收。
4. 结束后留40秒保存，完全关机后只读回收全部原件并弹出。以本轮45原件完整哈希清单比较新增/变化，不删除旧文件；逐个比较EXE3及LCP1上下文，保留歧义。新增ERPT独立登记，不自动归因于SysDVR。
5. 成功则增加一个独立复现样本；失败、部分完成或未决则原样保留，不补次、不复用旧记录。即使再次成功，也不宣称长时稳定或完整UVC/UAC已通过。

## 已核验的准备材料

`private/analysis/A23-lead32-repeat-preparation-20261017`：29条，manifest摘要 `27e7cc6dc6cd716b1fc5a7ee6e3a6ca66c5e3826f3f6e1759abb03f12854f6e3`。包含8份ERPT解析、固定官方源码、字段比较、条件时间比较、复现方案、45原件基线、预览及离线dry-run。暂存分析首次写基线时误将原始字节当作JSON摘要，未写入该文件或执行硬件操作；修正为逐件SHA256后继续，原脚本和中断原因一并封存。

预览目标：`private/analysis/A23-lead32-once-20261017-repeat1.json`，当前不存在。新次数0、acquisition_enabled=false。251项既有来源和两条lead32现场记录均保持，前次成功记录仍recovered=true；本轮没有重跑既有80项回归，因为未改变源代码。

续接读取 `private/analysis/A23-lead32-pending.json`，保持stage=single_burst_recovered，准备材料另附引用。现场条件未确认，尚未签发或开始下一次测试。

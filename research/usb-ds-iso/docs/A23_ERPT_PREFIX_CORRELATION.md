# 新增ERPT与未闭合生命周期的离线关联（2026-10-25）

新增ERPT可解释为“检测到强制关机”，但现有材料不能确定是哪次启动、何种触发或哪个模块。四条quiet_enter前缀也不能定位崩溃位置。本次321..368三轮216条trace与27条正常返回生命周期的关联保持成立。

## ERPT含义与旧报告对照

当前120件快照含9份ERPT，8份在112件基线中已存在，新增1份。9份全部完整解码、错误码均2162-0004，AbortFlag=false、HasSyslogFlag=true，没有ProgramId/ProcessId。官方错误定义的模块号为162、ForcedShutdownDetected描述号为4；SystemProgramAbort描述号为2，是不同结果。旧8份同码只说明该类记录以前出现过，不能据此断言新记录无害或确定同一原因。

新增文件96833172-806f-cb4e-552d-b67d9124c6c0的内部ReportIdentifier为72318396-6f80-4ecb-552d-c0c624917db6。两种字符串受旧文件命名字段与Uuid::ToString字节序差异影响；9份都按同一转换匹配。最初直接比较两种字符串的分析r1因此拒绝，失败封存，未把它误判为卡上数据损坏。

## 时间与默认字段的边界

官方Reporter在组装报告时采样OccurrenceTick和时间戳；它们不是被打断程序最后执行时刻的记录。新增OccurrenceTick为146491530，若按19.2 MHz换算约7.630秒，仅是名义计数换算。ElapsedTimeSincePowerOn/LastAwake为相对于Reporter参考tick的整秒值；0不能解释成设备物理上电0秒。ERPT缺少本实验boot/session身份，不能把这个tick与不同启动的29–60秒生命周期计数直接相减或排序。

官方源码还会在调用者缺字段时补AbortFlag=false和HasSyslogFlag=true。报告中这两个布尔值不足以证明没有过abort，也不足以证明已存在或已收集对应syslog。没有进程身份、调用栈或本实验序号，不能把本报告关联为某个sysmodule的崩溃报告。

本次公开源码固定于提交6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8，封存7份原件及哈希；尚未采集并认证SD上实际Atmosphere二进制版本与这些源码一致。因此错误符号及字段实现是官方源码依据，不能冒充已验证部署实现。

## quiet_enter前缀实际覆盖到哪里

封存的实际部署来源显示：prepared → usb_init_call → usb_init_result(0) → quiet_enter。quiet_enter位于CoreSetDiagnosticQuiet(true)、工作线程启动和启动journal封口之前，所以四条前缀只确认USB初始化返回0与该记录内容，不能证明线程已启动或启动44项journal已完成。

生命周期capsule进入deferred后，运行窗口内刻意不写普通note；允许的下一条是main_loop_left。后续写入失败还会disable该观察器；各note返回值通常被主流程忽略。因此四条有效记录加零尾，无法区分仍在运行、进程/系统中断、关机掉电或后续文件IO失败，也不证明程序在quiet_enter当场崩溃。每条记录自身最终commit仍保留格式原有的不认证边界。

main_nonce来自randomGet；execution中名为boot_id/session_id的字段也是VideoStreamThread每次随机生成。它们用于本实验记录之间的关联，并非系统全局启动号。writer344来自线程ID；三份新生命周期重复这个值不能证明同一次启动。该未闭合前缀没有joined_context，不具备与ERPT或两份execution建立身份连接所需的字段。

## 另外37条上下文

额外execution含37条有效trace，无丢失/无效；两个相同SET_INTERFACE setup(010b000001000000)各在接口0/1/2分发，形成6个记录组。这里的分发记录数不能当成6次独立总线请求。两条URB回执均是channel2控制端点(704/1168)，ISO channel8为空；无本次321/337/353序号。44项启动journal无失败结果，窗口30.002840156秒到期，与其自身27条main_return/result0生命周期对应。发送者和启动入口仍未知，不能分配给No HOC或默认项。

## 当前结论与后续

本轮只分析本地已回收副本和官方公开源码，USB/SD访问、实测、编译与新许可消费均0。640来源、实际321记录、旧actual273和七个namespace均复核保持，SD最后已弹出、remaining0；不改卡、不重试。本次三轮成功与额外前缀未知分别保留，旧卡logo及interest根因未证。

现有材料的身份关联已到边界，继续按文件名字典序、重复线程号或跨启动tick排序不会增加可靠结论。后续转向持续采集约束和轮间完整校验开销的离线研究；不为复核已通过的相同三轮自动增加实测。未来实测仍需120件新基线、新范围及新授权。

分析r1的UUID字符串假设和r2误把candidate子树当成独立封存根的失败分别原样保留；最终r3验证包含candidate的父级封存。原r3分析输出一度把控制URB列表字段标为iso_urbs，completion.py在最终封存前改为urb_reports，并独立过滤channel8为空；未修改原执行脚本或设备原件。

## 可复核来源

- [官方错误定义](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libvapours/include/vapours/results/err_results.hpp)
- [官方Reporter字段采样和默认值](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libstratosphere/source/erpt/srv/erpt_srv_reporter.cpp)
- [官方文件命名](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libstratosphere/source/erpt/srv/erpt_srv_report.cpp)与[Uuid字符串实现](https://github.com/Atmosphere-NX/Atmosphere/blob/6b0c077b4c608a3a2ee712b8dc35fee87ceb62e8/libraries/libvapours/include/vapours/util/util_uuid.hpp)
- 本地封存：private/analysis/A23-erpt-prefix-correlation-20261025-r3，含脱敏9件索引、生命周期索引、部署来源副本、固定上游源码、完整来源及namespace哈希与ticket；旧失败目录不覆盖。
- [本次三轮与只读回收结果](A23_LIVE112_SHORT128_FIRST_RESULT.md)

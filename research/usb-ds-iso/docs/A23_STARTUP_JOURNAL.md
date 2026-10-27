# A23 独立启动阶段记录原型（2026-10-14）

新增固定64条、只追加的**EP0INI1启动日志**，区分API调用、原始Result、void返回和fatal
Result。一个调用方指定writer发布不可变记录区间，读取方以acquire只查看已提交记录，
不读取owner/URB/payload。日志与EP0DIA1/EP0OWN1独立，不能放行正常导出或授权清理。

40项既有启动场景结果逐项保持，新增15项策略检查通过ASan/UBSan，并用ThreadSanitizer
复跑15项策略；两个真实电脑pthread并发发布/读取32份日志、2048条记录，TSan无报告。
14项新增、370项相关Python回归无跳过。AArch64只编译独立核心.o，**未接完整ARM main、
初始化/线程实际API hooks或设备文件路径**；本轮仍USB/SD0、remaining0，根因未知。

## 已发布记录区间

[核心头文件](../device/ep0_startup_journal.h)提供init、record、seal和snapshot。调用方需
提供零初始化存储，保留单writer约定并禁止直接修改已发布槽；writer ID是调用方参数，
不查询线程身份、不认证调用方。native使用11；recipe绑定新原型输入与旧审查manifest。

| 操作 | 行为 |
| --- | --- |
| init | CAS取得INITIALIZING，写入固定writer/recipe和空writer栈，再release发布READY；重复init拒绝 |
| record | 核验writer/阶段/事件，CAS取得BUSY，写下一槽后release一次发布新count；不改旧槽 |
| 不匹配return或无效调用 | sticky INVALID，拒绝新记录，保留已提交区间；不读取未提交槽 |
| 第65条 | sticky OVERFLOW，前64条不动；仅保留丢失标记，不提供准确丢失次数 |
| fatal Result | 提交非零原始Result并终止后续追加；可再seal，无资源操作 |
| seal | 只在writer未BUSY时CAS置位；seal后任何append/init/重复seal拒绝，不改变日志 |
| snapshot | acquire一次取count/标记，复制前count条；写入中可返回旧区间并标BUSY，不等待writer |

writer私有调用栈核验嵌套CALL与同阶段RESULT/VOID_RETURN配对；读取方不读这个栈。
记录字段范围错误、错误writer或重入写入永久拒绝；若拒绝发生于另一个写入期间，提交时
保留sticky INVALID位。seal与失败追加并发时，错误标记不会改写已经sealed的状态。

配置只在READY前写一次；各槽只在首次发布前写一次，所以读到count后不需要第二次读
count或复制可变总体状态。下一槽的写入不涉及读取方的旧槽。配置初始化保护、BUSY、
计数与错误标记都在一个32bit atomic token中，发布/读取使用release/acquire。
seal只表示该**记录日志**不再修改，不表示线程已join或设备URB终结。

短buffer和输出与journal重叠在写任何输出字节前拒绝；snapshot无分配、时钟、文件或
USB查询。没有等待reader确认或自动恢复；TSan验证的是当前电脑并发模型，ARM的原子
实现/CPU成本与实际fatal上下文尚未验证。

## 阶段与结果语义

[构建/回放工具](../tools/build_a23_startup_journal.py)复用封存
[启动失败审查](A23_STARTUP_FAILURES.md)的实际函数副本，将记录wrapper接在**native服务
adapter边界**。原提取函数主体不改，40个场景的Result/资源/回调计数与旧audit逐项相同。
描述符、接口、ISO setup内部仍为旧模型；这些粗粒度阶段不能当作逐接口真实API观测。

阶段包括FS初始化/挂载、原日志delete/create、video/audio capture open、USB init/setup/
enable、video/audio threadCreate/threadStart、sm/setsys/firmware/serial、Core/UVC顶层初始化，
以及FS/mount/capture close调用。Result返回失败仍正常记录，记录拒绝不更改原API结果。

- `result`保留API原始32bit值；可以分别看到threadCreate成功、threadStart失败82。
- `void_return`没有Result；它只表示函数返回，不能造一个“成功Result0”或证明资源已释放。
- `fatal_result`保留fatalThrow的非零Result；nativefatal仍用longjmp，不执行真实fatal。
- 历史成功API表示当时返回0，不表示资源当前仍持有或已经退出。关闭、重试与部分失败按
  时间顺序保留；不会用一个成功bit掩盖之后的失败。

例如audio-start-error保留video create/start成功，audio create成功、start失败82，以及
fatal82；不会把video start成功解释成已join。core-audio-error保留FS/mount/video open成功、
audio/顶层Core返回72，而且没有fsExit事件。假设手工retry-partial保留两次FS初始化；
这是注入的假设重试，当前实际main并无自动重试。40项中最长46条，未发生丢失/INVALID。

## 独立格式与解码

EP0INI1是96byte头+最多64条×16byte条目，最大1120byte，所有整数little-endian。
头含simulation/startup-only、sealed/overflow/invalid/busy、count、调用方writer、32byte
recipe和两组CRC。条目含step/event、原始Result或空值、1起ordinal和reserved0。
没有boot/session nonce、EP0 owner/writer交接、join或payload字段，也没有清理授权。

[独立decoder](../tools/analyze_ep0_startup.py)检查布局/长度/CRC/reserved、阶段与事件配对、
fatal后无记录、void与Result类型、容量/标记和可选recipe匹配。修改记录并重算CRC仍不能
绕过这些语义检查。旧DIA1与正常capture decoder拒绝INI1 magic；不重标旧诊断。

`complete_journal`只表示sealed、无错误/丢失、没有尚未返回的CALL；它不表示整台设备
启动成功。live BUSY快照可以包含未结束CALL，单次发布的一致记录仍可解码；不会等待
writer恢复。CRC、writer和recipe不认证来源或线程状态，也不能关联到某次实机启动。

## 验证与封存

[14项Python检查](../tests/test_a23_startup_journal.py)覆盖40场景保持、partial失败、thread
created/started、重试历史、void结果、64条上限、busy未提交槽、wrong writer/invalid/
不匹配return/fatal终止/seal、电脑并发、格式与语义破坏、旧decoder拒绝及离线范围。

[15项C策略](../tests/ep0_startup_journal_test.c)包括短输出/别名不改、未初始化/重复init拒绝、
最大1120byte、仅复制提交区间、错误writer、不配对return、sealed不可变和fatal后拒绝。
并发用两个实际pthread；握手确保至少一次live读取，再观察32份日志各64条。ASan/UBSan
与TSan各执行一次；总40+15+15=70次native检查/回放，55项不同场景。并发读次数依调度
变化，不作为成功阈值之外的性能数据；未执行任何Switch线程。

- `private/analysis/A23-startup-journal-review-20261014`：40份INI1/独立JSON、生成native源码/
  binary、两组策略与pthread结果、ARM.o、recipe/audit/manifest。没有新完整ARM ELF。
- `private/analysis/A23-startup-journal-validation-20261014`：370项相关回归、源码/生产快照、
  旧封存/三票据/文档链接核验、独立validation/manifest。

```sh
python3 research/usb-ds-iso/tools/build_a23_startup_journal.py --output /private/tmp/A23-startup-journal-new
```

必须使用新目录。电脑native输出和策略文件不等于设备落盘；旧候选/格式和生产不修改。

## 下一步

在新的完整ARM候选副本接入实际初始化/启动API边界，先明确BSS初始化、实际单writer身份
取得和recipe时序，再核对返回/fatal前的原始Result保存、phase预算与成本。记录失败不得
改动原服务返回值、自动重试、回滚、join/close或既有cleanup gate；异常回调只能读取已
发布区间。还需审查实际helper内部阶段，native粗粒度setup wrapper不能替代它们。

之后另设计与EP0DIA1/启动日志关联的版本化扩展，记录admission原因和文件保存结果。
当前INI1没有启动nonce或会话关联，既有DIA1没有admission/文件错误字段；不能靠recipe
关联就宣称同一次启动。初始化失败前可能没有可用FS，不能由日志历史的FS成功推断现在
可以写卡；设备保存路径和资源保持条件需要另验证，旧sink继续只用于已join的诊断。

没有新初始化回滚、设备入口、测试次数或部署；实际fatal/回调、Switch并发/成本、DMA和
FS持久性未知，根因未确认，不把这些新原型路径当作首次SDK burst seq0的原因。

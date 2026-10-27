# A23 启动日志 ARM 隔离候选（2026-10-14）

新完整ARM候选在实际Core/Capture/UVC初始化、__appInit和线程创建/启动调用处接入EP0INI1。
**__appInit开始时只查询一次启动线程ID；失败或ID0禁用记录，继续原启动流程。** 原始API
返回值和fatal Result在对应返回/fatal前保存，fatal前或两线程启动成功后封存启动日志。

44项实际函数副本回放与7项runtime策略检查通过ASan/UBSan，15项新增、385项相关Python
回归无跳过；两窗口配置各完整链接11对象libnx ELF，只链接。原40项服务结果/资源计数
逐项保持。生产/旧候选/格式/封存/三票据不变，本轮USB/SD0、remaining0，根因未知。

## 接入位置与身份

[构建工具](../tools/build_a23_startup_candidate.py)复制最新完整
[诊断sink候选](A23_DIAGNOSTIC_SINK.md)，使用封存
[启动日志核心](A23_STARTUP_JOURNAL.md)，只改生成副本：core.c、capture.c、UVC初始化函数
和main的appInit/启动部分，新增[startup runtime](../device/ep0_startup_runtime.c)及
[API](../device/ep0_startup_runtime.h)。原core.h/API签名、生产与旧目录不改。

runtime采用C静态零初始化存储；__appInit在原20秒等待、smInitialize和CoreInit之前调用Begin。
CAS取得唯一初始化尝试，再`svcGetThreadId(..., CUR_THREAD_HANDLE)`；成功且非零才发布日志
READY和runtime enabled。失败/零ID发布disabled，不重试、不fatal、不改变原服务返回值。
在身份查询中断的native场景中，status仍initializing，没有伪造ready、writer或日志文件。

这是新增一次本地kernel调用，不是USB查询；未测真实加载器/BSS/libnx时序、权限/错误概率
或启动延迟。固定writer来自该次API观察，不逐条查询身份。代码约定启动点都由同一线程
调用，回调只沿旧gate执行、不写日志；不认证调用方或实机线程状态。调用在其他线程上的
行为仍不属于已验证合同。

| 实际源码范围 | 接入记录 |
| --- | --- |
| _initFileLogging | FS挂载、原log delete/create的原始Result，保留原忽略错误行为 |
| _getSerialNumber/CoreInit | setsys/serial、FS初始化、Core入口及每个返回 |
| CaptureInitialize | video/audio grcdServiceOpen原始Result，原失败仍立即return |
| UvcDeviceInitialize | 顶层入口/返回、usbDsInitialize、descriptor/interface/ISO helper返回与enable |
| __appInit | sm/setsys/firmware查询；原fatal前记录并seal |
| LaunchThread | 原threadCreate/threadStart前后，失败R_THROW之前记录fatal并seal |
| 原启动清理函数 | FS/mount/capture close的void事件；main已seal时不再追加 |

UVC的descriptor/interface/ISO阶段现在围绕真实helper调用，而非ARM中使用stub；但日志仍
是**粗粒度helper返回**，没有逐项记录所有register/append IPC。native回放中的这些helper
依旧是已标注的服务模型，未运行HOS或libnx实际机器码。内部usbDsExit仍执行原cleanup，
未新增一个虚构的释放成功Result或用日志授权清理。

原运行期LogFunctionImpl完全保持，不在视频/音频线程的日志FS调用插桩；实际VideoStream/
AudioStream/__appExit正文、EP0 handler、所有旧账本/guard/admission/文件sink保持原样。
原logfile初始化delete/create仍存在，日志原型不改变它们或测量LOG成本。

## threadCreate与threadStart

main在两个原LaunchThread调用之前绑定两个Thread对象地址。Core通过地址相等映射video/
audio的create/start阶段，不读取Thread内部或假设某个结构布局。绑定拒绝NULL/相同地址/
重绑定覆盖；未知地址无法取得有效阶段，记录拒绝但不改变原thread API调用。

- video-start-error保留create成功、start失败82、fatal82，再seal。
- audio-create/start-error保留之前video create/start成功；不把成功返回解释为已join。
- LaunchThread错误仍调用原R_THROW/fatalThrow，没有新增停止、join、close、返回错误值
  给main或初始化回滚。__appInit的两个fatal点也保持原fatal调用顺序。
- 两次LaunchThread均返回后，main在“running”日志及sleep循环之前seal；UVC初始化失败
  return1前也seal。callback不写启动日志，正常回调清理不会改变已封存内容。

启动日志seal只冻结此CPU日志，不证明video已退出、URB终结或资源可释放。音频失败时
视频可能已运行；是否到达callback、其真实PC/processing/pending仍未知。

## 回放、容量与成本边界

[15项Python检查](../tests/test_a23_startup_candidate.py)覆盖真实API插桩、原40场景保持、
identity一次/失败/零ID/中断/重复Begin、fatal/线程角色、partial保留、seal位置、原正文和
runtime logger保持、容量与完整ARM链接及封存边界。

- 40项旧场景的所有Result/资源/回调计数逐项相同，唯一新增的kernel查询单独计数1。
- 4项额外native：身份失败97、身份0、查询中断和重复Begin。失败/0时原appInit仍完成
  Core；查询中断场景没有运行后续服务。中断由longjmp注入，不是实机事件证据。
- [7项runtime策略](../tests/ep0_startup_runtime_test.c)：未尝试、三种身份边界、正常seal、
  fatal、容量溢出。已seal后再次调用/Begin不能改变原字节，不读owner/payload。
- 实际hook回放最长44/64条，只有显式策略溢出标OVERFLOW；40场景无INVALID/丢失。
  比前native adapter最多46条少，是因为grcdServiceOpen内部失败时的自动close未单独
  插桩；不等于少调用原close或实际资源被解除。
- ARM符号确认journal结构存储696byte，固定64条；这是该对象大小，不是整个固件BSS/
  内存峰值增量。指针/状态等额外globals、对齐、代码/stack及实际trace时间成本仍需评估。
- 默认时间窗口关闭与30秒样例各链接11对象完整ELF，实际startup/kernel/FS/USB调用存在，
  未执行、打包NSO/NSP或部署。

当前main仅记录内存，**没有启动日志设备保存/导出路径**。Snapshot/状态访问器用于native
及object验证，未被main调用的函数可以在最终ELF优化链接时剔除；journal和已接入记录函数
仍在ELF中。旧DIA1 sink只保存其既有已join诊断，不增加INI1或字段关联。

## 证据与继续入口

- `private/analysis/A23-startup-candidate-review-20261014`：两配置完整源码/11对象/ELF/map/
  recipe，44项插桩回放/INI1/独立JSON、7项runtime及audit/SHA256SUMS。
- `private/analysis/A23-startup-candidate-validation-20261014`：385项回归、源码/生产快照、
  旧封存/三票据/文档链接核验、独立validation/manifest。

```sh
python3 research/usb-ds-iso/tools/build_a23_startup_candidate.py --output /private/tmp/A23-startup-candidate-new
```

输出必须新目录。recipe绑定旧ARM与journal manifests、新runtime/hooks/输入、libnx与编译器；
两个配置recipe独立。原EP0DIA1/INI1/capture布局不变，CRC/recipe不认证来源。INI1仍无启动
nonce/boot/session关联，不能据recipe宣称与某份DIA1属于同次启动。

下一步优先设计启动记录与EP0/admission/文件保存结果的版本化关联和初始化失败旁路。
先明确无owner、FS未取得或可能live线程时的独立语义；不要读取未join的owner/payload，
不由历史FS成功推断当前可写卡，不重标旧诊断。再审实际helper细阶段与容量/代码/BSS/
stack及时间预算，新增记录必须重新评估64条边界。旧logger与cleanup问题仍按原审查保留。

没有新回滚、自动重试、设备测试入口或次数；Switch并发、fatal/回调、DMA、FS持久性和
真实成本未验证。remaining0，根因未知，不把插桩的注入失败当作首次SDK burst seq0原因。

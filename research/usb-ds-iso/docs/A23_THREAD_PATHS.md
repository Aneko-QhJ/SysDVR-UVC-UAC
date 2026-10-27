# 线程等待调用点与采集重试审查（2026-10-14）

完整线程图里有两种等待：eventWait只等待1个Event；UvcDeviceProcessRequests的后续SETUP轮询同时等待VC、VS、ISO三个Event。新的只读审查按实际调用点接入句柄回放，保留所有其他未知边。采集函数的递归并非已经观察到无限重试：顺序执行下，持久的初始化标志使Transfer最多两次。另在电脑并发调用实际采集函数时复现锁外标志读取的数据竞争，但当前A23没有启用UAC，不能把这个潜在问题当作首次burst根因。

16项新Python检查与459项相关回归通过，无跳过。实际采集源码与仅供测试的锁内读取对照各16项顺序检查通过ASan/UBSan；两个并发顺序各产生预期TSan报告，对照两次无报告，共36次native检查。两封存ELF各追加32组混合三事件指令回放。生产、候选runtime和历史封存不改，本轮无新ARM构建/执行、打包、USB或SD访问，remaining=0，根因未知。

## 三事件等待不能套单事件数字

最终ELF只有两处直接调用waitObjects。eventWait调用前将w2置为1；UvcDeviceProcessRequests调用前将w2置为3，并从三份SetupEvent.autoclear读取三个Waiter.type。合法Event的bool字段只生成Handle或HandleWithClear，类型0/1；这仍要求初始化、对象寿命、字段和SVC成功索引有效，未验证损坏对象或通用Waitable回调。

| 调用点 | 对象数 | waitObjects自身SP | 含等待SVC的回放峰值 |
| --- | --- | --- | --- |
| eventWait | 1 | 224+16+48=288byte | 304byte；加eventWait自身48则352byte |
| UvcDeviceProcessRequests中的waitMulti | 3 | 224+16+144=384byte | 400byte；另加实际caller持有栈 |

新增回放遍历三个type的8种组合，每种注入成功、timeout、同步取消重试、clear错误重试四种序列，各配置32组。SP均恢复、没有到达间接callback；取消是SDK同步等待取消，不能等同USB URB取消或IOUSBHost abort。timeout保留0xEA01，其他这些具体序列返回0。有限回放不是全输入证明，也没有停止时限。

调用点证书绑定两处caller及三个SDK函数的机器码摘要，并与已封存ELF/反汇编逐字核验。只在两条waitObjects边上替换具体句柄profile；不全局删除动态SP或间接边。参数、SDK指令、调用边或峰值变化会拒绝。证书和摘要用于一致性，不认证来源。

## 递归重试与并发前提

CaptureReadVideoFrame和CaptureReadAudioFrame的真实源码在首次GRCD_NOT_INITIALIZED且_ensureGrcdInit成功后递归一次。helper在调用grcdServiceBegin之前置g_grcdBeginCalled=true，之后没有reset；Begin失败也不清零。在单worker、有效生命周期和没有外部改写的条件下，第二次Transfer即使再次返回未初始化也不能再次Begin/递归。当前机器码为真实bl递归而非尾跳，视频自身96byte、音频80byte，第二层仍占栈；原保守调用图继续报告递归循环，不将上述条件擅自写成无条件上界。

实际函数电脑回放覆盖视频/音频的直接成功、Transfer错误、小尺寸、Begin成功/失败、第二次仍未初始化/Transfer错误及跨流顺序调用，每份源码16项。成功/错误和Transfer计数逐项核对，最大Transfer2、Begin1；没有观察到无限递归。每个样例从新进程的静态初值开始，不代表重新初始化Capture会重置该标志。日志在采集夹具中为no-op，服务返回和pthread Mutex由电脑模型提供。

helper先在锁外读取普通bool，随后才加锁重读，写入则在锁内。在两个电脑pthread同时调用视频和音频采集的两个顺序中，TSan分别报告锁外read1与锁内write1冲突，位置是g_grcdBeginCalled。排程仅由服务stub里的relaxed原子控制；控制变量按64byte隔开，避免TSan影子单元覆盖测试中的标志访问。测试对照仅移除锁外快速读取，所有标志读取都在原mutex内，两个并发场景无报告、16项顺序观察保持。原场景将Begin暂停至第二worker完成锁外路径；锁内对照在第二Transfer返回后恢复Begin，以免测试stub自身制造死锁。修改只存在于新生成的电脑对照源码，未进入候选ARM或生产文件。

当前A23 UvcDeviceInitialize先清零g_uacCtx，只引用而不调用_setupAudioInterfaces5x；唯一将initialized置true的该helper也未出现在两封存ELF中。UacDeviceIsStreaming依赖initialized与streaming，因此正常当前生命周期不会进入音频采集。电脑双worker测试揭示的是启用音频/外部并发调用时的风险，不证明当前实机发生竞争，更不解释burst时seq0。图审查保留音频路径，未凭源级生命周期假设剪枝；故障、内存损坏、外部入口和其他共享状态仍未核验。

## 剩余栈缺口及其含义

按调用点接入回放后，视频与音频根不再列waitObjects动态SP/间接路径为未知，但仍不能给出线程上界。两个配置的视频已知profile路径为3600/3616byte，音频3120byte，main4592byte，最长已知链经过原logger的vsnprintf及分配器锁；这些是已遍历路径数字，不是实际峰值或完整上界，不用于判断线程栈是否足够。原严格图的session_capture352byte和独立保存768byte保持。

- _svfprintf_r仍有blr x23与br x1；未假定格式串、间接目标、logger重入或FS并发安全。
- __syscall_getreent的TLS标记不匹配分支调用diagAbortWithResult；后者包含svcBreak和udf #0。原分析器将不返回路径的函数尾部列为未知，不代表观察到异常。
- armDCacheFlush后紧接armDCacheFlush_L0局部标签，SP为0的循环和ret位于第二标签块。原分析器按所有反汇编标签分割函数，因而在第一块末端报falls outside；这是分析边界，不能据此认定cache flush错误。
- fatalThrow、LaunchThread等不返回出口、randomGet失败路径及内核/异常栈仍未闭合。不能仅删除末端未知或假设abort不占栈来宣布线程安全。

下一步在新的独立分析器中核对ELF符号类型/大小，合并有证据支持的汇编局部块，明确svc/udf与不返回边界；再审具体日志格式与合法线程TLS的间接调用前提。若后续启用音频，先在新的隔离候选里处理初始化标志并发门槛及有限重试，保留当前生产与封存。失败FS/启动细阶段预算/部分线程回滚仍是独立未完成项。任何电脑结论都不恢复实机次数。

## 可复核材料

- [只读审查工具](../tools/audit_a23_thread_paths.py)、[实际采集函数夹具](../tests/a23_capture_retry_fixture.c)、[新检查](../tests/test_a23_thread_paths.py)。
- [审查结果](../private/analysis/A23-thread-paths-review-20261014/audit.json)、[封存摘要](../private/analysis/A23-thread-paths-review-20261014/SHA256SUMS)。
- [验证结果](../private/analysis/A23-thread-paths-validation-20261014/validation.json)、[相关回归](../private/analysis/A23-thread-paths-validation-20261014/regression.txt)、[验证摘要](../private/analysis/A23-thread-paths-validation-20261014/SHA256SUMS)。
- [此前等待/定长路径审查](A23_WAIT_FIXED_PATH.md)与[研究交接](PROGRESS_HANDOFF.md)。

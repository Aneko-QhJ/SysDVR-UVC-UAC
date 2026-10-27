# 默认locale字面扫描与格式化初始化审查（2026-10-15）

本轮续接[转换入口到取参路径](A23_PARSER_BRIDGE.md)，从既有完整ELF的`_vsnprintf_r`
入口开始回放，接通FILE构造、va_list副本、`_svfprintf_r`初始化、TLS/reent获取、
默认locale选择和UTF-8字面扫描，再进入首个转换。两配置共876组回放与4组拒绝
对照通过。首个转换的percent位置、顺序索引、缓存计数及FILE状态不再注入。
转换渲染、后续循环及整线程栈仍未闭合，USB失败根因未知。

## 实际连接的路径

新审查重新绑定两配置79/80个直接日志调用点及只读字节，仍覆盖73种格式。其中
50种有转换，23种是纯文本。每格式各回放容量0/1/512与寄存器/栈两种ABI，共
每配置438组：300组到首个取参结束，138组纯文本到`_vsnprintf_r`返回。

实际wrapper用256字节帧；FILE地址为wrapper SP+72，flags=0x208，remaining为
max(capacity-1,0)。原va_list的32字节通过实际两次q寄存器读取/写入复制到SP+32。
formatter接收该副本，使用1264字节帧，实际指令将顺序索引和缓存计数初始化为0。
首次取参只推进副本，原va_list的gr_offs保持，缓存计数及下一索引推进到1。
没有在formatter、扫描或取参入口重新装入这些状态。

`__getreent`实际读GOT，尾调用`__syscall_getreent`；后者读取TPIDRRO_EL0指向的
TLS，核对+480处标记0x21545624，再取+496的reent指针。`_localeconv_r`及
`__locale_mb_cur_max`也执行其实际调用/选择指令。模型提供有效TLS地址、标记和
reent对象，线程locale字段为NULL；实际代码才从当前ELF的GOT取`__global_locale`。
这些是显式运行态前提，没有验证Switch实际TLS或locale生命周期。

字面扫描使用默认`__utf8_mbtowc`的实际ARM指令，覆盖当前格式扫描出现的64种
不同ASCII字节（包括NUL和percent），没有覆盖完整UTF-8语言或全部输入状态。
每次调用时mbstate计数为0；回调写formatter SP+344处的mbstate与SP+316处的
wide-character输出，均与wrapper内FILE字段分离。真实扫描找到首个percent，
随后保留全部机器状态接入上一轮已更正的真实hex、整数或窄字符串取参路径。

## 纯文本、容量与错误前沿

23种纯文本格式继续执行`__ssprint_r`及非增长`__ssputs_r`的实际指令，核对返回
完整应输出长度、实际截断长度、最后NUL和SP恢复。容量0不写输出；容量1仅写NUL；
容量512保留全文。flags始终0x208，callback观察到的写入不覆盖FILE字段。

strlen、memset和memcpy采用有界内存模型；调用后把x0之外的caller-saved通用
寄存器标记未知，防止错误依赖模型保留的scratch值。没有执行这些SDK函数本身，
也没有执行分配、get_arg或诊断退出。FILE增长路径在分配前沿停止。

每配置两个拒绝对照：TLS标记错误到`diagAbortWithResult`调用前沿停止；非NULL
替代locale对象具有未知callback时，在间接调用前沿停止，不强行按默认UTF-8解释。
新增测试还核对未映射locale、丢失TLS字节、错误FILE增长flags、指令预算与
实际UTF-8机器码篡改。它们是电脑模型中的敏感性检查，不是Switch异常实测。

## 栈与结论边界

已回放的wrapper到首个取参前缀，观测持有用户SP最多1536字节；纯文本返回路径
最多1664字节。这包含实际执行的locale/callback/追加函数帧，但不包含有界模型
替代的strlen/memset/memcpy内部栈、caller、内核或异常栈。不能作为完整格式化
链或线程栈上界，不能据此放行清理或新测试。

输入的TLS/reent、va_list ABI与值、缓冲区和容量仍由模型提供。ELF地址按零load
bias解释，假定有效映射和初始全局locale未改变；实机重定位与运行态对象未验证。
有转换的50种格式仅执行到首个取参，尚未输出转换值、解引用窄字符串或回到
后续字面扫描，所以原97转换的跨转换索引/缓存连续性仍未证明。
不剪枝全图，不排除全局get_arg、错误/重入/TLS/locale变化或未知FILE别名。
GetSize失败后继续offset0写入的问题未修复。

生产源码、旧runtime、旧工具/证据及三票据保持。无新ARM构建/执行、固件打包、
USB或SD访问。SDK burst票据仍failed_no_retry、remaining=0、acquisition_enabled=false。

## 验证与续接

新增14项检查与解析器/缓存/FILE/formatter/ELF边界/日志契约的相关回归见记录。
126项相关测试全部通过，无跳过，新增14项包含在其中；较早的571项回归记录保持。
7315个既有及新增审查证据文件的哈希、当前生产源码及三个票据已独立核验保持。
审查工具使用python3.12，`--output`必须是新目录。只有电脑研究，没有硬件入口。

- [审查结果](../private/analysis/A23-literal-scan-review-20261015-final/audit.json)
- [dormant回放](../private/analysis/A23-literal-scan-review-20261015-final/dormant/profiles.json)
- [30秒回放](../private/analysis/A23-literal-scan-review-20261015-final/window-30s/profiles.json)
- [审查封存](../private/analysis/A23-literal-scan-review-20261015-final/SHA256SUMS)
- [相关回归](../private/analysis/A23-literal-scan-validation-20261015/regression-final.txt)
- [独立核验](../private/analysis/A23-literal-scan-validation-20261015/validation.json)
- [验证封存](../private/analysis/A23-literal-scan-validation-20261015/SHA256SUMS)

下一步在新ELF逐类连接整数/hex/窄字符串转换渲染、输出向量和返回扫描循环；
保留FILE与mbstate的不同存活区间，逐转换观察sp+136复用后的reset及va_list/缓存
连续性。不用手工推进参数计数替代真实渲染指令。默认locale/TLS仍需显式前提，
非默认locale、完整线程栈、GetSize失败保留和实机根因继续独立待审。

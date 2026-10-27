# 日志格式、长度与类型契约审查（2026-10-14）

两份封存候选的13个C单元各预处理出76处日志调用，仅使用d/s/u/x及已有ll长度和固定宽度，没有浮点、宽字符、位置参数或动态宽度。加入printf格式检查声明后，原代码各发现1处真实类型不匹配：ISO timing的frequency用%u，但armGetSystemTickFreq返回u64。在新的隔离源码副本中改为%llu并显式转unsigned long long、给日志声明加格式检查属性，同时限制截断后的文件写入长度；13单元的修正副本语法/类型检查均通过，未构建或执行新的ARM候选。

实际日志函数的电脑回放还确认：vsnprintf写入512byte缓冲区后，原函数把“需要的长度”直接交给fsFileWrite。512字符样例会把结尾NUL也写入请求，513/1024字符样例请求跨度超过512byte对象。新的长度限制对照最多请求511byte，原76个格式的样例结果逐项保持。当前修正副本的保守最大输出229byte，不能据通用接口的超长样例认定首次burst触发截断或找到根因。

250项native检查通过ASan/UBSan：原/限长对照各76个格式样例共152，边界/错误各11个共22，修正格式另76个。16项新增和515项相关Python回归通过，无跳过。服务仅为电脑stub，未让它越界读取；SDK FS/DMA、真实线程/locale及ARM均未执行，USB/SD0。生产/原候选/历史封存/三票据保持，remaining=0，根因未知。

## 格式与参数来源

使用封存构建的同一编译器、define/include参数做预处理，并在13单元上增加格式检查后做语法检查。源码目录不写入，结果保存在本轮新目录。清单包含编译期活跃而最终可能被GC丢弃的helper，尚未绑定全部ELF日志调用点或剪枝dead code。

| 参数类别 | 保守字节界限 | 前提 |
| --- | --- | --- |
| %d | 32bit完整范围最多11 | 实参类型正确 |
| %u / %x | 32bit最多10 / 8 | 实参类型正确，宽度是最小值 |
| %llu / %llx | 64bit最多20 / 16 | unsigned long long实参 |
| serial %s | 31 | 32byte数组、strncpy最多31、末位明确NUL |
| BuildID %s | 64 | 65byte数组、32字节转hex、[64]写NUL |
| version %s | 5 | 预处理后的1.0.0字面量 |

只有3处%s，均核对来源和终止构造。原格式按声明转换计算的最大值219byte，但原frequency实参类型不匹配，所以这个数字不是原代码在任意C执行下的安全证明。修正该一处格式/实参后的最大值229byte，在有效参数、已终止字符串和正常生命周期下小于511；字符串当前运行值及整个生命周期未读取/测量。所有原始编译诊断保留，没有忽略warning来宣布通过。

修正副本仅变动core.c、core.h、uvc/uvc_device.c三个文件：限长、printf属性和frequency格式/显式cast。handler、main/worker/callback、协议及保存门槛的其他文本保持。副本仍带原recipe header，仅供源码审查；若下一步构建完整候选，必须生成新的recipe和证据关联。没有修改生产、旧封存源码或向设备部署这些修正。

## 截断返回值与实际文件请求

原文件logger的真实函数体复制到电脑夹具，以真实host vsnprintf格式化，FS仅记录请求和调用次数。host库不是Switch newlib执行；样例是正确类型的保守ASCII输入，原frequency类型错误通过AArch64编译诊断核验，未在host上执行该不匹配实参。

| 输入字符串长度 | 原required / write请求 | 限长对照write请求 |
| --- | --- | --- |
| 0 | 0，不打开文件 | 不打开文件 |
| 1 / 511 | 1 / 511 | 1 / 511 |
| 512 | 512，包含缓冲区结尾NUL | 511，不含NUL |
| 513 / 1024 | 513 / 1024，超过512byte对象 | 511，不含NUL |

stub只复制min(request,512)，避免检查自身制造越界；超长请求的观测不等于SDK实际越界读、DMA或文件损坏。76个原格式样例在限长前后长度、内容校验和、offset与FS次数完全相同，修正格式76个样例也在其各自界限内。通用logger的缺口已确认，当前日志语言未显示会自然产生超过229byte的有效修正输出。

未挂载、空输出、格式化失败不打开文件；open失败不close未取得的file；write失败仍close。既有GetSize错误仍被忽略，offset初值0继续交给Write，限长没有改变这一点。它是另一项未修复的错误处理缺口，不据调用offset0认定实际覆盖过日志。

## 最终ELF的字符串FILE条件

原logger机器码明确传capacity512，自身SP832；vsnprintf/_vsnprintf_r构造字符串FILE，初始_flags低16bit为0x208=__SSTR|__SWR，剩余空间511。实际stdio.h定义与机器码核对。formatter初始malloc检查bit7，当前初始值为0；__ssputs_r增长检查mask0x480，当前初始值也不命中。

这允许在有效字符串FILE且相关flags保持的条件下排除初始缓冲分配与字符串增长分支。尚未证明全调用期间FILE flags不被错误路径/非法参数改变，也未把这些条件接进完整CFG；不能用“初始bit为0”直接删除所有malloc、stdio或错误路径。原formatter还会无条件读取locale信息，输入格式窄并不自动解决TLS/locale回调。

下一步把这些修正以新recipe构建完整隔离候选并保持既有启动/退出/文件观测，再将当前格式语言、FILE状态与ELF调用点绑定。需要逐条核对get_arg、有效字符串输出、错误出口/重入和reent/locale初始化后，才能继续讨论完整线程栈；既有352/768byte入口不受本轮审查影响。GetSize失败、失败FS/启动预算/部分线程回滚继续保留，当前票据不续期。

## 可复核材料

- [格式/机器契约分析器](../tools/analyze_a23_log_contract.py)、[审查工具](../tools/audit_a23_log_contract.py)、[真实日志夹具](../tests/a23_file_log_fixture.c)、[16项检查](../tests/test_a23_log_contract.py)。
- [审查结果](../private/analysis/A23-log-contract-review-20261014/audit.json)、[审查摘要](../private/analysis/A23-log-contract-review-20261014/SHA256SUMS)。
- [修正源码core.c](../private/analysis/A23-log-contract-review-20261014/dormant/source-reviewed/core.c)、[格式检查声明](../private/analysis/A23-log-contract-review-20261014/dormant/source-reviewed/core.h)、[frequency修正](../private/analysis/A23-log-contract-review-20261014/dormant/source-reviewed/uvc/uvc_device.c)。
- [验证结果](../private/analysis/A23-log-contract-validation-20261014/validation.json)、[完整回归](../private/analysis/A23-log-contract-validation-20261014/regression.txt)、[验证摘要](../private/analysis/A23-log-contract-validation-20261014/SHA256SUMS)。
- [此前formatter边界](A23_FORMATTER_FRONTIER.md)、[进度交接](PROGRESS_HANDOFF.md)。

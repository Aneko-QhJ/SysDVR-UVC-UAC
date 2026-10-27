# 日志格式化分派与默认locale审查（2026-10-14）

_svfprintf_r的br x1是受范围检查保护的只读分派表：91个halfword表项对应28个函数内部目标，已按实际ELF和CFG展开。blr x23的初始默认目标则是__utf8_mbtowc，自身用户态栈16byte；这条调用只能在有效reent/TLS、线程locale为NULL、全局locale未变化及正常重定位的条件下展开，不能推广到任意线程locale。

展开分派后发现更深的依赖：宽字符与浮点转换、参数读取、断言失败、stdio/系统退出及回调中的静态循环。上一轮“两条formatter间接边”描述的是当时已探索图的边界，不是完整调用链只剩两处问题。本轮保留新增未知，整体线程栈仍未确认，首次SDK burst根因未知。

20项新增和499项相关Python回归通过，无跳过。每候选核对91表项/28目标、256个输入byte及382处RELR位置，与独立readelf解码逐项一致。新增审查没有构建或执行ARM、修改生产/候选runtime、打包或访问USB/SD；完整回归继续覆盖既有电脑模型。历史封存和三份票据保持，remaining=0。

## 分派目标可以有限展开

实际机器码依次计算w1=w0-0x20，以无符号cmp/b.hi拒绝大于0x5a的索引，再从[x26,w1,uxtw #1]读取halfword。目标是adr基址加该halfword符号扩展后乘4。有效索引0..90、字符32..122，其他输入走default；32bit下溢也由无符号检查拒绝。256个输入byte逐项核对，另检查32bit边界与寄存器截断。

两配置的182byte表位于只读.rodata，摘要相同；91个表项归并为28个已解码的函数内部instruction地址，default也在范围内。分析器跟踪所有已解析CFG路径上x26的最近定义，确认读表处只来自表地址add，add只来自对应adrp。直接分支不得跳过guard；不支持的函数内部bl、可写表、越界目标、指令/表基址变化均拒绝。调用保持x26及正常只读映射属于明确ABI/内存前提，未测硬件故障或时间成本。

新frame分析从br处沿全部28个目标继续工作，不按当前日志的格式字符剪枝，也不把br改成普通call或增加不存在的栈层。有限目标解决了这一条未知边，不能省略它带出的callee。

## 默认locale仅有初始与条件证据

实际formatter调用__getreent，从reent偏移64读取线程locale；非NULL时选线程对象，否则选从GOT取得并保存在栈上的默认对象。从所选对象偏移464读取函数指针，再通过blr x23调用。__locale_mb_cur_max也按相同选择读取偏移584。

ELF中GOT指向__global_locale，后者是656byte可写对象；其偏移464初始为__utf8_mbtowc，偏移584初始为6。默认_impure_data的偏移64初始为NULL。解析15个RELR编码项得到382个位置，与readelf列表一致，GOT和callback slot都需要加load bias；直接把未重定位的文件指针当运行时地址是不成立的。

两份图分别保存：只展开分派表，保留blr x23未知；再明确假设线程locale一直为NULL、全局对象未改、reent/TLS有效、loader正确重定位，才接__utf8_mbtowc。其实际机器码自身SP16，无直接callee；独立函数入口的16byte不依赖默认locale选择。证书不能通过删掉条件字段升级为无条件结论。非NULL线程locale、当前对象内容、TLS发布和实机locale均未核验。

新增newlib头文件快照仅说明reent含_locale成员及声明出处；偏移64/464/584来自已链接机器码，不声称已编译验证对应C结构布局。本轮没有对照完整threadCreate/_EntryWrap/newlibSetup路径证明所有日志时刻的NULL状态，也没有依据未链接setlocale就宣布对象不可变。

## 新可达路径继续保留未知

全部格式类型的分派会把_wcrtomb_r、_wcsnrtombs_l、get_arg、浮点/bignum转换、断言与普通stdio分支纳入图中，带来更多函数指针、分派表、不返回尾部、SP变化和递归循环。部分循环经断言/退出到__appExit再进入logger；这只是未作条件剪枝的静态图，不证明实际递归、栈耗尽、异常回调可达或实机故障。既有cleanup gate及格式/FILE标志等条件尚未在这些新路径中建模，不擅自删除它们。

| 根入口 | 默认locale条件图的已遍历用户态路径 | 仍有未知 |
| --- | --- | --- |
| main | 7536byte | 29条 |
| VideoStreamThread | dormant6544 / window6560byte | 各29条 |
| AudioStreamThread | 6064byte | 29条 |
| LogFunctionImpl | 5904byte | 28条 |
| _svfprintf_r | 4720byte | 28条 |

这些数字随已探索路径增加而变大，是已遍历路径，绝不是完整上界、实际峰值或剩余栈余量。原session_capture352byte与独立保存768byte保持，不进入formatter；所有线程整体上界继续未知。SDK“不返回”约定和n=1/n=3等待profile沿用上一轮的明确限制，不包含内核/异常栈，也不证明停止时限。

下一步先整理当前候选全部日志格式及字符串参数来源、vsnprintf所构造FILE的标志/长度和实际转换集合，确定哪些宽字符/浮点/普通stdio路径能在有效调用中排除；再针对剩余get_arg、转换callback与错误出口逐条审查。主线程/worker reent和locale初始化、logger重入门槛及截断后的写入长度也需单独核验。当前采集递归/共享标志的适用前提、启动预算、失败FS和部分线程回滚继续保留；电脑结论不恢复硬件次数。

## 可复核材料

- [独立formatter分析器](../tools/analyze_a23_formatter.py)、[只读审查工具](../tools/audit_a23_formatter.py)、[20项检查](../tests/test_a23_formatter.py)。
- [审查结果](../private/analysis/A23-formatter-frontier-review-20261014/audit.json)、[审查摘要](../private/analysis/A23-formatter-frontier-review-20261014/SHA256SUMS)。
- [验证结果](../private/analysis/A23-formatter-frontier-validation-20261014/validation.json)、[完整回归](../private/analysis/A23-formatter-frontier-validation-20261014/regression.txt)、[验证摘要](../private/analysis/A23-formatter-frontier-validation-20261014/SHA256SUMS)。
- [ELF/异常约定](A23_ELF_BOUNDARIES.md)、[等待与采集条件](A23_THREAD_PATHS.md)、[交接](PROGRESS_HANDOFF.md)。

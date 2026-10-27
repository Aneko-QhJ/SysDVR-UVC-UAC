# 转换入口到真实取参路径审查（2026-10-15）

本轮续接[参数缓存局部审查](A23_ARGUMENT_CACHE.md)，将实际转换入口、字符读取、
只读分派表、宽度/长度修饰符处理与取参片段连接为同一份机器状态。两配置的73种
绑定日志格式、97个转换，共776组日志转换回放与12组对照通过。发现上一轮标为
`x32/x64`的区域实际属于`%o`分支；真实十六进制路径已重新核验。
这修正的是电脑分析，USB失败根因仍未知。

## 十六进制路径更正

相对于`_svfprintf_r`入口，上一轮`PATHS`中的`x32=0x1bf0`、`x64=0x191c`实际位于
八进制取参区域。当前候选只读分派表将`o`送至`+0x18f0`，再按长度进入这些区域。
局部无符号取参值、ABI与缓存边界的旧回放仍是该区域的观察，不能作为已验证真实
`%x/%llx`路径的证据。

真实`%x`先进入`+0x240`设置小写数字表，`%X`进入`+0x2560`设置大写数字表，二者
汇合到`+0x2588`。真实32位十六进制取参入口是`+0x286c`，64位入口是`+0x2598`，
取参片段均在`+0x295c`停止。新工具单独记录这些入口，不改写旧工具或旧封存。

## 本轮连接的范围

重新从两份既有完整ELF绑定直接日志调用及只读字符串，仍为79/80个调用点、73种
格式；转换token与独立从格式字符串扫描的结果逐项一致。每个转换在实际
`+0x1e4`入口开始，执行入口初始化、逐字节读取、91项实际halfword表跳转、零填充/
数字宽度/`ll`处理、转换前保存与加载，直到真实取参入口。随后保留全部寄存器和
内存，继续执行取参指令，没有重新注入位置标志或取参入口状态。

每个转换的四组条件为两种ABI布局乘以两种旧栈内容：`0xdeadbeef`及64位全1。
顺序参数索引与缓存计数由转换序号注入，最大索引7；第八项核验转向栈取参。
六种当前类型d32/u32/u64/x32/x64/窄字符串均核对原始值、索引推进、缓存写入与
哨兵。字符串仅取指针，没有解引用或执行输出。

所有当前转换都由真实入口的4字节写入清零sp+136，再从该位置加载位置标志0；
到取参前没有其他重叠写入。即使旧内容为指针或全1，当前局部回放也未进入get_arg。
这将该片段内的存活区间明确为“入口reset到转换前加载”，不是全函数恒零。
直接SP访问清单仍保存三处宽写入复用，未解决间接指针别名或全函数存活区间。

每配置六组敏感性对照：`%1$d`、`%32$u`通过真实数字扫描设置位置标志并到达
get_arg调用前沿；`%33$u`在设置标志前拒绝；`%0008x`、`%12x`及`%llx`走实际
宽度/长度分派。测试另外删除reset后观察到旧非零标志进入helper前沿，防止模型
无条件屏蔽get_arg。helper自身仍未执行。

## 仍未证明的内容

percent位置、顺序索引、缓存内容、有效va_list/ABI及实参值仍由电脑提供。前面的
字面文本/locale扫描、函数完整初始化、上一个转换的渲染和转换间循环均未执行；
不能推断整个73格式运行会保持这些前提，也不能删除完整调用图里的get_arg。
本轮没有完整符号证明、完整格式化输出、FILE生命周期/TLS验证或完整线程栈上界。
SDK memcpy、分配、get_arg、Switch线程和候选ARM均未执行。

GetSize失败后继续offset0写入的问题尚未修复；本轮也未修改生产设备源码、旧
runtime、旧证据或三个测试票据。没有新ARM构建、固件打包、USB访问或SD访问。
SDK burst票据仍为failed_no_retry、remaining=0、acquisition_enabled=false。

## 验证与续接

新增13项测试核对真实hex入口、reset缺失敏感性、位置索引拒绝、ABI边界、真实
宽度/长度处理、字节篡改、未初始化读、未知指令与预算失败，以及旧封存保持。
571项相关测试全部通过，最终覆盖无跳过。首次默认回归未加载17个模拟fixture入口，
随后使用首次burst离线修正时封存的环境配置，仅补跑这132项；按测试ID合并439项
首次成功与132项补跑成功，得到571个不同测试。中间选错旧fixture/测试名的失败
记录保留，不作为最终源码回归结论。原13项新增测试包含在571项内。
独立核验7202个旧及新审查证据文件、当前源码哈希和三个票据，均保持。

复查需使用本机`python3.12`，系统`python3`为3.9，旧解码器会主动拒绝。审查工具的
`--output`必须指向新目录；相关fixture环境取
`private/analysis/A23-IOUSBHost-burst-test-20261013-170016/offline-fix/python-environment.json`，
包括BOOL修正后的入口及ISO7关联模拟样例。不要指向早期未修正fixture，不启动实机。

- [审查结果](../private/analysis/A23-parser-bridge-review-20261015-final/audit.json)
- [dormant逐转换回放](../private/analysis/A23-parser-bridge-review-20261015-final/dormant/profiles.json)
- [30秒逐转换回放](../private/analysis/A23-parser-bridge-review-20261015-final/window-30s/profiles.json)
- [审查封存](../private/analysis/A23-parser-bridge-review-20261015-final/SHA256SUMS)
- [相关回归](../private/analysis/A23-parser-bridge-validation-20261015/regression.txt)
- [模拟fixture补跑](../private/analysis/A23-parser-bridge-validation-20261015/fixture-regression-final.txt)
- [独立核验](../private/analysis/A23-parser-bridge-validation-20261015/validation.json)
- [验证封存](../private/analysis/A23-parser-bridge-validation-20261015/SHA256SUMS)

下一步先审默认locale回调的字面扫描、实际函数初始化与FILE别名，再接转换渲染及
循环，核对顺序索引/缓存的连续状态。保留位置栈复用边界，不能从单转换回放直接
剪枝全图；GetSize失败保留策略及完整线程栈仍是后续独立缺口。继续仅电脑研究。

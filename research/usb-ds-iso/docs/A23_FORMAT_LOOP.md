# 当前日志格式的完整渲染与扫描循环回放（2026-10-15）

本轮续接[字面扫描与初始化](A23_LITERAL_SCAN.md)，执行取参后的真实整数、hex和
窄字符串渲染、输出向量、追加/刷新及返回扫描，直到`_vsnprintf_r`返回。两配置
73种格式、三组值、四种容量、两种ABI共3504组完整回放通过；4656次取参连续性
核验通过，全部输出与独立类型化本机snprintf逐字节一致。没有手工推进索引或缓存。
这是当前样例路径的电脑证据，USB根因仍未知。

## 输入与独立输出对照

重新绑定既有两配置79/80个直接日志调用点及其ELF只读格式，覆盖73种格式、97个
转换，最多8个实参。仍只有d32/u32/u64/x32/x64/窄字符串六种当前类型，flags为空
或零填充；没有动态宽度/精度、位置参数、宽字符或浮点当前日志。

每配置每格式采用zero、limits、mixed三组值，容量0/1/32/512与寄存器/栈两种ABI。
zero用整数0及可变字符串空串；limits用signed最小值、unsigned/hex最大值及声明
界限的字符串；mixed用不同整数及包含percent/换行的窄字符串。固定版本字符串
保持1.0.0，可变serial/build分别不超过31/64字节。值和终止字符串均为模型输入，
没有读取实际Switch参数。

本机libc的snprintf通过独立ctypes类型传入int32/uint32/uint64和字符串，获取完整
应输出长度及字节；共438份独立对照结果。每个ARM指令回放核对完整返回长度、
容量内实际输出、最后NUL、截断后的剩余容量及缓冲区前后哨兵。容量0不写，容量1
只有NUL，容量32覆盖中途耗尽；容量512容纳当前输出。最大完整输出229字节，
与此前修正日志语言的声明界限一致。

## 真实连续状态

从wrapper、FILE和va_list副本初始化开始，沿实际TLS/默认locale/UTF-8扫描及转换
入口继续执行，没有在取参、渲染或循环处重新注入机器状态。完整格式结束时，
每个顺序索引和缓存计数由0逐次推进到实参数；八实参日志的扫描入口观察为0..8，
每次取参前cached=i、结束cached=i+1，始终只有一次对应缓存写入。

寄存器ABI下，前七项在保存区，第八项从栈读取，实际copied va_list的gr_offs及
栈指针与八次读取一致；独立栈ABI也逐项核对。原va_list未改变。
这些检查没有用“手工更新计数然后重跑下一转换”替代实际渲染。

十进制多位数字渲染在实际`stp x22,x24,[sp,#136]`复用栈位置，随后实际恢复寄存器、
清零渲染局部值并在下一个转换入口重新reset。688组回放观察到重叠宽写入，全部
当前取参时position=0；不能把sp+136整函数都解释为一个始终为0的标志。
输出向量超过七项时，实际`__ssprint_r`/非增长`__ssputs_r`刷新并返回扫描；
所有当前回放的FILE flags保持0x208，容量耗尽不绕过返回长度或NUL核验。

位置reset故障对照每配置一组：把真实入口的mov w3,0改为1，观察到get_arg调用
前沿后停止，helper不执行。新增测试还改动真实hex右移量，独立本机输出能检出
错误；另检查缺失第八实参字节、指令预算/未知指令及ELF渲染机器码篡改拒绝。

## 模型边界与栈观察

当前回放包括实际渲染与循环，但strlen/memset/memcpy仍为有界内存模型。模型
调用使caller-saved通用寄存器和条件flags未知，并保持BL返回地址语义；没有
执行这些SDK函数、get_arg、分配或错误退出。所用分派表、函数指令和GOT/locale
对象绑定既有ELF字节。

所有当前回放观测持有用户SP最多1664字节，包含wrapper/formatter/locale/追加
函数帧；不包含上述模型替代的SDK helper内部栈、caller、内核或异常栈。因此仍
不能给出完整格式化链或线程上界，也不从通用调用图删除get_arg或未知分支。

TLS/reent、输入ABI/参数/终止字符串由模型提供；初始global locale未变、零load
bias、有效映射和单次不重入均有前提。只有三组值，不是全部32/64位输入的符号
证明。非默认locale、非法参数、重入/并发、错误/宽字符/浮点等路径未闭合。
FILE flags的结论只适用于本轮样例，不是所有callback别名或运行态生命周期证明。
模型在函数返回后保留栈字节用于离线核验，不授权实际读取已退出线程的栈。

生产源码、旧runtime/工具/封存和三票据保持，无新ARM构建/执行、固件打包、USB
或SD访问。SDK burst仍failed_no_retry/remaining=0/acquisition_enabled=false。
GetSize失败后继续offset0写入的问题未修复，不能把当前格式化对照解释为USB原因。

## 验证与后续

新增15项测试与此前formatter相关回归见下列封存。工具使用python3.12，审查输出
必须指向新目录；141项相关测试全部通过，无跳过，新增15项包含在其中。
7423个既有及新增审查证据文件、生产源码哈希和三个票据已独立核验保持。
本机snprintf只是输出参考，不是Switch SDK或USB验收。

- [审查结果](../private/analysis/A23-format-loop-review-20261015/audit.json)
- [dormant完整回放](../private/analysis/A23-format-loop-review-20261015/dormant/profiles.json)
- [30秒完整回放](../private/analysis/A23-format-loop-review-20261015/window-30s/profiles.json)
- [审查封存](../private/analysis/A23-format-loop-review-20261015/SHA256SUMS)
- [相关回归](../private/analysis/A23-format-loop-validation-20261015/regression.txt)
- [独立核验](../private/analysis/A23-format-loop-validation-20261015/validation.json)
- [验证封存](../private/analysis/A23-format-loop-validation-20261015/SHA256SUMS)

下一步审SDK内存helper实际指令与调用边界，再独立设计logger的GetSize失败保留
策略，避免错误返回后以offset0覆盖已有日志。完整线程栈、运行态locale/TLS和
重入/错误路径仍需保留未知，不能由3504组成功样例直接剪枝全图或放行实机。

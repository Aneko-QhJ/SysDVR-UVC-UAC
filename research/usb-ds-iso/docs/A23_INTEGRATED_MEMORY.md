# 新ELF完整格式化与SDK内存指令连续回放（2026-10-15）

续接[GetSize保护完整候选](A23_LOG_GUARD_ARM_CANDIDATE.md)，重新绑定两个新ELF，
将真实SDK memcpy、memset、strlen指令直接接入完整formatter回放。4080组完整
回放、5808次取参、24720次helper调用均通过，全部输出与438份类型化本机snprintf
参考一致；另在新ELF重做1282组独立helper回放及12组拒绝对照。16项新增和184项
相关Python回归无跳过通过。上述均为电脑指令模型，USB根因仍未知。

## 重新绑定范围

本轮读取GetSize保护候选的dormant及window-30s完整ELF，逐字核对新反汇编。
只归一化反汇编首部的构建路径，不忽略指令或地址差异。重新解析79/80个直接
日志调用点、18个调用函数、73格式/97转换，重建formatter分派、默认locale及
所有允许函数的字节摘要。最终logger保护/511限长证书也从新ELF重算并与该候选
记录核对，没有复用旧ELF的绝对地址或把旧回放结果记到新候选。

完整回放仍从_vsnprintf_r入口开始，实际执行FILE/va副本初始化、TLS/getreent、
默认locale/UTF-8格式扫描、取参、整数/hex/窄字符串渲染、输出向量/刷新、循环
和返回。本轮在真实BL或尾调用处进入SDK helper，保留同一寄存器、SIMD、内存、
条件flags及返回地址，执行其实际指令后返回；不在helper或下一转换处重注入状态。

## 输入、数量与输出对照

每配置2040组，两个配置合计4080组：原73格式×zero/limits/mixed三组值×四容量
0/1/32/512×register/stack两ABI共3504组；三个含窄字符串的格式另加页内偏移
1/15/31/4095，共576组。包括5字节版本、31字节serial及64字节BuildID。
参数值与终止字符串是注入输入，不是从Switch读取。

| 项目 | 两配置合计 |
| --- | --- |
| 完整formatter回放 | 4080 |
| 连续实际取参 | 5808 |
| SDK memcpy调用 | 15840 |
| SDK memset调用 | 4080 |
| SDK strlen调用 | 4800 |
| 独立类型化本机输出参考 | 438 |
| 新ELF独立helper指令回放 | 1282 |
| 拒绝对照 | 12 |

438份参考对应73格式×三组值×两配置；不同容量、ABI和字符串地址复用同一个
应输出文本，不从模型输出生成oracle。逐字节核对完整返回长度、截断输出、NUL、
剩余容量及前后哨兵；最多229字节，当前样例FILE flags保持0x208。顺序索引和
缓存0..8连续，第七到第八项跨寄存器/栈读取及原va保持仍核验。

## 实际helper与映射条件

每次memcpy/memset逐次记录机器指令读写范围并核对结果；memcpy不读请求范围外，
两者不写请求范围外，还必须通过formatter活跃栈/输出范围检查。返回值、SP、
已初始化的callee-saved通用寄存器及SIMD低64位均核验保持。跳过实际memcpy或
伪造strlen返回值的对照在helper返回处拒绝，不让抽象实现悄悄替代SDK。

当前完整formatter中的memset实际请求只有8字节；独立helper补充仍覆盖0..96的
17种长度、填充值和对齐。192字节零填充停在DCZID/ZVA架构前沿；本轮没有执行
大块清零，也不由这些成功样例证明所有memset输入。

strlen还用于读取locale的只读小数点字符串，这部分长度与可读区间来自新ELF
只读字节。三个输入字符串则显式注入覆盖其内容的完整页，以非零0xa5填充周边，
再写真实终止NUL；跨页字符串提供覆盖内容的两页，没有在运行时自动补零。

64字节BuildID放在页内4095偏移时，实际路径读取指针前31字节；整个样例集合
还观察到终止NUL后最多31字节读取。所有读取均在声明映射内，返回长度正确。
删除必要padding字节或不提供周边页会拒绝。此结果不能证明Switch映射满足条件，
也不能据逻辑字符串外读取直接断言设备故障；只读ELF映射同样是明确前提。

## 拒绝、栈观察与剩余边界

每配置六组拒绝对照：位置reset损坏到get_arg前沿、TLS标记无效到diagnostic前沿、
未知locale callback、缺失字符串映射字节、指令预算耗尽及大块memset架构前沿。
新增测试另检查helper机器码漂移、错误返回、跳过复制、页尾/向量及两ABI容量。
没有执行get_arg、分配、诊断/异常退出或未知callback来伪造通过。

所有完整回放观察入口以下用户SP最多1664字节，现在包含实际三个helper指令；
三helper在新ELF独立静态分析均为自身栈0的叶函数。1664只覆盖本轮具体输入与
_vsnprintf_r入口，未包含其caller、logger、内核或异常栈，不是线程上界，也不是
全输入符号证明。没有据此剪枝通用formatter或全局get_arg/错误/重入分支。

有效TLS/reent、ABI/参数、初始global locale未变、零load bias、只读及输入映射
仍由模型提供或假设。非默认locale、并发/重入、非法指针和完整错误路径未闭合；
本机libc只作输出参考。GetSize保护仍只有隔离候选，无生产或实机修复结论。

## 封存与继续入口

本轮没有新ARM构建或执行、固件打包、USB或SD访问；生产、旧工具/runtime、
旧封存及三个票据哈希保持。SDK burst仍failed_no_retry、remaining0、采集禁用。
8721个旧证据及本轮审查文件独立哈希核验，相关184项回归无跳过；工具使用
python3.12，审查输出须指向新目录。

- [审查汇总与源哈希](../private/analysis/A23-integrated-memory-review-20261015/audit.json)
- [重新绑定的日志清单](../private/analysis/A23-integrated-memory-review-20261015/linked-catalog.json)
- [dormant完整回放、内存访问与参考文本](../private/analysis/A23-integrated-memory-review-20261015/dormant/profiles.json)
- [30秒完整回放](../private/analysis/A23-integrated-memory-review-20261015/window-30s/profiles.json)
- [新ELF独立SDK补充](../private/analysis/A23-integrated-memory-review-20261015/dormant/standalone-sdk-memory.json)
- [新ELF logger复核](../private/analysis/A23-integrated-memory-review-20261015/dormant/logger-machine.json)
- [审查封存](../private/analysis/A23-integrated-memory-review-20261015/SHA256SUMS)
- [184项相关回归](../private/analysis/A23-integrated-memory-validation-20261015/regression.txt)
- [独立核验](../private/analysis/A23-integrated-memory-validation-20261015/validation.json)
- [验证封存](../private/analysis/A23-integrated-memory-validation-20261015/SHA256SUMS)

下一步把实际logger调用、vsnprintf外层、TLS/reent生命周期及重入/错误条件接入
同一条局部调用过程，区分已回放样例的栈范围和仍未证明的线程上界。字符串真实
来源/映射与异常路径继续保留未知，生产及实机票据不变，不以本轮模型放行硬件。

# 新 ELF 日志调用点与字符串 FILE 状态审查（2026-10-14）

本轮只读审查[日志修正完整候选](A23_LOG_ARM_CANDIDATE.md)，将实际日志调用与源码格式
清单逐点绑定，并审查字符串 FILE 的局部错误更新和追加函数。新候选的限长修正保持；
没有新 ARM 构建、运行或部署，生产源码、旧候选和旧封存均未改动。USB ISO 根因未知。

## 源码清单与实际调用点

| 配置 | 直接日志调用点 | 含日志的函数 | 已绑定不同格式 | 清单中未绑定格式 |
| --- | ---: | ---: | ---: | ---: |
| dormant | 79 | 18 | 73 | 3 |
| window-30s | 80 | 18 | 73 | 3 |

先用 FUNC 边界和最终 ELF 字节核验反汇编，再沿调用者 CFG 求寄存器到达定义。
直接 BL 和尾调用 B 都计数。ADRP/ADD/MOV 组成的实际 x0 格式地址必须沿所有支持的
前驱路径已知；函数调用使 x0..x18 的值失效，x19..x29 保持只依赖 AAPCS64 约定。
条件合流保留所有来源，未知来源、内部未知跳转、循环地址定义均拒绝猜测。

每个解析出的地址均位于只读、可分配、文件实际包含的区域，必须存在 ASCII/NUL
终止字符串，并与新候选的源格式清单一致。73种格式的最大声明输出界限229字节，
继续要求有效实参、字符串来源上限和映射有效；不是运行时测量。

30秒配置多出的调用点同样打印 `Video stream thread exiting`，位于 VideoStreamThread。
这是不同配置的物理调用点计数，不能将它当成额外源码日志或真实退出次数。
三条未绑定格式均为 UAC 初始化日志：AC 注册失败、AS 注册失败、UAC 初始化成功。
这里只确认未出现在这些直接调用点，不能据此排除整个二进制的间接日志调用。

## FILE 初始状态、错误更新与追加指令

新 ELF 的 `_vsnprintf_r` 重新确认局部 FILE 起点sp+72，flags位于FILE+16，初始低16位
0x208（字符串+写模式）。初始动态分配检查仍测试bit7；追加增长仍检查mask0x480。
绑定本地 stdio.h 的 SSTR/SWR/SMBF/SOPT/SERR 定义并保存头文件哈希。

`_svfprintf_r` 对 `[x18,+16]` 有两个半字写入位置。沿已解析的分派 CFG 核验各自
到达定义：第一个来自一条、第二个来自三条错误处理路径，共四条更新，均先读取
原flags，再OR0x40（SERR）。不是只读取第二个写入前的最近指令而忽略另外两个前驱。

遍历全部65536种16位状态，`(flags|0x40)&0x480 == flags&0x480` 均成立。
因此这些已绑定的局部错误更新不会自行增加增长位；0x208经这些更新成为0x248。
但别名写入、所有callee/回调效果、TLS状态和完整FILE生命周期仍未证明。
不以此宣布整个格式化器不会分配。

新增 `__ssputs_r` 的实际 ARM 指令解释回放，每配置60组非增长场景，覆盖：

- flags0x208/0x248；剩余容量0/1/511。
- 输入长度0/1/511/512/513/1024，以及跨边界分块、20次64字节追加、耗尽后继续追加。
- 每次复制不超模型输入与目标边界，累计储存最多原容量，剩余空间不负数，flags保持，SP恢复。

每配置另外6组将增长位设为1的敏感性对照，正确走到增长分支；在那里停止，未执行
分配函数。两配置共132组场景，非增长场景各回放6098条指令。memcpy由有边界检查的
电脑模型替代，并按ABI破坏调用者保存寄存器，未执行真实SDK memcpy/FS/DMA。
这是注入有效FILE/输入的有限指令profile，不是完整符号证明或实际Switch运行。

## 未解决的格式化路径

新 ELF 重新绑定91项只读分派表/28个内部目标、256种输入byte分派、382个相对重定位，
并与readelf列表对照。默认locale仍指向UTF8 callback；线程locale为NULL、全局locale
不变、重定位与TLS有效只是显式条件，不是实机验证。

每配置仍有28个直接get_arg调用点。当前日志清单没有位置参数，并不足以证明这些
分支在机器码中不可达；本轮没有剪枝它们。重新展开的条件图保留get_arg、宽字符、
错误/重入和静态调用循环。main仍有29项未闭合，LogFunctionImpl有28项；不推断真实
递归已经发生，也不把已知路径前缀当成整线程栈上界。

关联保存直接入口仍为768字节，session_capture为352字节；完整线程栈仍未知。
文件大小读取失败后继续offset0写入的行为保持，尚未修复，也未观测真实文件覆盖。

## 证据与后续

18项新增Python核验覆盖寄存器调用约定、合流未知路径、写区/未终止字符串、实际字节
篡改、局部错误更新、截断/分块追加、增长分支及保留未知项。542项相关回归无跳过。

- [总审查](../private/analysis/A23-linked-logs-review-20261014/audit.json)
- [dormant直接日志绑定](../private/analysis/A23-linked-logs-review-20261014/dormant/linked-calls.json)
- [30秒直接日志绑定](../private/analysis/A23-linked-logs-review-20261014/window-30s/linked-calls.json)
- [FILE局部状态](../private/analysis/A23-linked-logs-review-20261014/dormant/file-state.json)
- [追加指令回放](../private/analysis/A23-linked-logs-review-20261014/dormant/append-profiles.json)
- [新ELF条件调用图](../private/analysis/A23-linked-logs-review-20261014/dormant/conditional-stack.json)
- [审查封存](../private/analysis/A23-linked-logs-review-20261014/SHA256SUMS)
- [相关回归](../private/analysis/A23-linked-logs-validation-20261014/regression.txt)
- [独立核验](../private/analysis/A23-linked-logs-validation-20261014/validation.json)
- [核验封存](../private/analysis/A23-linked-logs-validation-20261014/SHA256SUMS)

下一步检查实际格式解析器的位置参数状态和get_arg入口条件，按73种已绑定格式逐步
约束错误/宽字符/浮点路径，并核验FILE传递与回调别名。继续研究GetSize失败时的保留
策略。只做电脑工作；failed_no_retry/remaining0/acquisition_enabled=false，USB/SD0。

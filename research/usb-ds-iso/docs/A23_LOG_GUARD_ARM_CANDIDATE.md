# 日志大小读取失败保护的完整ARM隔离候选（2026-10-15）

续接[SDK内存函数与日志保护](A23_SDK_MEMORY_LOG_GUARD.md)，将GetSize失败保护接入
两种配置的完整隔离候选，各编译13对象并链接真实libnx ELF。两配置各91项原有
启动/退出/文件/容量观察保持；262项路径检查及194项独立logger错误/长度对照
通过，共638项native ASan/UBSan检查。12项新增及168项相关Python回归通过，
无跳过。所有结果来自电脑编译、静态核验或注入模型，USB根因仍未知。

## 新构建身份与源码范围

基线为[此前完整日志候选](A23_LOG_ARM_CANDIDATE.md)，保留类型修正、511字节限长、
固定关联路径及已有诊断/启动/退出代码。新副本仅core.c和生成recipe头文件变化；
生产源码、旧runtime、旧工具和封存原样保留。

新recipe绑定工具/fixture源哈希、两个旧封存manifest、SDK相关头文件、libnx.a、
switch.specs、编译器字节与版本。配置再绑定0/30000ms窗口及GetSize保护；配置
身份互异，并在最终ELF只读段逐字节找到实际recipe数组。它是构建关联标识，
不认证实机来源，也不是ELF自哈希。ELF自身SHA256另在审查结果中保存。

| 项目 | dormant | window-30s |
| --- | --- | --- |
| 编译对象 | 13 | 13 |
| 严格格式检查单元 | 13 | 13 |
| text | 156874 | 157186 |
| 相对旧日志候选text变化 | +64 | +64 |
| data / BSS变化 | 0 / 0 | 0 / 0 |
| logger机器码字节 | 312（旧304） | 312（旧304） |
| logger自身栈 | 832 | 832 |

完整ELF只链接，未执行或打包NSO/NSP，未部署或写卡。旧对象阶段保留旧recipe的
限制已通过新完整构建解决；不能将本轮离线构建身份当作实机测试授权。

## 最终链接代码中的保护与限长

新分析器从最终ELF重建函数范围，反汇编逐字核对实际指令，五个BL调用按机器码
相对位移绑定到真实SDK符号。GetSize Result的CBZ、Open失败CBNZ、格式化非正数
返回的b.le及分支目标都核对原始指令字；没有沿用core.o的地址或重定位证书。

GetSize之后Result=0走Write→Close，1、72、0xffffffff只走Close；实际CBZ只比较
w0是否为0，所有非零Result采取同一路径。成功打开后的Close一次，打开失败直接
恢复栈返回。返回长度跨SDK调用的spill/load、带符号min(length,511)、buffer地址、
Write参数和唯一SP恢复均检查。联合修改ELF字节及反汇编，将CBZ反向、限值改为
512或改变调用目标的对照均被拒绝。

本机logger仍使用候选的精确函数体与内存文件服务替身，两个候选core.c中逐字
确认该函数体。194项检查重跑：73格式、6长度边界及9类故障×2长度，基线和保护
版各97项。四种GetSize失败输出各7/513字节输入，保护版全部Write0/Close1，
原文件内容和大小不变；其余每版本89项观察保持。基线offset0覆盖在电脑替身
复现，不推断实际Switch出现过该Result。

写入已发生后才报错的部分写入仍可能改变文件，没有回滚或持久性保证。SDK
调用遵循ABI及vsnprintf契约仍是前提；本保护也没有解决并发日志/追加或重入。

## 生命周期与静态范围

本轮对两配置分别重新编译native启动/退出fixture：45启动、20退出、20文件场景
及6容量检查各91项。原始返回值、调用计数、保留/清理分支与基线一致；新INI1/
REL1样本用对应新recipe独立解码，startup/ownership与文件receipt语义保持。
262项固定路径检查同样重跑。native文件仅写电脑目录，不操作SD。

这些生命周期fixture中的LOG仍是空操作，未运行Switch线程或真实文件服务。
它们验证的是隔离初始化/退出和文件策略；logger行为由前述194项精确函数体对照
单独验证，最终链接代码再将保护和限长绑定到实际ELF。638项不能解释为638次
设备启动或真实文件写入。

新ELF的保存入口直接调用图仍闭合768字节，session_capture及其入口保持352字节；
这是指定入口的用户栈范围。原单事件SDK模型每配置156组、三事件调用点证书
各32组仍成立，等待/清理/协议/timeout/main/worker/callback源码不变。
没有停止时间界限，也不从它们推出USB URB已排空或整个线程栈安全。

此前3504组formatter及SDK helper回放绑定旧ELF，本轮未在新ELF上重跑这两组
分析；不能直接沿用旧地址或证书。完整formatter仍有helper模型，strlen映射、
大块memset架构前沿、运行态TLS/locale、重入/错误和完整线程栈仍需研究。

## 封存与下一步

12项新增测试包括实际ELF/反汇编漂移、联合篡改分支/限值/调用、recipe/源码
关联、两配置旧观察对照与生产/票据保持。168项相关测试全部通过，无跳过；
8602个旧证据及本轮审查文件独立哈希核验。SDK burst仍failed_no_retry、remaining0、
acquisition_enabled=false；没有USB、SD、ARM执行或部署。

- [审查结果、构建命令与所有源哈希](../private/analysis/A23-log-guard-candidate-review-20261015/audit.json)
- [总recipe](../private/analysis/A23-log-guard-candidate-review-20261015/recipe.json)
- [dormant最终logger证书](../private/analysis/A23-log-guard-candidate-review-20261015/dormant/logger-machine.json)
- [30秒最终logger证书](../private/analysis/A23-log-guard-candidate-review-20261015/window-30s/logger-machine.json)
- [dormant隔离源码](../private/analysis/A23-log-guard-candidate-review-20261015/dormant/source/core.c)
- [dormant完整ELF](../private/analysis/A23-log-guard-candidate-review-20261015/dormant/full.elf)
- [30秒完整ELF](../private/analysis/A23-log-guard-candidate-review-20261015/window-30s/full.elf)
- [精确logger本机替身](../private/analysis/A23-log-guard-candidate-review-20261015/logger-native/guarded-native.c)
- [审查封存](../private/analysis/A23-log-guard-candidate-review-20261015/SHA256SUMS)
- [168项相关回归](../private/analysis/A23-log-guard-candidate-validation-20261015/regression.txt)
- [独立核验](../private/analysis/A23-log-guard-candidate-validation-20261015/validation.json)
- [验证封存](../private/analysis/A23-log-guard-candidate-validation-20261015/SHA256SUMS)

下一步在新ELF重新绑定当前日志调用、formatter与SDK helper指令，把真实helper
访问接入完整格式化回放，并显式核对字符串周边映射和架构条件。不能因本轮
logger局部保护完成而剪枝所有错误/重入路径或宣布线程上界，生产与实机票据保持。

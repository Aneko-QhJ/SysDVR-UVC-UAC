# 日志限长与类型修正完整 ARM 候选（2026-10-14）

本轮将[日志契约审查](A23_LOG_CONTRACT.md)的三文件修正接入新的完整隔离源码树。
两种配置分别生成新 recipe，均链接 13 个对象。新 ELF 的日志函数已核验限长指令，
原有启动、退出、关联保存观察保持。ARM 未执行，未打包固件、部署或访问 USB/SD；
生产源码、旧候选和所有旧封存保持。USB ISO 根因仍未确认。

| 配置 | text | data | BSS | 相对上个完整候选 |
| --- | ---: | ---: | ---: | --- |
| dormant，0ms | 156810 | 13760 | 1007536 | 三项均不增 |
| window-30s，30000ms | 157122 | 13760 | 1007536 | 三项均不增 |

## 实际修正与构建身份

相对[定长路径完整候选](A23_WAIT_FIXED_PATH.md)，仅以下文件内容变化，文件集合不变：

- `core.c`：FILE_LOGGING 的正数 vsnprintf 返回值最多取 `sizeof(buf)-1`，即 511。
- `core.h`：LogFunctionImpl 增加 GCC printf 参数检查属性。
- `uvc/uvc_device.c`：frequency 改为 `%llu`，实参显式转 unsigned long long。
- `uvc/ep0_candidate_recipe.h`：替换为绑定本轮输入的独立 recipe。

main、worker、callback、EP0 运行时、normal/DIA1/REL1 格式、保存授权与 SDK 等待实现
保持旧副本。不是生产修复或已验证设备固件。每配置 13 单元重新经过 `-Wformat=2`
和 `-Werror` 语法检查；当前清单 76 处格式的保守输出界限仍为 229 字节，要求有效
实参和字符串来源约束。没有借此证明 SDK 的全部格式化分支可达性。

根 recipe 同时绑定输入工具哈希、上一完整 ELF manifest、本轮源码审查 manifest、
两棵 source-reviewed 全树哈希、compiler version、libnx.a 与四份 SDK 等待头文件。
配置 recipe 再绑定窗口和修正策略，写入实际参与编译的头文件。旧 recipe 未复用。

## 最终 ELF 与电脑回放

新反汇编每个指令 word 与 ELF 字节匹配，再按 ELF FUNC 边界定位 LogFunctionImpl。
日志局部栈帧保持 832 字节，512 字节 buffer 位于 sp+128。vsnprintf 使用容量512；
返回值小于等于0时跳到恢复栈/返回路径。正数返回值保存在 sp+24；写入前的实际指令为：

```
cmp  w4, #0x1ff
csel w3, w4, w3, le
sxtw x3, w3
bl   fsFileWrite
```

因此在 SDK ABI 保持调用者保存区、vsnprintf 满足其契约的前提下，该正数路径给
fsFileWrite 的长度不超过511。证据包含新 ELF/函数哈希、调用和限长指令地址。
不把局部指令核验当成完整符号证明、内存有效性证明或实机文件系统观察。

电脑 ASan/UBSan 共603项检查：旧45项启动、20项退出、20项文件、6项容量观察共91，
定长路径262项，日志250项。旧91项的 Result、服务次数、资源保留、路径等逐项保持；
带新 recipe 的 INI1/REL1 重新解码，不以不同身份字段要求二进制全文相等。

日志250项包含原格式76+同格式限长76、两实现各11项长度/错误边界、修正格式76。
限长实现的真实函数正文与两棵参与编译的 core.c 内容核对一致。原格式 host 样例用
格式要求的正确实参类型；原有 frequency 实参的错误由 ARM 编译器诊断，不通过
host 可变参数未定义行为模拟。启动 harness 的 LOG 是空操作，所以其91项不覆盖
日志运行成本；日志行为由独立真实正文回放覆盖。FS 为模型，没有 SDK FS/DMA读取。

每配置156组 SDK 等待机器指令 profile，另外32组混合三事件 profile，合计376组；
调用点证书针对新 ELF 重新绑定。它们只覆盖注入的有效事件、类型与返回结果，没有
真实超时上界、线程退出保证或 USB 取消/释放证明。保存直接调用图仍闭合768字节，
session_capture仍352字节；完整线程栈未知，formatter 间接调用/错误/重入仍未排除。

9项新增 Python 核验包括旧观察对照、源文件变化范围、ELF身份、指令边界，以及修改
limit/select/长度寄存器和 ELF 字节后必须拒绝的检查。相关回归共524项，无跳过。

## 证据与继续方向

- [构建、回放与机器码审计](../private/analysis/A23-log-candidate-review-20261014/audit.json)
- [构建输入 recipe](../private/analysis/A23-log-candidate-review-20261014/recipe.json)
- [dormant 限长机器证据](../private/analysis/A23-log-candidate-review-20261014/dormant/logger-machine.json)
- [30秒限长机器证据](../private/analysis/A23-log-candidate-review-20261014/window-30s/logger-machine.json)
- [候选 SHA256SUMS](../private/analysis/A23-log-candidate-review-20261014/SHA256SUMS)
- [相关回归](../private/analysis/A23-log-candidate-validation-20261014/regression.txt)
- [独立复核](../private/analysis/A23-log-candidate-validation-20261014/validation.json)
- [核验 SHA256SUMS](../private/analysis/A23-log-candidate-validation-20261014/SHA256SUMS)

GetSize 失败仍以初始 offset0 继续 Write/Close，本轮未修复；不能推断真实文件覆盖。
FILE 初始flags来自旧ELF审查，新ELF的完整flags生命周期尚未核验，未按日志语言剪枝
formatter CFG，TLS/locale/错误分支与整线程栈仍未闭合。

下一步在新 ELF 上绑定格式语言、FILE 初始构造、分派表和实际日志调用点，检查
get_arg/错误/locale/TLS及可能的重入路径，再研究文件大小读取失败的保留策略。
所有工作继续限于电脑；票据 failed_no_retry/remaining0/acquisition_enabled=false，
不得续发次数或重试。USB/SD0、hardware_verified/root_cause_confirmed=false。

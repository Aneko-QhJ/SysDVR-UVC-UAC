# SDK 打开失败的定位（2026-10-12）

本次打开失败的原因已确认：Codex 命令执行沙箱拒绝 IOServiceOpen 创建 USB user client。
相同诊断二进制在沙箱外成功完成初始化、描述符验证、pipe 获取和两块目标缓冲区分配，
随后正常释放资源。设备保持 A23，无需写卡。这解释最新 open_failed，不解释历史 native/raw
分歧；空窗口完成、空槽政策、取消及 callback 排空仍未验证。

## 实际对照

本轮执行三个独立准备诊断，每次最多打开一次接口，均无 STATUS、帧号查询、ISO 提交、
取消、reset、seize、配置/alt 切换或设备 TD。SDK 描述符访问可能包含标准 GET_DESCRIPTOR，
因此本轮不能描述为“USB 访问 0”。SD 访问 0，空窗口采集凭据仍 failed_no_retry/0。

| 诊断 | 实际结果 |
| --- | --- |
| 普通分阶段诊断，沙箱内 | 唯一匹配接口2，sdk_init 返回 E00002C9；Failed [super init]；后续步骤未执行 |
| 父类错误观察，沙箱内 | openWithOptions:error: 原样返回失败，底层 IOServiceOpen 为 E00002E2（kIOReturnNotPermitted）；子类改写为 E00002C9 |
| 同一父类观察二进制，沙箱外 | 原样 open options0 成功；前后身份相同、描述符通过、endpoint83通过；raw184320和共享transaction26880 bytes分配成功；退出0且资源释放 |

本机 SDK 的 IOReturn.h 定义 E00002E2 为 not permitted、E00002C9 为 internal error。
纯代码检查先确认本机 framework UUID b0d41eefc9bf39dda1c4226dcb94e78b 及父类调用路径，
再在独立诊断进程观察原始父类方法返回。观察器保持原调用参数、返回值及 NSError 不变；
不修补系统文件，也不进入生产接收器。这个证据组合确认本次访问拒绝来自执行沙箱。

## 代码与执行要求

[独立诊断程序](../host/io_usb_host_open_diagnostic.m)只提供 --describe 与
--diagnose-once 已存在输出目录；调用前独占 claim，已用目录不会再次打开接口。
每个准备步骤的 begin/end 均写盘并 fsync，保留 SDK 错误说明、failure reason 和 userInfo。
父类观察只在编译定义 A23_DIAGNOSTIC_PARENT_TRACE 的独立进程启用。
没有 ISO 提交入口；prepare 分配的缓冲区未用于 I/O，关闭时先释放它们再 destroy interface。

生产 provider 现在为失败补充 preparation_stage：provider/token/retain、前后身份、sdk_init、
descriptors、copy_pipe_83、endpoint_83、raw/transaction 分配。SDK domain/code 和原文本保留；
硬件 session 记录描述、failure reason、32bit 错误值和阶段。文本按 UTF-8 字节限制，
不会从多字节字符中间切断。标准 SDK 子类仍可能覆盖父类错误；这些字段不会恢复已被 SDK
覆盖的底层码。本次 E00002E2 来自单独的父类观察。

在 Codex 中，真正打开 USB 的命令需要使用已授权的沙箱外执行；默认沙箱仍可运行只读
文件校验、--describe、拒绝路径和纯模拟测试。--dry-run 不能验证 USB user client 访问权限。
正常 Terminal 中直接运行不等于需要 sudo；本次没有修改用户权限或设备权限。
下一次空窗口须重新冻结当前源码、准备独立单次凭据，再在正确执行环境调用 test-sdk-no-td。
本轮未准备或执行新的空窗口，不重复使用已消耗凭据。

## 验证与证据

19个适配/服务引用场景现在核对每个失败阶段；新增原始 NSError 保留和长 Unicode 错误文本
的检查通过。连同10个STATUS、18个旧no-TD、16个会话、11个运行条件、18个注入SDK形状
driver场景及9组时基向量，通过严格编译和 ASan/UBSan。114项Python回归无跳过；当前生产
二进制的5项设备访问前防护检查通过，未运行新鲜有效采集凭据。

证据位于 private/analysis/A23-IOUSBHost-open-diagnostic-20261012/：三份独立准备 journal、
诊断二进制、原调用记录、父类路径 stub 解析、前后源码快照及回归报告。
此前 run、冻结构建和原采集状态保持不变。本轮真实准备成功只证明所列步骤，不代表
新接口的实际 ISO 传输、空窗口完成或历史错误已修复。

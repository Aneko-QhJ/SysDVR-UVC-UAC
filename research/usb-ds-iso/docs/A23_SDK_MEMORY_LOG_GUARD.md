# SDK内存函数边界与日志大小读取失败保护（2026-10-15）

续接[完整格式化循环回放](A23_FORMAT_LOOP.md)，本轮完成两配置1282组SDK内存函数
指令模型回放，并在隔离源码中加入GetSize失败保护：只在读取文件大小成功后写入，
成功打开的文件仍关闭一次。194项native ASan/UBSan场景和156项相关Python测试通过，
无跳过。USB失败根因仍未知；本轮没有实机、USB、SD访问或生产源码修改。

## SDK实际指令与内存范围

回放绑定既有完整ELF的真实指令字节，包含实际SIMD读写及扫描指令；不是在ARM上
执行，也没有把这些函数替换进上一轮3504组完整格式化回放。每配置641组：

| 函数 | 每配置组数 | 覆盖与边界 |
| --- | --- | --- |
| memcpy | 203 | 29种长度、7组源/目标对齐，逐次访问在请求范围内，输出及哨兵核验 |
| memset | 204 | 17种0..96字节长度、4种对齐、3种填充值，核验低8位与哨兵 |
| strlen | 234 | 13种长度、18种地址偏移，包含页尾及向量路径，核验长度与读取范围 |

静态函数范围分析显示三者没有栈帧和外部调用。此结果只针对绑定SDK版本的用户
指令，不构成整个线程或异常/内核栈上界。

strlen在样例中最多读取字符串指针前31字节、终止NUL后31字节。模型显式提供
周边已映射页；这些访问超出逻辑字符串区间，但不能据此断言实际设备越界故障。
页尾样例并未独立验证设备映射。缺失必要映射字节的对照会拒绝，不能用任意补零
掩盖前提。memset的大块清零在DCZID/ZVA架构前沿停止；192字节零填充拒绝对照
确认边界，不宣称已覆盖大块清零。零长度、截断填充值、指令预算/未知指令和
ELF字节漂移另有拒绝检查。

完整formatter仍使用上一轮有界helper模型；TLS/reent、ABI、参数、终止字符串、
初始locale和映射的前提保持。1664字节仍只是原样例SP观察，尚未将helper真实
访问及映射条件接入完整调用过程。没有据具体样例排除全局get_arg、重入或错误图。

## 隔离日志修正及错误对照

本轮基线是上一阶段已修正类型和511字节限长的隔离logger，生产logger未改变。
唯一新增行为是：

```c
if (R_SUCCEEDED(fsFileGetSize(&file, &offset))) {
    fsFileWrite(&file, offset, buf, len, FsWriteOption_Flush);
}
fsFileClose(&file);
```

本机测试使用真实logger函数体及内存文件服务替身，不调用实际文件系统。文件
初始长度99字节；分别注入GetSize失败且不写输出、写17、写-1和写INT64_MAX。
每类用7及513字节格式化长度对照，合计每版本8个大小读取失败场景。基线未写
输出时offset保留0，会覆盖内存文件前部；新版本全部Write=0、Close=1，文件大小
及原内容逐字节不变，不使用失败API输出。此证据不等于实际Switch曾出现该错误。

每版本另有73个类型化日志样例、6个长度边界及其余错误对照，共97项；两个版本
共194项ASan/UBSan检查。除上述8项有意改变外，每版本89项观察保持，包括未挂载、
格式化/打开失败、写入失败及部分写入。部分写入后返回失败仍可改变文件内容，
本保护不回滚写入，不证明flush/close或commit持久性，也不保证并发追加安全。
打开失败无Close；打开成功后的GetSize失败仍Close一次，不递归调用日志报告错误。

## ARM对象核验范围

两配置各构建基线与保护版core.o，共4个可重定位对象；采用原隔离候选的编译参数
并加严格格式检查。每配置源码副本只有core.c新增保护，与旧生产及封存源码分离。

对象中LogFunctionImpl从304增至312字节，自身栈832字节不变。反汇编逐指令核对
对象字节，五个调用绑定ELF原始CALL26重定位；打开失败CBNZ、大小读取CBZ、分支
目标及唯一SP恢复均核验。沿Result=0、72和0xffffffff的实际分支，成功是Write→Close，
失败只有Close；篡改分支或指令字节的对照会拒绝。

这次只编译对象，未完整链接新ELF、创建新固件recipe身份、打包或执行ARM。对象
源码保留旧候选生成头文件，仅作编译输入，不作为可部署新候选；此前91项完整
启动/退出观察没有在新完整候选上重跑，不能沿用为新链接验收。

## 封存、验证与继续入口

新增15项测试包含在156项相关回归中，全部通过、无跳过；7741个旧证据及本轮审查文件独立哈希核验通过。生产源码、旧工具/
runtime及封存哈希、三份实机票据均核验保持；SDK burst仍为failed_no_retry、
remaining=0、acquisition_enabled=false。工具使用python3.12，输出须指向新目录。

- [审查结果与源哈希](../private/analysis/A23-memory-log-guard-review-20261015/audit.json)
- [dormant SDK回放](../private/analysis/A23-memory-log-guard-review-20261015/dormant-sdk-memory.json)
- [30秒SDK回放](../private/analysis/A23-memory-log-guard-review-20261015/window-30s-sdk-memory.json)
- [保护版本机函数与替身](../private/analysis/A23-memory-log-guard-review-20261015/guarded-native.c)
- [隔离core.c](../private/analysis/A23-memory-log-guard-review-20261015/dormant/guarded/source/core.c)
- [对象分支证书](../private/analysis/A23-memory-log-guard-review-20261015/dormant/guarded/certificate.json)
- [审查封存](../private/analysis/A23-memory-log-guard-review-20261015/SHA256SUMS)
- [156项相关回归](../private/analysis/A23-memory-log-guard-validation-20261015/regression.txt)
- [独立核验](../private/analysis/A23-memory-log-guard-validation-20261015/validation.json)
- [验证封存](../private/analysis/A23-memory-log-guard-validation-20261015/SHA256SUMS)

下一步先将GetSize保护接入带新recipe身份的完整隔离候选，重做链接与原91项
生命周期观察；另可将SDK真实helper访问及明确的映射条件接入formatter完整回放。
保持生产源码和实机票据不变，不据模型成功放行USB测试。整线程栈、运行态TLS/
locale、重入/错误及USB根因仍待研究。

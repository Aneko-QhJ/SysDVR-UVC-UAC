# IOUSBHost transaction调用链与离线所有权原型（2026-10-12）

继续[请求与平台分派审计](HOST_DRIVER_FLOW_AUDIT.md)，已核对本机用户态framework提交、完成、
数据对象释放及内核中间层，完成单请求所有权组件和纯模拟验证。
当前调用链不经过旧UserClient的NotSent合并，可以作为保留更多内部状态的独立诊断backend。
这不改变控制器本身的错误汇总，也不恢复原始event CC或DATA PID；历史失败根因仍未知。
本轮USB0、SD0，采集状态及剩余次数保持原值，未添加`experiment.py`采集入口。

## 1. 本机调用链的确认范围

输入为macOS27.0.1/26A434的系统共享缓存中的IOUSBHost.framework，UUID
`B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B`；代码从`dyld_info -section_bytes __TEXT __text`
输出提取，起点0x197acad58，95236bytes。不能用“framework路径没有磁盘文件”推断实现不可读取。
482个函数边界的字节哈希及全文反汇编已保存。框架的历史运行版本尚未验证。

用户态关键路径如下。机器码地址均为当前缓存的unslid地址。

| 边界 | 当前机器码行为 |
| --- | --- |
| transaction异步API，0x197adae24 | 把version2传入共用内部方法 |
| 共用提交，0x197adaa68 | version1选selector0x17；version2选0x1c，经IOConnectCallAsyncMethod提交 |
| scalar数组，0x197adab08..0x197adab18 | endpoint地址、事务数组地址、数量、数据地址、数据长度、firstFrame、32bit transfer options、version，共8项 |
| 提交回调上下文 | async reference count3，包括回调函数及复制后的completion block |
| `__isochCompletionCallback`，0x197adada8 | 调用block并释放block；没有遍历或改写事务状态，没有改写整体IOReturn |
| `abortWithOption:error:`，0x197ad9f98 | selector0x15，传endpoint和abort option；没有用户block队列排空逻辑 |

已解析13个跨镜像stub，核对ObjC selector以及objc_retain、objc_retainBlock、objc_release、
IOConnectCallAsyncMethod、IOConnectCallScalarMethod等目标。辅助程序只读取自身加载代码，
不创建USB服务对象、不枚举注册表，也不执行所解析stub。

内核使用上轮同一份已核验kernelcache，14个目标函数反汇编及16个分派/方法表记录已保存：

| 边界 | 当前机器码行为 |
| --- | --- |
| selector0x17/0x1c | 方法表均指向`_hostPipeIOIsoch`，scalar输入数8；版本字段决定数组布局和完成路径 |
| `_hostPipeIOIsoch`，0xfffffe000b3a44a0 | version1映射count×24bytes，version2映射count×28bytes；异步上下文保存两个映射及原用户数组地址 |
| FrameworkClient虚表+0xa90 | transaction版`hostPipeIO`，再经pipe+0x548调用transaction版IO |
| pipe transaction入口，0xfffffe000b3d3d28 | 将用于旧frame兼容的额外参数置零，进入共用IO实现 |
| pipe+0x598 | `isochronousIoGated`；经请求+0x290准备交易，控制器+0x998入队 |
| ISO请求+0x290 | AppleUSBIORequest的transaction prepare；初始化status为Invalid，检查offset/requestCount范围 |
| 交易完成，0xfffffe000b3a776c | 结束映射操作并释放映射引用，经异步结果传出原整体结果和原用户数组地址 |

通用AppleUSBXHCI与T8112的+0x998都指向AppleUSBHostController::io。
这确认当前类的分派，不证明历史运行实例、全部平台路径或取消/重置时的具体控制器事件。
中间的事务prepare、pipe IO、完成边界没有旧UserClient那段NoResources/NotResponding→NotSent
转换或逐槽整体结果传播。控制器ISO finish仍可能用整体错误终结剩余交易，见上轮报告；
因此新API保留的也是驱动处理后的IOReturn，不是每笔交易的原始硬件事件。

## 2. 缓冲区和回调所有权

共用提交方法对data仅作局部retain，在成功返回前释放；completion block则由retainBlock复制，
失败提交时释放，成功提交时留给回调。不能假设framework一直持有data对象。
事务数组是裸指针，调用方必须保存其对应对象、禁止重用和改动，直至自己的完成处理结束。

SDK提供`dataWithCapacity:options:error:`（本机头文件标记macOS26.4起可用）：
数据可用None，事务数组建议KernelUserShared。返回IOBufferMutableData的length/capacity不能更改；
`setLength:`的实现抛出异常。其deallocator负责解除映射/归还缓冲区，因此提前释放有实际影响。
内核copyDataMemoryDescriptor/copyKernelMemoryMap还包含已有映射复用与普通用户内存映射路径，
不能将SDK的优化建议描述为所有普通NSMutableData必然失败。

完成由对象的串行dispatch queue处理。同步abort保证的内核I/O完成不等于用户completion block
已经处理并保存证据；框架abort方法自身没有执行该队列的排空。
后续实现应在同一串行队列维护请求状态，使用异步abort，等待真实完成处理。
若取消失败或回调缺失，保留所有权并停止，不自动释放、重投或重置endpoint。

## 3. 已实现的离线组件

[io_usb_host_transaction_owner.h](../host/io_usb_host_transaction_owner.h)及对应.m提供单请求组件，
接收已经存在的数据/事务缓冲区、串行queue和transport。真实pipe适配器的SDK签名已编译核验；
模拟测试只注入MockPipe，未实例化真实适配器，也没有任何设备匹配、打开或burst触发入口。

组件固定960笔×192bytes，事务数组26880bytes，raw184320bytes，明确的非零firstFrame，options0。
它记录submit开始/返回及callback到达的Mach ticks，复制整份raw和事务数组，并单独保留
未经修正的32bit overall。提交失败的NSError另记，不伪造为完成回调的overall。
时间记录仍是软件观测，不能当作总线125µs相位。

| 状态 | 所有权规则 |
| --- | --- |
| Prepared→Pending | 每个对象只提交一次；block持有owner及两份存储 |
| Pending→CancelPending | deadline只请求一次异步abort，不释放存储 |
| abort被拒绝→Retained | 保留abort error及缓冲区，禁止重新提交 |
| completion→Completed | 原样复制完整证据，再通知消费者；重复回调不覆盖首份证据 |
| 提交失败→Rejected | 保存提交错误和原缓冲区，不发起abort |
| Completed/Rejected且证据保存确认 | 才允许清除原数据/事务存储 |

回调指针与提交数组不一致时标记mismatch，不读取陌生地址；这不能证明自己的DMA所有权结束，
因此进入Retained并自持有这一个有界请求直到进程退出，拒绝保存确认后的释放。存储尺寸不符则拒绝创建对象。
本轮原型暂未完成证据写盘/读回校验；后续[离线证据链](IOUSBHOST_EVIDENCE_PIPELINE.md)已补齐
simulation写盘与独立分析。完整设备生命周期或detach仍待完成；消费者不得把“收到snapshot”
当作“已保存证据”，也不得把组件Completed状态当成严格传输通过。

再后续[离线会话审计](IOUSBHOST_SESSION_AUDIT.md)补齐可注入的生命周期/断开模型及所有回调事件
观察；真实SDK生命周期仍未执行。当前owner首份快照仍先复制，observer不会覆盖既有证据。

纯模拟验证覆盖错误帧actual192及raw仍保留、整体NoResources不转换、取消成功/拒绝后继续持有、
提交拒绝、重复回调不读已释放数组、不覆盖首份证据、提交期间的即时回调、外部引用消失后的
ARC所有权、陌生回调指针和错误存储尺寸。AddressSanitizer与UndefinedBehaviorSanitizer通过。
这些验证不计作USB传输或实机成功样本。

```sh
/usr/bin/clang -std=c11 -fblocks -fobjc-arc -Wall -Wextra -Werror \
  -fsanitize=address,undefined -framework Foundation -framework IOUSBHost \
  research/usb-ds-iso/host/io_usb_host_transaction_owner.m \
  research/usb-ds-iso/tests/io_usb_host_transaction_owner_test.m \
  -o /tmp/a23-transaction-owner-test
/tmp/a23-transaction-owner-test
```

## 4. 后续证据与实机边界

后续已完成提供字节的匹配/预检代码、simulation证据文件保存及独立验收器；真实打开是否成功、服务对象所有权、
HS端点实际配置、新API真实返回与取消完成时序，都需要实机证据。
新backend必须有独立标识、冻结包及停止机制，不共用旧采集次数，也不与旧backend混算成功率。

诊断目标是保留被旧接口合并的整体NoResources/NotResponding以及每笔交易的内部状态。
所有空槽状态照实保留，不先假设新API应与旧API一样报Underrun。
即使看到某种内部状态，也不能凭它恢复原始CC或认定历史根因。
后续有界方案需先核验新backend的空窗口，再独立评估fresh单burst；旧32轮成功不会替代它的验收。
当前未准备或执行这些步骤，A23设备补丁和采集阶段不变。

## 复现与冻结产物

[audit_io_usb_host_framework.py](../tools/audit_io_usb_host_framework.py)读取当前共享缓存及本地内核镜像，
导出framework文本、完整反汇编、函数字节哈希、内核函数及分派记录，拒绝覆盖已有输出。
[io_usb_host_framework_inspect.m](../host/io_usb_host_framework_inspect.m)仅解析当前加载代码的stub。
两者绑定当前版本；版本不符拒绝继续，不能直接用于另一个系统版本。

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/audit_io_usb_host_framework.py \
  --output /tmp/a23-framework-fresh \
  --objdump /opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump
```

有效冻结材料位于private/analysis/A23-IOUSBHost-framework-review-20261012-v2/，包含SHA256SUMS、
provenance、源码/SDK头文件哈希、模拟验证结果及反编译草稿。初版保留作过程记录；v2补强陌生
回调指针时的所有权隔离，避免把“保存了一份快照”当成自己的DMA已结束。
Ghidra只加载代码；陌生stub及尾调用会造成截断甚至串入其他函数，伪代码不作为独立证据。
关键条件以反汇编、真实stub解析和format8/cacheLevel0虚表解析核对。
6项新增解析/坏输入检查通过；原13项驱动工具检查仍通过；旧冻结材料及采集状态哈希不变。

# 主机请求结果、平台分派与新接口候选（2026-10-12）

继续[主机驱动审计](HOST_DRIVER_AUDIT.md)，已确认普通完成路径中的方向判定，追到正常ISO
结果的汇总与收尾，并核验T8112相关虚表。还找到一个可离线准备的新诊断方向：IOUSBHost
transaction API 的内核完成回调没有旧接口的错误合并；SDK布局和调用签名编译通过。
这不是可运行接收器，也不是已验证修复。根因、历史运行驱动身份和当时端口控制器仍未确认。
本轮USB0、SD0，无新采集入口，既有三次失败和采集次数不变。

## 1. 之前未命名的布尔值是内存描述符方向

`_PipeIOIsoch`（0xfffffe000b35d834）从IOUSBLib的7个scalar参数创建异步参数块。
最后一项为0时请求方向1，否则方向2；普通ReadIsochPipeAsync传0。
描述符返回自UserClient虚表+0xa00，解析为`copyMemoryDescriptorFromArguments`。
该描述符写入参数块+0x58；普通帧映射的完成函数从此处取对象，调用+0x1e8并比较返回值是否为1。

`IOMemoryDescriptor`与`AppleUSBHostClientBufferMemoryDescriptor`两张虚表的+0x1e8
均指向内核的`IOMemoryDescriptor::getDirection`：0xfffffe000c423874。
机器码读取对象+0x20的flags，返回低两位。SDK定义1为`kIODirectionIn`，2为Out，3为InOut。
因此该布尔值的准确解释是**描述符方向恰为In**，并非新增诊断、接收器开关或设备属性。

缓存描述符复用还检查方向位是否与请求方向相交，可能保留InOut描述符；不能仅凭Read API
就断言每个历史参数块里的实际方向都必为1。旧日志未保存这个内核字段。
对于direction==In的路径，内部状态0且actual<requested会变成Underrun；完整包则落到整体结果传播。

## 2. 正常ISO事件路径保留首个转换后非零的CC

以下是当前镜像的静态规则，适用于所核验的正常事件/收尾路径，不覆盖所有取消、重置、
外部`finish(int)`或平台特殊分支。

| 路径 | 机器码确认的行为 |
| --- | --- |
| ISO `update(event, time)` | 每笔交易写自己的CC转换结果，同时更新请求+0x2dc中的汇总CC |
| 汇总更新，0xb59ca18..0xb59ca44 | 已存CC为0，或已存CC经转换为成功时，才替换为新CC；一旦转换后非零，就保持它 |
| ring `transferEvent`，0xb5960b0 | 使用ISO虚表+0x318更新当前请求；通过空event更新检查已完成的请求 |
| ring `scavengeRequests`，0xb5962b8 | 完成请求移出队列，再经+0x2c0收尾 |
| 基类 `finish(event)`，0xb5781f0 | update确认完成后，转换请求+0x2dc的CC，通过虚表+0x160调用`finish(int)` |
| ISO `finish(int)`，0xb59cbe8 | 非零结果填入剩余交易并清零其actual；再调用基类收尾 |
| 基类 `finish(int)`，0xb5782bc | 经+0x1c0调用`AppleUSBIORequest::setStatus` |
| `setStatus`，0xb3e166c | 把传入32bit结果写入请求+0x278 |
| `AppleUSBIORequest::complete` | ISO准备时completion类型为2；该分支把+0x278整体结果和交易数组传给完成回调 |
| 旧UserClient完成 | 再执行上一轮确认的NoResources/NotResponding→NotSent及部分frStatus继承整体结果 |

表内短地址均位于0xfffffe0000000000地址空间。37个虚表槽解析见dispatch.json，
根chained pointer format8和cacheLevel0均实际校验；不把PAC编码直接当成虚拟地址。

成功事件可以更新尚未出现错误的汇总值，但后续成功不会清除已经保存的错误。
这与“最终收到16个正确包，却整体失败”相容；不需要假设接收器在成功回调后又制造错误。

对旧日志更强但有条件的约束是：如果执行相同普通兼容路径，完整有效槽显示E00002ED，
则该分支传入的整体结果也是E00002ED；它再被兼容层映射成overall E000400E。
在上述正常CC汇总模型中，CC4或36可产生这种整体结果；**只出现CC23、其余全成功**会汇总成
NoResources，不能单独解释有效槽E00002ED。其他收尾入口和历史镜像差异尚未排除，
所以这不是从历史日志恢复出的CC，也没有把历史失败认定为已证实的CC4。

## 3. “帧过旧”还有不同的软件路径

ISO `link(TD)`（0xb59a5e8）读取当前microframe及控制器提前量，检查明确指定的startFrame。
当某笔ISO交易的计划帧不晚于检查阈值时，它写当前时间、actual0和E00002EE（IsoTooOld），
并跳过对应TRB/交易。关键状态写入位于0xb59a94c；阈值比较在0xb59a83c..0xb59a840。

这与event CC23→NoResources、CC4/36→NotResponding是不同来源。
旧UserClient不把内部IsoTooOld直接合并成NotSent；其“其他状态”分支仍可能被整体结果覆盖，
所以**旧日志没有IsoTooOld也不能证明没有过旧交易**。同样，NotSent前缀不能直接当作这段
软件过旧检查的输出，更不能用前缀时长反推实际内核入队时刻。

## 4. 平台分派的确认范围

当前镜像中T8112类位于AppleSynopsysUSB40XHCI模块。
`AppleT8112USBXHCI`的以下槽与通用`AppleUSBXHCI`一致：

| 槽 | 最终实现 |
| --- | --- |
| +0xac8 / +0xad0 | AppleUSBHostController::currentMicroframe / referenceMicroframe |
| +0xb10 | AppleUSBXHCI::createRequestPool |
| +0xbf0 / +0xbf8 | AppleUSBXHCI::makeMicroframeNumber / generateRawReferenceMicroframe |
| +0xcd0 | AppleUSBXHCI::createIsochronousTransferRing |

通用createRequestPool调用的auth stub已解析到StandardUSB::getEndpointType；类型1分支创建
AppleUSBXHCIIsochronousRequestPool，虚表+0x1a8指向其allocateCommand。
对照中T8101确实覆写createRequestPool，说明不能把“没有名字含ISO的导出函数”当作充分证据；
此处以实际槽值和分支为依据。

这缩小了T8112上的分派不确定性，未确认运行实例就是T8112类。也没有完整追完时钟会话、
端口拓扑、控制器quirk或全部平台分支。历史测试的实际控制器身份仍需运行证据。

## 5. 可以先离线准备的诊断候选

本机SDK提供较新的`IOUSBHostIsochronousTransaction`及IOUSBHostPipe异步transaction接口。
它的28byte packed结构为status、requestCount、offset、completeCount、timeStamp、options，
与已逆向交易数组的布局一致。SDK的时间戳描述仍受中断延迟影响，不能当成125µs总线相位。

内核`AppleUSBHostFrameworkInterfaceClient::isochronousTransactionCompletion`
（0xb3a776c）释放/同步映射后直接传出原整体结果，没有旧UserClient的NotSent合并和逐槽
整体结果传播循环。其frame完成函数`isochronousCompletion`（0xb3a7668）也没有这段legacy转换。
这给出一个比继续只加用户态时钟更具体的候选：另建直接IOUSBHost transaction诊断backend，
保存每笔交易状态、整体状态、actual和时间戳，以区分旧接口合并的两类错误。

已完成的范围仅为当前内核完成边界核对，以及
[io_usb_host_signature_probe.m](../host/io_usb_host_signature_probe.m)的SDK编译检查：

```sh
/usr/bin/clang -std=c11 -fblocks -fobjc-arc -fsyntax-only -Wall -Wextra -Werror \
  -isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk \
  research/usb-ds-iso/host/io_usb_host_signature_probe.m
```

本报告阶段没有生成或执行采集程序。后续[接口审计](IOUSBHOST_TRANSACTION_AUDIT.md)已核对当前
用户态framework主路径，并完成单请求所有权/失败保留的模拟原型；接收器还需处理匹配/打开对象、
真实对象生命周期、证据文件保存与独立验收。必须先定义证据与验收，
再做实机验证。直接API也仍不是原始host event或总线分析器，不能据此承诺恢复event CC或DATA PID。
接口改变构成新backend，之后不得与旧backend混算成功率，也不得覆盖旧失败。

## 复现与产物

[audit_host_driver.py](../tools/audit_host_driver.py)新增可选`--module`/`--target`以扩展导出，
默认两模块/旧目标集合保持原输出；[audit_host_driver_dispatch.py](../tools/audit_host_driver_dispatch.py)
只读解析当前fileset和37个虚表槽，输出JSON。后者明确绑定本轮镜像中的endpoint-type stub，
版本不同或target变化会拒绝，不猜测另一份镜像的地址。

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/audit_host_driver_dispatch.py
```

本轮有效产物为private/analysis/A23-host-driver-flow-review-20261012-v2/：62份文件及SHA256SUMS，
包含4模块材料、目标反汇编、近似伪代码/脚本、分派核对、getDirection机器码、SDK probe及源工具快照。
native-audit.json另记录新框架两处完成函数的完整字节范围和哈希。
Ghidra仍仅加载代码，关键条件用反汇编和虚表核对，类型推断及不可识别的尾调用不作证据。
13项相关检查通过，覆盖fileset偏移/损坏输入、拒绝覆盖、目标函数实际导出、多模块默认筛选、
pointer格式/cacheLevel/范围及stub指令识别。
复核时发现初版扩展导出将筛选参数覆盖为空列表，漏掉了目标函数材料；修正后重建v2，
默认输出逐字段与上轮冻结audit.json一致。初版保留作过程记录，由v2的provenance明确替代。
上轮28份证据和采集状态保持原哈希。

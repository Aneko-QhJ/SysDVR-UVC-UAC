# A23 联合预检与 trace 预算候选（2026-10-14）

独立候选补齐两个边界：**BURST在ISO状态/payload改写之前同时检查ISO和ACK范围；每个
已就绪SETUP在开始记录/处理之前预留最坏17条trace空间。** 前置STATUS timeout现在保持
seq0/ISO post0/旧pending1；完整三步会话仍为6槽/66条。185项native场景与327项相关Python
回归通过ASan/UBSan，无跳过；默认窗口关闭与30秒样例各完整链接9对象libnx ELF。

本轮没有执行ARM ELF、打包/部署、访问USB/SD或修改生产、旧runtime/封存与三份票据。
burst仍failed_no_retry/remaining0，根因未知。上一阶段
[会话审查](A23_GUARD_SESSION_DIAGNOSTICS.md)及其“先ISO post后拒绝ACK”“带丢失正常导出”
结论是旧候选的历史事实；新候选的行为和recipe另封存。

## 联合范围预检

[构建工具](../tools/build_a23_bounded_candidate.py)复制封存guard候选，保留原范围/身份账本、
原子stop与一次性清理授权，只在新输出树接入
[admission API](../device/ep0_request_admission.h)和[实现](../device/ep0_request_admission.c)。
新recipe绑定输入、旧guard/session manifests、编译器/libnx.a及窗口配置。旧source/recipe不覆盖。

BURST沿原速度/busy判断继续，到首次memset g_isoStatus之前调用AdmissionBurst：
检查g_isoBuffer的实际length及_ctrlBufferFor(iface)的零長ACK地址，统一要求剩余两个永久
身份槽。两个检查之间没有copy/post；还拒绝本次拟用ISO范围与ACK点重叠。通过只表示
当前账本未见冲突，不能保证后续post返回成功、服务终结或ACK到达主机。

- 前置STATUS IN timeout：旧control占用阻止整个BURST的新ISO改写/seq/post；旧pending不解除。
- 注入未知ISO、非零control OUT、零长control地址：均在ISO改写/post前拒绝。
- 仅余一个永久身份槽：同样在改写/post前拒绝；两个检查不重复消费四个槽。
- 拟用ISO/ACK地址重叠拒绝，位于ISO半开区间末端的相邻ACK点允许。零长身份不表示payload字节损坏。

上述直接边界场景给ISO buffer填入0xA5，拒绝后完整payload仍原样；正常三步会话与两个
额外STATUS的服务路径保持。实际DMA/借用是显式模型假设，不能据此确认实机损坏或seq0根因。

## 每个就绪请求的记录预算

实际[ProcessRequests](../../../source/uvc/uvc_device.c#L1795)包含while(serviced)后续SETUP循环，
一次调用可以处理很多请求。仅在函数入口按三接口预留固定空间不足以覆盖该循环。
新_serviceSetup在原eventWait/trace_poll确认就绪后、trace_request/event clear/GetSetupPacket
之前检查剩余17条；quiet poll不占记录，也没有新增USB查询。预算不足时保留未clear的
SetupEvent、设置capacity fault并atomic stop，后续接口与while循环直接跳过。

17条是对冻结源码/插桩的逐分支上界，按单个已就绪接口请求计算：

| 路径 | 最大记录组成 | 最大条数 |
| --- | --- | ---: |
| VC/VS标准GET或数据类GET/SET | event/clear/setup3 + 最多两个6阶段控制helper | 15 |
| ISO STATUS | 基础3 + ISO enter/status snapshot2 + 两个控制helper12 | 17 |
| ISO FRAMES数据回复 | 基础3 + ISO enter1 + 两个控制helper12 | 16 |
| ISO BURST成功 | 基础3 + ISO enter/speed/sequence/post4 + IN helper6 + ACK1 | 14 |
| 忽略/guard/无数据ACK/CANCEL | 早退或单helper/ACK；原ISO poll不append trace | 不超过17 |

单请求End检查实际增量、dropped/invalid及active阶段；违反上界永久拒绝并停止。此检查
发生在处理之后，**不能撤销已发生的USB调用**，因此未来增加trace阶段或handler时必须
重新审查预留值和所有source anchors。native直接回放最大ISO STATUS17条，VC/VS class
完整分支上界来自当前实际源码静态审查，未将原native class stub称为真实class回放。
真实ARM树包含完整实际class handler，并成功编译/链接。

wrapper只在Enter成功且admission Begin通过后调用原处理函数；Begin为可能的断开状态
记录检查至少1条余量，并拒绝已丢失/invalid/已停止/fault状态。owner fault在请求End立即
触发stop；_serviceSetup以及原后续while都检查stop。原调用已经在等待时不会被中断，
原有同步控制helper仍可能等待完成；停止延迟没有实机上界。

## 行为与回放结果

| 输入/条件 | 新候选结束状态 | 正常导出 |
| --- | --- | --- |
| 完整STATUS/BURST/STATUS，原poll已观察ISO终结 | 6槽/66条，pending0，dropped0 | 放行 |
| 三步会话再2次STATUS | 10槽/112条，dropped0 | 放行 |
| 三步会话再3/5/6次STATUS | 第3个额外请求在admission拒绝；仍10槽/112条，dropped0/fault1 | 拒绝 |
| 连续5次STATUS | 10槽/115条，dropped0 | 放行 |
| 连续6/8/9次STATUS | 第6个请求在admission拒绝；IN/OUT仍各5次，10槽/115条，dropped0/fault1 | 拒绝 |
| 单次ProcessRequests内注入100个可继续投递的STATUS | 完成5个后返回，仍有注入请求未投递；115条，dropped0 | 拒绝 |
| trace前缀已用111条，再单接口STATUS | 17条正好填满128，无丢失 | 边界回放不导出 |
| trace前缀已用112..128条 | 就绪请求或入口拒绝，现有记录不变、无data/status post | 边界回放不导出 |
| 处理外故意append200条trace | dropped138/fault1，保留诊断 | 拒绝 |

统一按最坏17条预留是保守策略：即使某接口只是忽略广播、实际只需3条，也可提前拒绝。
拒绝之前不会读取SETUP，因此拒绝请求的实际8byte没有记录；已有EP0DIA1的capacity reason4
可来自trace或身份容量，独立admission计数当前只留在内存/native JSON，不增加旧wire字段。

**新Finish在成功身份交接后将dropped/invalid转为永久fault，拒绝正常capture。** 同一批
fault/pending诊断仍按原EP0DIA1独立解码，不授权清理。故意在admission外写满的测试也不能
绕过最终导出；没有清fault、清账本、强制cancel/close或主动查询迟到报告。

## 验证与封存

[15项Python检查](../tests/test_a23_bounded_candidate.py)覆盖：联合预检、健康会话保持、
容量前停止、129个已用记录偏移、持续followup、未知IN/OUT/零长、拟用范围别名与相邻点、
槽预算、上界违反/外部溢出、停止交接、旧控制复用回归、诊断/身份错误及完整ARM链接。

- 28项实际VideoStreamThread回放，其中只有故意绕过门槛的trace-overflow丢记录，且正常导出拒绝；其余全部dropped/invalid0。
- [138项边界回放](../tests/ep0_request_admission_test.c)：129个偏移+9个特殊场景；其中元数据/线程/USB结果均注入，无DMA/HOS机器码执行。
- 19项既有实际control buffer场景再次回放，copy重叠0/同地址repost0。
- 19份独立diagnostic与5份正常ownership capture独立解码；仅native写电脑新目录，未将诊断sink接入ARM main。
- 327项相关回归无跳过；默认窗口关闭与30秒配置各链接9对象完整ELF，未执行、打包或部署。

`dormant`只表示时间窗口关闭，容量/范围拒绝仍能请求stop。这些预算只覆盖当前模型的
简洁会话，不证明真实枚举或VC/VS Probe/Commit协商后仍有足够空间；不能视作实机候选已验收。

- `private/analysis/A23-bounded-candidate-review-20261014`：185项native场景结果、生成源码/二进制、
  两套完整ARM源码/9对象/ELF/map/recipe、独立捕获与解码、audit和SHA256SUMS。
- `private/analysis/A23-bounded-candidate-validation-20261014`：327项回归、源码与生产快照、
  旧封存/三份票据/文档链接核验、独立validation与SHA256SUMS。

```sh
python3 research/usb-ds-iso/tools/build_a23_bounded_candidate.py --output /private/tmp/A23-bounded-review-new
```

输出必须为新目录。当前原main仍在Finish失败后sleep，无设备诊断文件路径；下一步电脑
在新候选接双join成功且Finish拒绝后的独立诊断sink，保存后继续保留资源，不走正常导出/
清理授权。需单独核对6656byte诊断容量（旧capture sink上限6640）、路径/一次性创建与读回、
commit失败、guard/admission诊断字段和初始化失败阶段。生产/旧wire保持封存。

真实DMA终结、线程/调度/成本、ID重用、SD持久性/来源认证及异常退出仍未验证；剩余实机
次数0，根因未知。不要把本次候选主动保持seq0的注入拒绝路径称为首次SDK burst的停止原因。

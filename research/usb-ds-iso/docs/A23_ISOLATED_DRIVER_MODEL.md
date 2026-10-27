# A23 完整 driver 的隔离数值时钟回放（2026-10-20）

后续：[callback/deadline/profile故障回放](A23_DRIVER_FAULT_MODEL.md)新增46场景与60测试通过；可见profile变化拒绝，ABA反例仍通过，不认证原子读取或真实SDK。以下保留原阶段。

接续[driver副本与时钟桥](A23_QUIET_DRIVER_COPY.md)，相同候选现已在裁剪后的 SDK-shaped 模型中链接并执行。19 个场景的优化版、UBSan 版及457来源搬移重建一致；新增20及旧driver副本20/quiet20项，共60测试无跳过通过。此次结果限定于注入模型，生产采集仍关闭。

## 执行范围

`tools/a23_isolated_driver_model.py` 固定36个父来源摘要，生成可审查的源码。保留driver候选、paired provider/lease、budget、owner、纯descriptor校验器及独立journal；真实SDK factory、ExistingPipeTransport、LocalMachClock和session执行器不在实现构建输入中。SDK头文件仅提供类型/ABI声明，SDK-shaped标签与provider类名不证明真实SDK对象。

旧TwoClock整段替换为数值clock，显式注入role/instance/ratio。owner的三个Mach读数改为独立原子计数器；它与driver时钟没有认证映射。broker、实际context读取、真实SDK operations及固件没有构建或运行。driver的deadline、emit/stop/guard、receipt/result部分仍逐字节保持；原driver文件未修改。

每版仅链接Foundation及系统运行库；在执行前保存otool链接库、nm未定义符号和完整符号表，并拒绝IOUSBHost/IOKit库、真实factory类及明确的Mach/context/IOService调用符号。这是本次实现输入与链接检查，不是OS能力隔离证明；Foundation和系统库内部行为没有被沙箱证明。

## 观察结果

- 正常1/1完成两轮保存、静默等待及receipt。SDK-shaped STATUS/frame样本均明确标记 `injected_fixture=true`，两轮3072有效字节、完整raw/transaction快照、独立bundle seal及receipt snapshot摘要核对通过。
- 2/3比例、374999999 tick仅有249999999又2/3ns，仍等待且不尝试receipt；同一driver再增加1 tick才完成250ms。375000001 tick亦通过。
- 未声明协议、owner角色、零实例在读取ticks及提交前被拒绝。quiet起始tick0、倒退、溢出、ratio/domain/instance变化、相同标签的新对象均终止。
- observation_complete append失败终止；append成功后注入旧ISO回调使post-guard失败，事件存在但settled及结束tick仍未提交。
- 完成后的旧回调撤销资格并保留历史quiet_end诊断；receipt保存后旧回调使receipt stale且saved=false。正常不足250ms的场景保持等待，不重试提交。

`clock-profile.json` 是fixture生成的独立sidecar，保存初始/结束profile和注入端点；Python Fraction以精确比例校验等待边界。原事件格式未扩展，sidecar是注入声明，不认证实际来源、对象地址或原子快照；旧分析器未被重跑或修改。对象替换场景仅在fixture中通过KVC替换driver内部clock，以触发同标签/不同对象的拒绝路径。

## 失败记录与重现

r1在第五个场景的拒绝结果读取处触发dispatch队列断言，崩溃栈定位到队列外的lease.result；r2仅将该读取放回串行队列，19场景两版通过。r2测试中另有一项把链接命令的 `-framework` 下标写错，19通过/1失败；r3修正测试下标并格式化renderer pin表，生成实现与r2完全相同。三版封存与失败日志均保留。

r1/r2/r3及搬移合计编译7份隔离模型可执行文件、14个compiler jobs；启动7次模型进程（含r1失败）及6次无参数拒绝入口。最终60测试与三种只读CLI不额外执行原生模型。正确/错误/缺失pin返回0/2/2。搬移回放的Python审计钩子记录原checkout与/Volumes打开0；编译器和原生子进程不继承此钩子，执行命令已检查使用搬移输入。

最终review：`private/analysis/A23-isolated-driver-model-review-20261020-r3`，1207成员，摘要 `a9083bb831b7512df918dc7e3356a952ca2947fa1587659704c171e14fb2a589`。

验证：`private/analysis/A23-isolated-driver-model-validation-20261020-r1`。收口：`private/analysis/A23-isolated-driver-model-closeout-20261020`，包括457来源、票据/文档前后快照、23保护项及账本摘要。

原452来源、冻结driver、真实49/65、账本、失败修复owner和23保护项保持。65已回收，remaining0；81..112只是模型数值，未正式保留/发行。USB、SD、真实SDK对象、实际context刷新和设备包改动均0。

下一步继续离线扩充callback/deadline故障及profile读取中途变化的完整driver回放，核对sidecar与事件材料的消费边界。profile ABA/读取原子性、owner/driver域映射、真实SDK runtime、现场quiet/drain与生产permit仍未认证。

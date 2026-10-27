# A23 driver隔离副本与时钟桥验证（2026-10-20）

后续：[完整driver隔离数值时钟回放](A23_ISOLATED_DRIVER_MODEL.md)已在裁剪的注入模型中执行相同候选，19场景与60测试通过；真实SDK/现场时钟与生产许可仍未认证。以下保留原阶段。

接续[独立quiet轮询候选](A23_QUIET_POLL_CANDIDATE.md)，本阶段生成完整Objective-C driver的隔离补丁，编译原版和候选对象文件，并执行只依赖Foundation及既有C算术helper的时钟桥fixture。完整driver、旧broker及SDK-shaped模型均未运行。

## 可审查的补丁

`private/analysis/A23-quiet-driver-copy-review-20261020-r2/work/driver-copy.diff` 给出完整差异；候选位于同目录的 `candidate/source/research/usb-ds-iso/host/a23_two_epoch_sdk_driver.m`。

补丁采用冻结driver摘要 `4f7f46345f1dbadf12b02bcf8c2322caacde33a63addd219976c9b942bfe8797`，每个替换锚点必须唯一。候选推导由 `a23_quiet_driver_copy.py` 验证；原文件首行的旧derivation工具说明描述父实现，不能作为此候选已通过旧生成器的证据。

- 初始化时要求显式的injected-driver clock协议、非零实例和有效ratio，profile预检不读取ticks。
- `epochs_saved`事件及guard成功后捕获quiet起点，保存ticks、ratio、逻辑实例与进程内对象身份；tick0仍按未开始sentinel拒绝。
- quiet结束点再次捕获，先校验同一对象、实例及timebase，再调用精确minimum比较；事件append→post-guard→settled顺序保持。
- deadline方法、emit/stop/guard方法和requestStop/receipt/result部分逐字节相同。没有改动原文件或设备包。

候选摘要为 `576b95ed175bc1c25409716a2e8c8bb8a77a78e6c62decd8854036da20589a6b`。对象文件只证明编译通过，不证明完整driver链接、初始化或运行行为。新的clock profile只保存在内部状态中，如何导出独立可核验的事件材料仍需在后续回放方案中处理。

## Foundation-only桥

新增头文件 `host/a23_quiet_driver_clock_candidate.h` 不引用IOUSBHost、IOKit或Mach时钟。fixture使用纯数值clock，拒绝未声明协议、缺失selector、owner/supervisor角色、零实例/ratio和观察到的profile变化。除逻辑标签之外，也要求起止样本来自同一进程内对象；两个对象复用同一逻辑实例不能通过。

27个场景在优化与UBSan版本中一致：包含2/3 short/equal/after、tick0与driver sentinel的区别、倒退/溢出、profile在两次采样间或采样过程中变化、对象替换、缺失selector和空指针/输出重置。原tick0算术桥仍可计算，但driver补丁单独拒绝quiet起始0。

ABA场景中，mock在一次nowTicks内部改变ratio再恢复，两次profile读取相同，因此捕获仍可能通过；`clock_profile_reads_atomic=false`。对象地址匹配和显式标签也不认证底层时钟来源或生产timebase。

新增20项、旧quiet20项及旧算术18项共58测试，无跳过通过。452来源搬移后重新编译对象和两版桥，补丁、保护方法摘要、27个结果及回放方案一致；正确/错误/缺失pin的只读CLI返回0/2/2，不执行原生程序。

首轮r1失败来自fixture将C逻辑表达式编码成整数1而非JSON boolean；严格校验已拒绝。r2仅在fixture中显式转换为BOOL，保留r1部分构建及失败日志。r1/r2/搬移合计编译6个driver对象文件、5份Foundation fixture，16个compiler jobs、9次fixture进程执行。driver对象没有链接到任何被执行的程序。

## 完整回放的边界

已检查的旧 `TwoClock` 调用mach_timebase_info和mach_absolute_time，`advanceNS`依实际timebase换算；broker还读取实际context并串接verifier/模型账本。旧native构建列表包含真实SDK factory所在的 `io_usb_host_sdk_adapter.m`，其中存在initWithIOService路径。因此本阶段没有直接复用其执行入口。

`work/replay-plan.json` 记录下一阶段九类回放场景及四项缺口：全链换用纯数值clock、明确排除真实SDK factory、确定profile事件导出/分析器兼容方案、保留owner与driver域间无认证映射的边界。当前Foundation fixture没有链接driver对象或这些factory，只链接Foundation和C helper；编译/子进程不继承Python文件审计钩子，不能声称系统能力隔离。

## 封存状态

- 最终审查：`private/analysis/A23-quiet-driver-copy-review-20261020-r2`，464成员，摘要 `7ac919f74b1cf11c7690b359df820472a630f36ddf5e63b51b6294b62dc1683a`。
- 初轮部分构建：`private/analysis/A23-quiet-driver-copy-review-20261020-r1`，摘要 `7938b735798a8a3c55da499b7d22713c246cb898a2bf5b259bfad1d5e6fa69e7`。
- 验证：`private/analysis/A23-quiet-driver-copy-validation-20261020-r1`，含测试、搬移重编译、对象类型/链接依赖、源观察和失败记录。
- 收口：`private/analysis/A23-quiet-driver-copy-closeout-20261020`，含452来源、票据/文档前后快照、23保护项及账本摘要。

原447来源、冻结driver、时钟候选、真实49/65、账本及失败修复owner不变；仅增加5份头文件/fixture/renderer/audit/测试。票据仍为65已回收、remaining0，81..112未保留，生产采集关闭。

本轮没有查询实际context/timebase、创建真实SDK对象、访问USB/SD、启动生产receiver、执行完整SDK模型、构建固件、改动设备包或正式发行/保留。下一步离线替换旧fixture中的TwoClock，并裁剪真实factory构建输入，再定义可执行的隔离回放范围。

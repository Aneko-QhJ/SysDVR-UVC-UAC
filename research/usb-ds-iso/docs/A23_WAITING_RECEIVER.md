# A23等待接收器构建与启动门禁（2026-10-15）

后续实施见[等待日志纳入EXE3收集主结果](A23_WAITING_COLLECTION.md)：24组材料与94项
相关回归通过；下一项回到V3实际线程/TLS/logger/整链栈成本。本页保留此前阶段语境。

已在[隔离入口组件](A23_WAITING_ENTRY.md)之外补齐独立接收器、冻结构建校验及单次消费
工作流。114份源码从冻结树严格编译；12组接收器循环注入场景、17项新增检查与此前58项
相关回归全部通过，共75项、0跳过。新构建记录为`offline_build_ready / remaining=0`，
没有签发器，也没有复用原失败票据。

接收器仅运行描述、文件校验和无效许可拒绝路径；有效许可的真实acquire从未执行。
真实IOKit/SDK操作、USB/SD、设备部署均为0，首次SDK超时根因仍未知。

## 构建与文件校验

[构建器](../tools/build_a23_waiting_receiver.py)冻结此前98份研究输入、新增9份文件及
七份生产输入，共114份源码。分别对接收器与注入fixture严格编译14个原生单元；
接收器使用O2，fixture使用ASan/UBSan。旧源码、旧工作流及设备V3候选保持原样。

构建生成只读JSON字节绑定，随[原生校验器](../host/a23_waiting_build_guard.m)编入接收器。
绑定包含源码绝对根目录、完整源文件摘要、固定接收器描述和V3预期recipe：
`a7aed8c72e3334c083963fb734e2e62fc3d6ca5f612a4914365fd6a2388ca850`。
这只是下一次候选的预期标识，没有认证任何实机部署或EXE3的物理来源。

Python与接收器分别检查当前源码、冻结源码、构建清单/COMMITTED、文件库存、描述文件及
接收器摘要；原生实现还比较清单与编译进接收器的绑定。改源码、冻结文件、metadata、
二进制、增加文件、符号链接、部分清单或旧schema均被拒绝，外层重新计算摘要不能替代
这些检查。迁移源码根目录需重新构建。

校验器显式排序UTF-8键，解决Foundation的SortedKeys对文件名标点排序与Python不同的
问题；规范JSON往返比较同时拒绝重复键及非规范字节。文件读取有大小/库存上限，并拒绝
符号链接和非普通文件。构建记录保存编译器摘要及SDK路径，没有冻结整个系统框架环境。

| 接收器入口 | 已验证的行为 |
| --- | --- |
| describe | 只输出固定计划，不构造设备对象 |
| check-build | 只核对文件，检查冻结输入与当前工作区 |
| check-consumed | 再核对独立的已消费receipt，不创建核销文件 |
| acquire-once | 文件核验及进程核销成功后才进入通知/SDK路径；仅测试了拒绝路径 |

## 三处单次约束与等待期间复核

[新工作流](../tools/workflows/capture_a23_waiting_receiver.py)要求显式提供新记录，没有默认
实时票据路径。只有新schema/backend、严格整数remaining=1、acquisition_enabled=true，
并具有绑定该构建/接收器的独立验证封存，才可能进入消费路径；没有签发或自动续期功能。
实际候选为0，dry-run只读，真正启动会在建立锁或run目录前被拒绝。

三处约束分别是：外层记录在启动子进程前持久化消费为0；接收器在任何通知端口、
IORegistry或SDK操作前独占保存`WAIT_PROCESS_CLAIMED`；选择设备后、打开SDK前再独占保存
`WAIT_RECEIVER_CLAIMED`。失败不删除核销标记，不重新选择，不重新启动。

新的绑定permit在选择设备时重新核对当前/冻结源码、构建和原receipt，检查进程核销中的
摘要仍与启动时一致；SDK核销完成后再复核一遍。这样，等待期间改源码或换UUID有效的
receipt也不能继续打开SDK。文件检查是有界顺序观察，不能当作对所有外部文件修改竞态
的原子认证；摘要完整性也不能替代用户授权或物理来源认证。

## 调度、退出与保留

[循环组件](../host/a23_waiting_receiver.m)只在选择日志的真实持久回执成功后准备资源。
准备和start在不同tick调用中执行，[新main](../host/a23_waiting_receiver_main.m)用同一
串行队列的不同timer调度轮次推进，给已经排队的SDK断开通知处理机会。该边界不能证明
所有真实异步通知竞态都已消除。开始SDK请求后不再pump等待通知。

主机被动等待预算120秒、轮询10ms；它们不延长设备V3的30秒窗口，也不替代原SDK的
16ms控制、ISO及退出预算。等待检查不能打断正在阻塞的IORegistry调用。

SIGINT/SIGTERM转为退出请求。准备前或准备后、start前的退出/断开阻止控制请求；已开始
的未完成I/O由原协调器保留，不强制释放。外层130秒观察超时或wait错误会保存PID和
`unresolved_no_retry`，留下接收器运行，不kill/terminate，不封存仍在变化的host目录。

完整关闭后，工作流核对等待日志、SDK记录、最终checkpoint与进程退出码，再保存结果和
封存；损坏、部分或矛盾材料保留为失败。receipt写入失败也已经消费次数，保持0且不能
重试；此时记录可停在consumed，而不是冒充未执行许可仍可用。

## 验证与封存

[原生fixture](../tests/a23_waiting_receiver_fixture.m)的12组循环包括正常、等待前/等待中/
准备后退出、两次队列调度之间的断开、等待过期、旧实例/模糊选择、未完成ISO/控制以及
运行中退出/断开。等待前收到退出时没有完整begin记录，原始失败前缀保留，独立核对器
明确报告不完整，不把它洗成完整关联。

[17项新增检查](../tests/test_a23_waiting_receiver.py)另外实际执行文件核销，验证重复核销、
进程/SDK两份许可的绑定、等待期间输入变化、九类错误receipt、六类构建损坏、启动前
消费、启动/持久化失败、超时不杀进程，以及五类矛盾/部分结果。所有prepared/消费样例
均在临时目录，工作流的Popen被注入替代；没有启动有效许可的真实接收器。

[审查工具](../tools/audit_a23_waiting_receiver.py)产生：

- `private/analysis/A23-waiting-receiver-review-20261015`：220条manifest；其中接收器构建120条。
  审查manifest SHA256：`92b4f8ca86a13e4ab7a320f745e68cbd3f5bfc4ab0f8265f9a38dfd4ce845592`。
- `private/analysis/A23-waiting-receiver-validation-20261015`：9条manifest，75项检查全部通过。
- 新离线记录位于审查目录的`offline-record.json`，remaining严格整数0、acquisition_enabled=false。
- 此前入口334/验证9、主机对接257/验证9、V3候选504/验证9及原失败run17条复核一致；
  旧98份输入、七份生产源和三份实时票据摘要保持。

## 后续研究路径

下一项把等待日志核对纳入EXE3收集主结果，保留损坏字节、失败回执和物理来源限制；
随后收敛V3实际可达线程、TLS/reent、栈及日志错误/重入成本，再形成一次有区分力的
诊断方案。当前主机门禁验证不能代替设备执行窗口、运行成本或USB成功的实机证据。

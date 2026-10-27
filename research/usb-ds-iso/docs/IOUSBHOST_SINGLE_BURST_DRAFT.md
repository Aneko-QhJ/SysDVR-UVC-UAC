# IOUSBHost 单次 burst 离线诊断草案（2026-10-12）

已定义独立候选计划、字节验收和失败停止模型。它只有离线plan/candidate命令，没有registry打开、
控制请求执行、捕获或凭据写入功能。硬件入口关闭、剩余次数0，不修改已冻结无TD证据或A23设备文件。
新工具io_usb_host_burst_draft.py只检验提供的Mock字节和状态模型，不能证明实机生命周期。

## 固定目标与预算

| 项目 | 草案 |
| --- | --- |
| 环境 | A23/fresh启动/HS/alt0/interface2/EP83/ISO/bInterval1/MPS256，UAC/PCM禁用 |
| Host ISO | 960×request192，options0，firstFrame=currentFrame+64；最多一次提交，无repeat |
| Device burst | 一次41/54/value1/index2/length0，16×192bytes，seq1..16；最多一次尝试，无设备cancel |
| STATUS | before/after各一次c1/51/0/index2/168；不循环轮询，不用frames53 |
| 软件预算 | query≤2ms；sample begin至最终enqueue检查age≤16ms；enqueue调用≤8ms；enqueue返回至trigger检查gap≤8ms |
| Trigger请求预算 | 拟请求异步控制timeout16ms；预计trigger end age≤48ms，64ms提前量中的16ms保留为假设余量 |
| 后续窗口 | 拟沿用一次ISO的2s截止、退出等待1s；不能用关闭后250ms监视证明排空 |
| 政策 | 空槽0为单次无TD观察派生的候选规则，verified=false；baseline_accepted/allow_next_burst仍false |

age必须覆盖query；16+8+8+16=48ms只是软件上限组合，不是线缆截止时间或已验证SDK调度余量。
拟用enqueueDeviceRequest异步入口，显式timeout0.016秒，避免同步控制阻塞处理ISO回调的队列。
SDK签名通过clang -fsyntax-only编译；未运行该函数、未链接可执行器，实际超时粒度和完成时序未知。
特别不能使用timeout0（SDK规定永不超时），不能凭参数0.016就称16ms硬截止已成立。
不套旧backend的40ms等待，也不从120个成组时间戳推断真实总线服务位置。

## 触发与持有顺序

1. 核验唯一设备及配置、原始fresh IDLE STATUS，原文持久化；失败不提交ISO。
2. 采样frame/timebase，记录固定firstFrame，最终预算检查后只提交一次ISO。
3. 仅在enqueue成功、journal正常、无退出/断开、owner尚未观察到completion且未触发时评估trigger。
   在真正控制调用前持久化并消耗唯一trigger尝试；持久化后重新检查时钟及owner状态，不自动补发。
   owner的Pending只表示软件未见自己的回调，不能证明内核尚未完成；拟实现须在同一串行队列处理事件。
4. 触发enqueue返回值与控制completion分开记录。timeout/提交错误不能推出设备没有TD，也不能重试。
   ISO callback若早于trigger检查则停止且trigger0；若在已发起控制后到达，只记录顺序和原始结果，不重复控制。
5. 拿到自己指针的ISO callback后复制全量raw/transactions，再读一次after STATUS，保存并读回验核核心证据。
   主机存储可否释放按自己的完成及commit/ack判断；SDK interface还须等待已发起控制的completion结束。
   ISO完成且已commit也不能关闭仍有control_pending的interface。
6. 出错停止。没有自己callback、陌生指针、写盘失败或未知所有权继续持有；Pending且服务在场最多一次host abort。
   abort拒绝/已尝试/断开时不再abort，不调用device cancel/reset/seize，不重投、重开或开始第二个窗口。

本轮模型以输入布尔状态及计数检查上述决策，尚未实现串行执行器、trigger日志绑定、真实DMA/SDK排空。
模型允许close只是建议的本地条件，不是实际SDK销毁已获证明。保存失败证据时也不能把stop消除后重新触发。

## 独立验收维度

| 维度 | 候选要求及边界 |
| --- | --- |
| 数据 | 恰16个连续active槽，每槽actual192；ISO1、seq1..16及整包字节正确；其余raw为0 |
| Active native | 16个有效槽status0；正确字节不能抵消非零status |
| Empty native | 944槽actual0，按完整原32bit值计数；候选期望0，Underrun/NotSent/未知值保留且候选检查失败，不转换成功 |
| Overall/所有权 | overall0、单次自己的callback、无Invalid/timeout/foreign/duplicate；完成不等于总线证明或排空 |
| Device | 原始before fresh，after seq1/state2/speed3/requested=transferred3072；唯一正URB/report ID一致，report_result0 |
| ISO7与完整日志 | A23/HOS/BuildID/runtime安装，唯一submit/timing/终结；bitmapffff、actual3072、terminal1、16包序列、event/tag/control/context关系按既有独立审计 |
| 控制绑定 | 主机原始before/trigger/after及各返回/完成绑定；device日志预计3组接口0/1广播，不把标签当请求ID，无额外vendor控制 |
| 时间 | host原始frame/入队/trigger/control完成/ISO callback记录；device 19.2MHz trigger/post/ack分别保存，不跨时钟直接相减 |

本轮candidate工具只覆盖模拟bundle的前三项及已保存owner callback/overall信息；device/trigger绑定
始终false，不将Mock包通过变为完整burst观察或政策接受。
未来设备after仍Pending/Retained、日志缺失或ISO7关系不成立时保存失败证据停止，不发第二个STATUS补齐。
空槽error而payload正确、active error而payload正确、overall error而payload正确分别报告。
137项相关Python回归全部通过、0跳过，新增11项包括预算边界、inline callback、触发尝试已消耗、
断开/取消/陌生指针、control仍Pending、有效数据不能掩盖native错误、残留raw及hardware重标记拒绝。
硬件/capture/repeat CLI三条路径均exit2；异步控制签名仅编译，USB/SD访问0。

## 后续电脑工作与实机缺口

接下来可离线实现可注入的异步burst执行器/日志格式，保存trigger enqueue与completion独立证据，
测试控制与ISO双完成的全部顺序及释放；核对控制timeout换算/时钟单位，并实现新burst collection独立审计。
空槽政策、trigger时序预算、callback/DMA排空、原生错误与device事件关联仍需明确证据边界。
这些完成后才评估独立有界实机方案；本次不产生硬件凭据，不以旧32轮成功替代新backend证据。

冻结目录：private/analysis/A23-IOUSBHost-burst-draft-20261012-214030
包含plan、模拟候选、生命周期决策、136项初版及137项最终回归、签名编译/CLI拒绝记录和源码快照。
所有MOCK_ONLY材料不计实机样本；原始无TD run/collection和语义重审原件保持不变。

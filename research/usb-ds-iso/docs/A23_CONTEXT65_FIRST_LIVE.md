# 序号65首次实测与设备回收（2026-10-18）

后续：[多突发准入与两轮协调器模型](A23_MULTIBURST_ADMISSION.md)已完成离线审查；未发新测试、未改当前设备包或本次65记录。以下保留实测与回收结论。

本次SDK初始化成功，唯一一次ISO提交和BURST(65)完成，主机收到65..80共16×192=3072字节，逐字节匹配预期。设备69份原件已只读保存并于14:41:59.289484+08安全弹出，四个部署文件全部匹配；新增设备记录与主机请求顺序及STATUS状态/序号相符。65..80永久保留，实际记录remaining=0，不复用、不补次。

用户明确授权一次序号65实测，确认SD已装回、设备完全关机及USB接好。沙箱外父进程先通过环境与native文件检查，再正式发行；接收器进入WAITING后才通知开机，用户确认已开机。原生上下文也记录sandbox_check(self,NULL,0)=0、errno=0，OS build为26A434、framework UUID匹配。310份代码来源逐字节保持；设备包、build8/receipt8、第4版计划和lead32/4-2-2ms预算均沿用。

## 主机结果

| 项目 | 本次记录 |
| --- | --- |
| 等待会话 | `5EEC25E6-6A85-4B41-87A6-73F981F9030C` |
| SDK会话 | `777CB0EE-9196-486B-900E-9E08145CE95E` |
| device / interface ID | 4298366307 / 4298366319 |
| 领取、SDK初始化 | 各一次；prepared=true，无preparation_error |
| ISO提交 / 回调 / 主机abort | 1 / 1 / 0 |
| BURST触发 | 1，wValue=65 |
| 显式控制请求 | STATUS前、BURST、STATUS后，共3个；不代表整条总线的控制请求总数 |
| ISO有效事务 | 0..15，各192字节，载荷序号65..80；960个事务status均0 |
| 原始缓冲区 / 实际数据 | 184320 / 3072字节；其余事务无有效数据 |
| 领取前frame / first frame | 12165031 / 12165063，lead32 |
| frame query / enqueue调用 | 4209 ns / 299500 ns |
| enqueue时样本年龄 | 145917 ns |
| trigger样本年龄 / 距enqueue返回 | 535750 ns / 90334 ns |
| 退出 | exit0，waiter关闭，finished=true、unresolved=false |

接收器正常保存transfer与final checkpoint并退出，没有自动重试或第二次提交。主机成功支持这一次受限窗口的传输，不能据此推断持续流稳定。

## 设备原件及关联

用户按要求继续保持开机至少40秒，随后明确确认完全关机并把SD接到电脑。回收使用共享介质锁和正式只读入口：动态识别disk4s1，15条命令中14条diskutil、1条sync，仅一次readOnly/nobrowse挂载及一次安全弹出，零可写挂载、零卡载荷写入。旧标记修复作业与旧owner摘要保持；本次只读回收owner在成功后按协议释放，永久执行领取标记保留。

相对发行前63份快照，新增两组EXE3/primary和两份LCP1，只有logfile.txt变化，无删除；62份既有原件保持。8份既有ERPT及旧crash/fatal材料字节不变，没有新增ERPT。空boot2.flag及其余三个部署文件仍匹配。未发现新增保存错误报告，不等于证明运行期间绝无错误。

| 新EXE3 / LCP1前缀 | trace / 请求 | 判读 |
| --- | --- | --- |
| 806843 / e63942 | 84条，12个请求，dropped=invalid=0 | 接口2的STATUS→BURST(65)→STATUS与主机匹配；主机载荷65..80；primary4384字节且与嵌入副本相同，commit acknowledged |
| e05246 / 35a54b | 56条，9个请求 | 仅常规SET_INTERFACE，无本次BURST；保留原件，不并入本次匹配链 |

两份新LCP1均27条、zero_tail、error=null，最后main_return/result0；按boot/session关联各自EXE3。全部11份已保存EXE3与本次主机进行比较，只有806843匹配；9份旧原件和另一份新增原件均不匹配。故序号65排除了这组已保存历史中旧成功原件的误配。有限历史内唯一匹配不等于密码学主机会话认证。

完整收集另保存负面对照：错误LCP1、旧primary和仅主机材料都不能构成完整所供链。五份归档在新进程、移动目录后重新判读，结论保持；禁止读取原快照、正式保留目录或现场挂载的检查中，外部证据读取为0。

首次静态分析遇到两份历史旧recipe的LCP1，失败输出保留封存。r2明确列为不适用，不放宽recipe校验；新两份LCP1仍按本次recipe严格验证。没有为此重读SD或重发测试。

## 结论边界与后续

本次证明在已记录的执行环境和部署状态下，SDK可成功初始化且65..80受限突发可完成；在原两次lead32成功基础上新增了不同序号的成功观察。与49失败相比，执行环境、序号和已确认的标记状态均有差异，不能单独确认沙箱或标记就是49的根因。

静态收集的supplied_chain_complete=true表示材料之间相符。工具仍保留same_physical_run_verified=false、hardware_verified=false、usb_strict_pass=false；未认证跨时钟对齐、完整STATUS载荷关联、运行来源或连续流。

下一项为离线研究多突发/连续流的准入、缓冲区及退出条件，并为未来不同序号设计独立候选。81仅是保留到80后的候选起点，尚未构建、保留、发行或获实测授权。本次65权限已消费；旧49与失败修复作业均保持。当前设备已关机、SD已安全弹出，不需要新的现场操作。

## 封存与续接

| `private`下材料 | SHA256SUMS摘要 |
| --- | --- |
| `runs/A-context65-waiting-124a148e-ccad-4bb4-a7d7-1f896d42e7e5` | 见本轮closeout引用 |
| `card-cycles/20261018-context65-first-live-read`（69原件、71条清单） | `2e5e4375acb822927e71c46e5bf6eb3618047064972c307268aef34670860205` |
| `collections/A23-context65-first-live-806843-20261018` | `d8cf6f22adbcccd87616139736ca3f93d67d5d96850ab4c8893ba6f44ee4bc2b` |
| `analysis/A23-context65-first-live-analysis-20261018-r2` | 完整比较、解码、时序、来源与四份新增收集引用 |
| `analysis/A23-context65-first-live-closeout-20261018` | 人工确认、可变票据前后状态、移动重分析及文档快照 |

可变续接为 `analysis/A23-context65-pending.json`；实际消费记录为 `analysis/A23-context65-once-baseline63-live-20261018.json`。前序离线流程：[63份基线](A23_CONTEXT65_BASELINE63.md)。

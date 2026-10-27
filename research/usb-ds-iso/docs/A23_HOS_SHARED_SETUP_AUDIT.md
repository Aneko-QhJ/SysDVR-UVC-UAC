# A23 HOS共享SETUP审查（2026-10-13）

已确认当前Build-ID的HOS usb:ds使用一份8byte最新SETUP存储，接口读取时复制这份存储，
并清除当前接口的SetupEvent。它不为各接口保存独立请求队列。因此接口0/1读到BURST，
不能证明接口2稍后也读到BURST。后续SETUP覆盖是有机器码依据的候选机制；本次实机
是否发生覆盖仍未确认。SDK的16.395ms超时本身没有被证明会清除设备事件或替换SETUP。

本轮只读电脑材料，USB/SD访问0。设备仍A23，failed_no_retry/remaining0，未修改固件、
timeout、采集凭据或冻结材料。前次[EP0分发审查](A23_EP0_DISPATCH_AUDIT.md)的17个场景
与原始结论保留；本次补足其中“setup替换”假设的HOS机制和时间约束。

## 字节绑定与实际调用链

原始HOS usb NSO的Build-ID为
`AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000`，
SHA256为`08e0c60a2879e59bb7ace77a17418f7fc0d18058e90a2f12516ff8b1ebe62dfb`。
归档ELF三个PT_LOAD段与NSO解压后的text/rodata/data逐字节匹配。A23原始run、读卡、
collection和冻结包104个manifest文件重新核验；部署源码三个哈希匹配冻结记录。
冻结IPS32的22项修改与manifest及原始字节匹配，审查范围内EP0指令及接口虚表未被改动。
控制器事件函数唯一重叠修改在0x30898，属于type0x20 Transfer Event调用；type0x3f
SETUP分支及其store/notify调用未改动。运行时安装成功的依据仍为原完整设备日志。

下表地址为这个Build-ID的模块相对地址；不得用于其他版本。反编译辅助阅读，实际分支、
指令、虚表及补丁范围另行逐字节核验。没有重新运行Ghidra，也没有模拟执行HOS机器码。

| 路径 | 已核对的行为 |
| --- | --- |
| IDsInterface命令2，IPC函数0x254e0 | 解码输出buffer，调用接口虚方法+0x30 |
| 实际接口虚表0x8fed0，槽+0x30 → 0x27d60 | 解包buffer地址/长度，接口对象偏移+8，跳到0x2cf90 |
| 0x2cf90 → 0x2a150 | manager指针取自interface+8；endpoint选择0；event传interface+0x120；wrapper返回0 |
| 0x2a150 | 锁manager+0x17f0，复制manager+0x17e8的min(size,8)bytes，清除传入接口event，解锁 |
| 0x2a0f0 | 同一把锁下把8byte新setup覆盖到manager+0x17e8，不按interface索引分槽 |
| 0x30700，type0x3f分支 | 保存setup/控制序号；普通序号调用0x2a0f0，再调用0x2a2c0通知管理线程 |
| 0x2aa20 | 复制当前setup进行标准请求处理；本次41/54和C1/51走广播，依次signal已注册的4个接口event槽 |
| 0x2cf00 → 0x2a1e0 | SetupEvent命令1的实际注册路径：manager+0x1810+index×8保存interface+0x120 |
| 0xb470 / 0xb4a0 | signal/clear事件；本地signal为置位状态，本地clear置0；remote到SVC0x11/0x12 |

[libnx作者源码](https://github.com/switchbrew/libnx/blob/master/nx/source/services/usbds.c)
交叉确认GetSetupPacket使用命令2和输出映射buffer，SetupEvent以autoclear=false加载。
网络master仅用于名称/协议交叉核对；部署libnx机器码绑定来自前次审查，不能用master替代。
HOS内层复制函数检查的是endpoint选择0；没有请求代次或当前控制state检查。返回成功
并不表示读到先前event对应的同一个SETUP；实际IPC传输错误仍可能返回失败。

广播event是通知当前状态的置位机制，不能把两个未读取请求理解为队列中两个独立项。
客户端还会在GetSetupPacket前手工eventClear，而HOS读取路径再次清除当前event。
锁保证8byte读取/覆盖与内层clear串行，不保证不同接口之间的请求快照相同。

## 保存的主机时间给出的约束

以BURST SDK调用start_ticks为0，原记录timebase=125/3：

| 事件 | 相对时间 |
| --- | ---: |
| 控制Timeout回调入口 | 16.395292ms |
| after STATUS SDK调用开始 | 30.565333ms |
| after STATUS SDK调用结束，168bytes | 34.225583ms |

如果替换者是这一次after STATUS，替换就需要等它的SETUP实际到达HOS。
30.565ms是主机调用边界，不是已经测量的总线/设备到达时刻。没有跨时钟对齐。
原先20ms日志延迟、16ms时刻注入替换的场景只说明条件分支，不能代替这次请求的时间。

两条BURST广播记录要求接口0、1在覆盖之前读到原请求；seq0要求接口2未走到BURST写seq
阶段。覆盖候选因此需要接口1读完原请求后、接口2读取前发生新SETUP。是否由四次同步SD
刷写、调度或其他等待形成该窗口，目前没有阶段计时，不能把30ms归因给其中某项。

## 六个实际客户端源码模拟

复用前次服务fixture的基础类型和辅助函数，插入真实_ctrl/ISO/setup/process源码；
新增共享8byte存储、每接口boolean事件、GetSetup时clear，以及一次后续STATUS到达。
这些服务操作依据已核对的HOS路径建模，但总线到达、日志耗时、速度及传输结果由fixture
注入。模拟不包括HOS线程/控制器、MMIO、真实IPC和SD性能，不能用于根因或修复验收。

| 注入条件 | 接口2第一次读取 | seq / post | 含义 |
| --- | --- | --- | --- |
| 无日志延迟，STATUS在30.565ms到达 | BURST | 1 / 1 | 正常先服务BURST |
| 四次日志各5ms，总20ms | BURST | 1 / 1 | 超过16ms仍不自动丢弃setup |
| 四次日志各7ms，总28ms | BURST | 1 / 1 | 仍早于假定后续setup |
| 四次日志各8ms，总32ms，STATUS在30.565ms到达 | STATUS | 0 / 0 | 可保持原IDLE/seq0；0/1先读BURST再读STATUS |
| 同32ms，STATUS实际到达另晚5ms | BURST | 1 / 1 | 主机调用开始不能等同总线到达 |
| 同32ms，没有后续SETUP | BURST | 1 / 1 | 延迟本身不足以覆盖请求 |

32ms替换场景的STATUS回复虚拟发生在32ms，位于保存的30.565..34.226ms主机调用窗口；
这说明存在与时间边界相容的调度例子，不是对实机时序的拟合或证明。模拟保持两接口原
BURST广播、后续STATUS广播及168byte回复；关键差异是接口2读取的8byte内容。
六场景通过ASan/UBSan；5项新增Python检查覆盖源码模拟、修改store/虚表拒绝、EP0
补丁重叠拒绝、IPS损坏/重叠拒绝。相关回归结果见本次validation目录。

## 复现与证据

从仓库根目录运行，输出须为新目录：

```sh
python3 research/usb-ds-iso/tools/audit_a23_hos_setup.py \
  --output /private/tmp/a23-hos-setup-new-review
python3.12 -m unittest discover -s research/usb-ds-iso/tests \
  -p 'test_a23_hos_setup.py' -v
```

私有输入默认读取当前分支对应.git归档的module；也可用--module指定同一已验证版本。
厂商模块、反编译和冻结包不公开。最终证据：
private/analysis/A23-HOS-shared-setup-review-20261013-final，含audit.json、机器码/反编译
节选、生成源码和模拟二进制及SHA256SUMS。前一个无final目录是初步审查，保留原样；
final扩大了IPC函数反汇编范围到整个0x254e0..0x26820，结论与6个场景不变。
回归、源码快照及凭据核验：private/analysis/A23-HOS-shared-setup-validation-20261013。

## 下一步电脑工作

设计并验证有界内存trace，首先记录每接口eventWait结果、eventClear前后tick/rc、
GetSetup前后tick/rc和实际8byte setup；再记录ISO入口state、GetSpeed、写seq、post、
ACK post/wait/report/parse分阶段结果。只记录event成功和重要状态变化，避免空轮询耗尽。
固定容量，满时保留旧记录、overflow计数，不在关键路径刷SD；boot/session身份、时基、
导出完整性及freeze规则需一起设计，USB/IPC结构不先增加查询。

若取得新证据：接口2读STATUS支持覆盖候选；读BURST而GetSpeed失败/非HS支持早退候选；
seq已写却之后返回0要求重新核对实例、初始化与STATUS来源。现有材料缺少这些分支记录。
下一步不单独提高timeout，也不直接调换接口顺序：两者均可能改变迟到TD和关键时序，
目前没有足够证据选择部署改动。首次实机失败、原空槽政策及remaining0保持。

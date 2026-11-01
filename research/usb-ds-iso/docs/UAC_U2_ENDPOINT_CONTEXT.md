# UAC U2：端点上下文、安装器与缺失的 commit（v23 离线）

> 状态：**v23 实机一次，成功**。离线部分只读 `usb.elf`（`0x295d0` 安装器、
> `0x2fd30/0x2feb0` 端点 setup、`0x30b50` 上下文安装、四个 ring 复位站点）；
> 2026-11-01 16:0x 用 `d984f729…` 一次 boot：host **12288B（4×3072）**，
> 设备 `posted=4 completed=4`、seq1..4 都 `complete 3072/3`，无 crash。
> 当前事实仍以 [CURRENT.md](CURRENT.md) 为准，burst 线的历史见
> [UAC_U2_RING_RESET.md](UAC_U2_RING_RESET.md)。

## 结论（一句话）

安装器 `0x295d0` 只是描述符遍历器，不碰控制器；真正把端点挂上控制器的是
`0x2fd30 → 0x2fd80 + 0x2feb0`：写 64 字节端点上下文（state=1、TR dequeue
物理地址 + DCS），再写 `regs+0x58` **commit** 并清 `regs+0x54/0x50` 的 halt。
完成错误路径 `0x30ff4` 在 burst 之后重写了同一份 ring/上下文，却**不 commit、
不清 halt**（这一半是静态事实）。由此推断控制器保持旧状态、第二套 TD 不再被
取指（这一半已由 v23 实机确认，§9）。v23 候选在每个 burst 前重放一次 `0x2feb0`。

## 地址与对象（本模块布局，全部由指令推导）

| 对象 | 地址 / 公式 | 出处 |
| --- | --- | --- |
| manager（`usb:ds` 控制器对象） | `base + 0xDA000` | `0x2854`/`0xB44`；`tests/test_uac_u2_precheck.py` |
| 控制器区 | `manager + 0x22000` | `0x302FC`/`0x30300` |
| 端点对象（DsEndpoint） | `manager + 0x22078 + dci*0x48` | `0x302E8..0x30304` |
| EP `0x84`（DCI 9） | `base + 0xFC300` | 同上，`0x22078 + 9*0x48` |
| EP `0x83`（DCI 7，A23） | `base + 0xFC270` | `0x22078 + 7*0x48` |
| 安装对象 | `[manager + 0x229B8]` = `base + 0x17B038` | `0x30294..0x302A8` |
| 安装 flag / 表项 | `obj + 0x14D0/0x14C8 + index*16` | `0x29600`/`0x2A9C4` |
| 端点上下文数组 | `[manager + 0x22050] + dci*0x40`（64B） | `0x30BF0..0x30BF8` |
| 寄存器基址 regs | `[manager + 0x22008]` | `0x31CD0`、`0x304C8` |

端点对象字段（`0x302E0`/`0x2FD80`/`0x2FEB0` 写、cave 读）：

| 偏移 | 含义 |
| --- | --- |
| `+0` | 8 字节端点描述符副本（`+2` = 端点字，`+6` = interval） |
| `+0x10` | ring base（虚拟地址） |
| `+0x18` / `+0x20` | enqueue（prod）/ dequeue（cons） |
| `+0x28` | 当前 Link TRB 指针（安装后 `ring+0xFF0`，cave 用 `ring+0xF70`） |
| `+0x30` | ring 缓冲（`0x1000`，DMA 缓冲） |
| `+0x38` | ring 的总线/物理地址（DMA map 结果） |
| `+0x40` | cycle（DCS，字节） |
| `+0x42` | DCI（字节） |

## 1. 安装器 `0x295d0` 做什么

入口 `0x292b0(install_obj, w1=state, w2=speed)` 是总线状态机；`0x295d0`
只在一个方向上被调用：

- `w1=1`：**安装**。SS（`w2==4`，`0x29608`）和 HS（`0x29A84`）两条路径遍历
  接口 0..3 的描述符（`0x2B520` 取描述符）；每个 type-5 端点调用
  `vtable[+96]`，**然后**才把 `install_obj + 0x14D0 + index*16` 置 1
  （`0x296E4`、`0x29B08`）。
- `w1=0`：**卸载**。只对 flag==1 的端点：清 flag、`0x2C890(表项)`、
  `vtable[+104]`（`0x297A0..0x297D8`）。

`0x295d0..0x2A050` 内**没有**寄存器访问、没有上下文写；它只写安装 flag、
表项和调用两个回调。状态机里 install 只发生在 **4→5**（`Configured`），
卸载发生在 **3→4**（`Address`）和 **5→4**；状态值取自 libnx `UsbState`
（3=Default、4=Address、5=Configured、6=Suspended）；控制器初始化
（`0x2F0D0` → `0x2F188`）只把状态推到 3，装的是 EP0。`SET_INTERFACE` 不
经过 `0x292b0`，所以 v22 观察到的“alt0→alt1 不重装”是必然的。

`[install_obj+8]` 就是 manager；它的 vtable 在 `.data`：
slot 12（`+96`）= `0x2FD30`、slot 13（`+104`）= `0x300B0`（`.data` 的
`0x90548`/`0x90550` 两个相邻指针，vtable 基址 `0x904E8`）。两个函数的签名
正好匹配安装器的调用：前者收“描述符 → 端点”，后者收“端点地址 → 摘除”。

## 2. 端点 setup：`0x2FD30 → 0x2FD80 + 0x2FEB0`

`0x2FD80`（建/找端点对象）：

- 从描述符字 `[desc+2]` 算 DCI（`dci = (epnum<<1) | dir`），对象
  `manager + 0x22078 + dci*0x48`；
- 描述符 8 字节原样拷到 `+0`，DCI 写到 `+0x42`；
- 若 `[obj+0x30]==0`：分配 `0x1000` ring（`0x3150`）、cache 维护
  （`0x10ED0`）、DMA map（`0x46C0`；容器由 `0x30C0` 取 `[manager+0x30]`，
  空指针即断言）→ `[obj+0x38]`。

`0x2FEB0`（本轮的核心）：

```text
if ([ctx] & 7) != 0:  [ctx] &= ~7          ; 0x2FEF4/0x2FEF8，先置 disabled
memset([obj+0x30], 0, 0x1000)              ; 0x2FF04..0x2FF18
[obj+0x10]=[obj+0x18]=[obj+0x20]=[obj+0x30]; [obj+0x40]=1
0x30B50(manager, obj)                      ; 写 64B 上下文
[obj+0x28]=ring+0xFF0；写 Link TRB 到 ring+0xFF0（addr=[obj+0x38], ctl=0x1800|2）
regs+0x58 = 1<<dci；轮询到 bit 清零        ; 0x2FFA0..0x2FFCC  ← commit
if regs+0x54 & bit: 清 bit；轮询 regs+0x5C；ack regs+0x5C   ; 0x2FFD0..0x3002C
if regs+0x50 & bit: 清 bit；轮询 regs+0x5C；ack regs+0x5C   ; 0x3003C..0x30084
```

`regs+0x58` 是**把上下文提交给控制器**的按端点命令（写 bit、自清）；上面
最后两步清的是 halt/stop 位。摘除路径 `0x300B0 → 0x30100` 的顺序正好相反：
清上下文 state → 写 `regs+0x58`（提交 disable）→ 清空 64B → 清 halt 位。

## 3. 上下文格式（`0x30B50`）

`ctx = [manager+0x22050] + dci*0x40`，64 字节，按 dword：

| dword | 内容 | 指令 |
| --- | --- | --- |
| 0 | `(old & ~7) | 1`（state=running）；interval 放在 bits 16..23 | `0x30C0C..0x30C28` |
| 1 | 端点类型 / burst / max packet / CErr（按 speed、attrs、mps 计算） | `0x30C2C..0x30CE0` |
| 2/3 | **TR dequeue 指针**：`0x4E50(容器, [manager+0x20A8+dci*0x48])` 的低/高 32 位；容器由 `0x30C0([manager+0x22990])` 从 `+0x30` 取出，`0x4E50` 做设备地址→物理地址转换；低 4 位保留旧值，bit0 换成 `[obj+0x40]` 的 cycle（DCS） | `0x30CF0..0x30D38` |

上下文本身是普通内存，**只有 `regs+0x58` 的 commit 才会让运行中的控制器重新
读取它**。

## 4. 谁会在 burst 之间改 ring

只有四个站点会把 `base/enqueue/dequeue/cycle/copy` 复位到 ring base 并重装
上下文（编译期搜索 `add x9,x8,#0xFF0` 只有这四处）：

| 站点 | 触发 | memset ring | 上下文 | commit `0x58` | 清 halt |
| --- | --- | --- | --- | --- | --- |
| `0x2F480` | 全部 32 个端点（`0x30EDC` → `0x2F470`，总线状态处理/初始化） | 是 | 是 | **否**（随后 setup 再 commit） | 否 |
| `0x2FEB0` | 端点 setup（安装/摘除/重开） | 是 | 是 | **是** | **是** |
| `0x30470` | 端点 reset（vtable slot 14；state==1 时先做 `0x54` 的 halt 握手，再 memset/重装） | 是 | 是 | **否** | 否（只清 `0x54`） |
| `0x30FF4` | 控制器事件的**错误码**分支 | 是 | 是 | **否** | 否（反而 **置** `regs+0x50`） |

`0x30FF4` 在 `event_original`（`0x30F70`）里，错误码集合为
`0x8000C438` 的位 {3,4,5,9,10,14,15,31} 加上 `0xDB`/`0xDE`
（`0x31170`/`0x31198`）；`0xDC` 走 ack（`0x311A8`），`0xDD` 置 mask
（`0x31324`），`0xDF` 单独走 `0x31180`（停止/清门状态，语义未命名）。成功码 1 的路径只把
`cons = 下一个 TRB`（`0x31238..0x31264`）并逐 ED 调
`complete_original(w4=192, w3=0, w5=1)`（`0x31CF0` → `0x31D2C..0x31D6C`），
**不碰 ring**。

## 5. 为什么“只有第一个 TD 集被取指”（v23 已确认）

**直接证据**：安装路径会 commit 并清 halt；错误复位路径 `0x30FF4` 会重写
ring/上下文但不 commit、不清 halt。实机日志（v16 的 `done` 行、v19 在
`eventWait` 后立刻看到 mailbox 被清零）只能证明 burst 之后 ring 被某条复位
路径清零；四条站点里只有 `0x30FF4` 在控制器事件路径上，因此归因到它是推断，
不是直接观测。

**v23 实机确认**：控制器因此仍停在 halt/旧 dequeue，后续门铃不再取指（§9）。

1. 安装时 `0x295d0(Configured)` → `0x2FD30` → `0x2FEB0`：上下文 state=1、
   dequeue=ring base、DCS=1，commit + 清 halt。第一个 burst 的 TD 集在 base
   写入后，门铃让控制器从 base 取指，成功。
2. 16 个 ED 完成后，控制器给出错误/停止事件（具体码未在实机观测；能进
   `0x30FF4` 的是 3/4/5/9/10/14/15/31 或 `0xDB`/`0xDE`）；驱动置 halt
   （`regs+0x50`）、memset ring、把上下文重写回 base/cycle=1，**但不 commit、
   不清 halt**。
3. 驱动在错误路径里把 ring 字段复位，于是 app 的 `seq=2 pre` 读到
   `prod=cons=copy=base`；cave 的 `prod==cons` 门照常通过，TD 集写在 base，
   `PostBufferAsync` 返回 0，门铃也写了——但控制器的端点仍是 halt/旧状态，
   不会去取新的 TD 集。
4. 证据自洽：v16 r2 的 `done` 行（burst 后 prod/cons/copy 回 base）、v19 在
   `eventWait` 之后立刻看到 ring+0xF80 的 mailbox 已被清零（说明 memset 发生在
   **事件处理里**，不是 app 的 report 调用）、v21 空闲 cancel 看不到字段变化
   （字段已经是 base，且 `0x30470` 没有 commit）、v22 alt 重装不跑安装器。

v17（把 TD 写到 base+0x200）、v20（cave per-ED 完成）、v21（idle cancel）、
v22（alt 重装）都只改动“位置/完成方式/重装触发”，没有任何一处让控制器重新
读取上下文，因此全部失败。

## 6. 附带发现：cave 事件路径的 `ISO_ENTRY` 错位

DCI 9 的端点对象在 `manager+0x22300`（`ISO_ENTRY` 应为 `0x300`），但所有
UAC cave（`dci9_noreport.S`、`dci9_eventcode.S`、`dci9_pered.S`）都写
`.equ ISO_ENTRY, 0x270`——那是 DCI 7（A23 EP `0x83`）的对象。UAC 配置里没有
DCI 7 端点，`[0xFC270+0x10]` 为 0，`iso_event` 在 `cbz x5` 处直接
`b event_original`。结论：

- 自 v14 起，UAC 的 transfer event 一直由驱动的 `event_original` 处理，
  **cave 的 mailbox/事件代码从未执行**；v19 的 `event=0`、v20 的“per-ED 不是
  差异点”都是驱动路径的结果，不能用来评价 cave 的事件分支。
- 本轮**不修**这个错位（保持“一次只改一个变量”）；若下一轮需要 cave 自己
  处理事件（例如绕过驱动的错误复位），必须把常量改成 `0x300`，并同时处理
  错误码，否则会吞掉错误、让 URB 只能靠 app 超时 cancel。

## 7. v23 候选：每个 burst 前重放 `0x2FEB0`

| 项 | 值 |
| --- | --- |
| assembly | `patches/iso_burst_uac84_dci9_rearm.S`（`dci9_noreport` + 一次 `bl rearm_endpoint`） |
| 行为 | `prod==cons` 门通过后：保存 `x0/x1/x2/x30` → `bl 0x2FEB0(manager, ep)` → 恢复 → 重载 `x8/x10`、重算 `x6` → 原有 TD 写入/mailbox/Link 修正/门铃 |
| payload | 29 条 edits / cave **620B**（limit 684）/ cave 前缀 `dci9_noreport` 不变 |
| NSP | `d984f729…`（91927B），`-DUAC_U2_BURSTS=4`（v15/v16 的 4-burst 顺序 train） |
| 工作目录 | `private/analysis/UAC-u2-v23-rearm-20261101`（已实机一次，见 §9） |
| 风险 | 在提交路径里重入驱动 setup：每次 post 多一次 4KB memset + 上下文重装；halt 握手最坏会 `sleep(50us)` 轮询到 100ms（发生在 post 之前，app 的 100ms 完成超时从 post 之后才开始）；只写本端点自己的 ring/上下文/寄存器 |

判定（一次 boot、失败即停）：

| 观察 | 结论 |
| --- | --- |
| 4 个 burst 各 3072B、设备 seq1..4 都 `complete 3072/3` | **缺失步骤就是 commit/unhalt**；下一步做持续流（不再每 burst 重装）与时钟 |
| 仍只有 seq1 完成 | halt 假设不成立；下一轮先做只读上下文诊断（见下） |
| 任一 crash/fatal/erpt | 立即停，读卡取报告 |

只读诊断（若 v23 失败，下一轮的首选）：app 通过 dmnt 读
`[manager+0x22050]+dci*0x40` 的 64 字节上下文（`+0` state、`+8/+0xC`
TR dequeue + DCS）在 post 前后、完成前后的值。若 state 变成 2/3/4 或 dequeue
不在 base，可把“halt”与“dequeue 错位”彻底分开；这一步不写任何内存。

## 8. 静态验证

- `tests/test_uac_u2_endpoint_context.py`（新增）：从 `usb.elf` 解码
  上下文数组/64B 步长、state/interval、TR dequeue + DCS、`0x2FEB0` 的
  commit/halt 清理、`0x30FF4` 与 `0x30470` 缺少 commit、DCI 7/9 的对象
  偏移（`0x270`/`0x300`）以及 v23 cave 的 `bl 0x2FEB0`（还能在本地工具链
  存在时实际汇编一次）。
- `make check` 见本轮提交信息。

## 9. 2026-11-01 16:0x v23 实机：4/4 burst 成功

一次部署、一次 boot、一次 probe；纪律：VM 在开机时 suspend，主界面后经
`prlsrvctl usb set` + 一次 VM suspend/resume 完成枚举，probe 只跑一次。

| 项 | 结果 |
| --- | --- |
| host | `claim/alt1/SET_CUR` ok；`done transfers=62 packets=16 valid=217 bad=775 bytes=12288`；四个 3072B burst（t=34/194/356/498 ms，2688+384 / 2304+768 / 384+2688 / 192+2880） |
| 设备 | seq1..4 每个 `post rc=0`、`complete rc=0 requested=3072 transferred=3072 status=3`；`UAC U2 train end posted=4 completed=4 pattern=3072` |
| ring | 每 burst 后 prod/cons/copy 仍被驱动复位回 base；下一个 burst 仍被取指——**commit/unhalt 就是差异** |
| crash | 无；日志无 crash/fatal/erpt，卡 erpt 27 / crash 21 与部署前相同 |
| 证据 | `private/runs/UAC-u2-v23-rearm-20261101`（`host-raw.txt` `205b3fee…`、`device-log-v23.txt` `c10005d2…`、`device-config.txt` `15422226…`）、`private/card-cycles/20261101-u2-v23-rearm` |
| 收尾 | 恢复 `52069a44…`、删 `/logfile.txt`、安全弹出；无重试 |

结论：**“只有安装后第一个 TD 集被取指”的原因是完成错误路径 `0x30ff4`
复位 ring/上下文后没有 commit、没有清 halt**；每 burst 重放驱动 setup
`0x2feb0` 后控制器重新取指，4 个顺序 burst 全部完成。这是 burst 线第一次
拿到超过 1 个 burst（12288B）。

代价与下一轮：当前每 burst 多一次 4KB memset + 上下文重装 + commit + 清 halt
（`0x2feb0` 全量）。下一步把它收敛为“首 burst 后只做 commit/清 halt”，或让
ring 跨 burst 连续，再验证 8/16 burst 与更短间隔。

## 10. 下一步

1. v23 已成功（§9）。下一轮把“每 burst 重放 `0x2feb0`”收敛为“首 burst 后
   只做 commit（`regs+0x58`）+ 清 halt”，或让 ring 跨 burst 连续（不 memset、
   不重置 base），用 8/16 个 burst 验证；仍一次 boot、失败即停。
2. 之后进入持续流（PCM/时钟/与视频共存）；UAC 默认仍禁用（仅
   `UAC_HOST_PROBE`）。
3. 修 `ISO_ENTRY`（0x3xx）与 8 个 descriptor-parser NOP 的全局风险仍待单独
   隔离。

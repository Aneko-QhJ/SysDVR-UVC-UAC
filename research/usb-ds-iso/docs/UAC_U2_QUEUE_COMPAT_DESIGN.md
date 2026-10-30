# UAC U2 队列兼容的 ISO 提交设计（2026-10-30）

> 状态：**离线设计草案 + 四次实机**；completion/report 回放已做。no-report
> 的 report 修复成立但随后崩溃；v3 installed/table 门在 `force-alt1` 后通过，
> completion 3072/3072、无崩溃，设备侧单次 burst 通过（host 16/16 未计数）。
> 地址均来自
> `private/module/usb.elf` 的当前 BuildID；所有“预期”都不是实机结论。
>
> 结论：不要再伪造“拒绝→返回 0”。driver 已经在 `0x2c520` 里完成 map 和
> 入队，cave 拿到的是已入队的请求；正确方向是让这个请求走完一次真实的
> completion，并让 driver 自己生成 report。当前最确定的缺陷是 report 被
> cave 覆盖；map 重复的来源还需要用 entry/队列状态区分“第二次 post”与
> “unmap miss”。

## 1. 现象

U2 六次实机的结果见 [CURRENT.md](CURRENT.md#L10-L19)。与本设计直接相关的三条：

1. precheck2：`post rc=0` 之后，usb 在完成/重提路径以 `0x1908c` 递归崩溃；
2. breaker：`0x302c0` 的 `nop` 同时跳过了 EP0 的错误完成，未 post 就断言；
3. safecave：首次收到 completion，但 `rc=0x748c requested=0 transferred=0`，
   随后触发风暴把 EP0 打崩。

离线已证明 fake-accept 会断言：

```
0x3da8  bl 0x4a20        ; 区间映射插入，重复/重叠返回 0
0x3dac  cbz w0, 0x40cc   ; 插入失败 -> panic
0x40cc  bl 0x9540        ; assert
```

即“请求没有真正入队/释放”，清理时再次插入同一区间。返回 0 绕过 driver
簿记不可行。

## 2. driver 实际路径

EP `0x84` 的一次 `PostBufferAsync`：

```
app  usbDsEndpoint_PostBufferAsync
  -> 0x2a420  IPC handler
  -> 0x2a330  endpoint lookup / cache flush
  -> 0x2c520  DMA map + request entry enqueue + submit
       -> 0x3c50  map (0x3d40 -> 0x4a20 interval tree)
       -> 0x2c5d0..0x2c664  enqueue entry, status=2
       -> blr [controller vtable + 136]  == 0x302e0
            -> 0x30364  ISO branch
                 original: b.eq 0x30394  (return 0x1908c)
                 U2 cave:  b.eq iso_enter
```

关键点：**请求项在进入 `0x302e0` 之前就已经入队并完成 DMA map**。cave 拿到
的是已经 map 过的 IOVA（`x2`）和已入队的 entry，不是“无簿记”的裸提交。

完成路径：

```
0x2a980  complete_original(controller, addr, x2, w3, w4, w5)
  -> table[manager + 0x14c8 + index*16]
  -> 0x2c690(entry, x1, force=w3&1, transferred=w4, lock=w5&1)
       entry+32  requested size
       entry+44  transferred so far
       entry+40  status (2=active, 3/4/5=done)
       entry+16  mapped IOVA
```

`0x2c690` 把 `transferred`（它的第四参，来自 `complete_original` 的 `w4`）
加到 `entry+44`，再和 `entry+32` 比较：

- 相等 → `0x2c714`，做 ZLP 检查，然后按状态 unmap/释放；
- 不相等且 `force == 0` → `0x2c770`，提交剩余部分；
- 不相等且 `force == 1` → `0x2c758`，status=3，unmap/释放。

report 由 `0x2cbe0` 之前的代码从同一个 entry ring 生成（`entry+0 id`、
`+32 requested`、`+44 transferred`、`+40 status`，count 写到 report+128）。

## 3. 现有 cave 的问题

### 3.1 report 被 cave 覆盖（确定）

`0x2cbe0` 是 report 函数的收尾（driver 已经把 entry ring 复制到 report、
写好了 count）。U2 payload 把这条 `add x0,x19,#0x10` 换成 `b iso_report`，
`iso_report` 用 mailbox（magic/bitmap/actual/first TRB）覆盖 `x20+16` 的
report 数据，但 count 仍是 driver 写的值。app 解析到的是 mailbox 字节，
不是 `{id, requestedSize, transferredSize, urb_status}`，所以
`usbDsParseReportData` 返回 `0x748c`、`requested=0`、`transferred=0`。

这是当前最确定的缺陷：即使 completion 完全正确，report 也一定解析失败。

### 3.2 拒绝时返回 0，请求和映射留在队列（确定）

`fail_accept` 直接 `mov w0,#0; ret`。但此时 `0x2c520` 已经 map 并入队；
返回 0 只让调用方跳过错误完成，entry 和映射都留在原地。下一次 map 同一
区间就会在 `0x4a20` 插入重复区间 → `0x40cc` 断言。

A23 的“完成缓冲复用会崩”是同类问题；serial640 用 640 个不同 buffer 避开
了复用，所以看起来“稳定”。U2 用同一个静态 buffer，复用时立刻触发。

### 3.3 completion 本身已经是 3072，不是 192

`iso_event` 在 16 个 ED 后调用：

```
ldr w4, [x5, #20]        ; previous actual (2880 before the 16th ED)
add w4, w4, #192         ; 3072
str w4, [x5, #20]
cmp w4, #3072
b.ne done
...
mov w2, #0
mov w3, #1
mov w5, #1
b complete_original      ; w4 = 3072
```

所以 completion 传入的 `w4` 是 3072，`entry+44` 会等于 `entry+32`（若
requested=3072），不会走“剩余 2880”的分支。这个数不需要改。

`0x2c690` 在相等后调用 `0x2a8b0` 做 ZLP 检查；`0x2a8b0` 只在端点 flag
为 1、`[desc+3] & 2`（bulk）且 size 是 MPS 整数倍时返回 1。UAC 端点 attrs 是
`0x05`（ISO），bit1 为 0，所以返回 0，**不会走 ZLP 提交**。也就是说
completion 的字节数和 ZLP 都不是当前空报告的直接原因；最直接的解释是
3.1 的 report 覆盖，但 report count 是否另有问题仍需 §7.3 确认。

### 3.4 map 重复的来源仍未定

崩溃栈 `0x2c584 -> 0x3ce0 -> 0x40d0` 指向一次 map（`0x3c50` ->
`0x3d40` -> `0x4a20`）；`0x2c584` 是 `0x2c520` map 后的返回地址。但 crash
report 只保留了 7 帧，不能排除这个帧是更早 U2 post 的残留。可能的原因：

- **H1：第二次 `PostBufferAsync`（U2）。** `burstPosted` 目前是在 post 调用
  **之后**置位；虽然事件循环是单线程，理论上不该并发，但日志只能证明
  一次成功 post，第二次可能直接在 map 里崩、来不及打印。需要 post 序号
  和“在 post 之前置位”来排除。
- **H2：第一次 completion 的 `0x4c70` unmap miss。** A23 审计已发现
  `2c690` 不检查 `4c70` 的返回值；地址不匹配会静默泄漏。之后即使
  第二次 post 用的是新 buffer，分配器也可能把仍留在树里的 IOVA 再分
  一次，触发重复插入。
- **H3：EP0 控制缓冲的重复 map。** 100× SET_CUR 风暴后出现
  `0x25c8c/0xf601` 数据阶段失败；如果控制缓冲在同一区间树上重复插入，
  也会走同一条断言，和 U2 post 无关，`0x2c584` 只是栈上的旧帧。

这三个假设不影响 3.1/3.2 的修法，但决定 3.4 要不要额外修 unmap 或控制
路径。设计必须把“post 序号 + entry 字段 + 控制传输计数”作为下一个判别点，
而不是继续猜。

## 4. 设计目标与不变量

1. 每个被接受的 submit 必须恰好完成一次：`entry+44` 等于真实传输字节，
   status 进入 done，`0x4c70` unmap 成功，entry 出队。
2. 拒绝不得返回 0；要么在 app 侧 precheck 阻止 post，要么让 driver 的
   错误完成真正移除 entry（不能递归）。
3. report 必须来自 driver 的 entry ring，不再覆盖。
4. 每次 boot 只 post 一次；同一 buffer 在确认 unmap 前不复用。
5. cave 仍放在 `0x68d54..0x69000`（684B）；新增逻辑优先用删除 report
   hook 和诊断腾出的空间。

## 5. 方案比较

### A. 保留 driver 请求，修 report 和一次性（推荐）

不重写提交路径；只做：

1. 删除 `iso_report` hook，恢复 `0x2cbe0` 的 `add x0,x19,#0x10`，让
   driver 用 entry ring 生成 report；
2. `burstPosted` 在 post **之前**置位，并记录 post 序号；
3. 每次 post 使用独立的 4KB 对齐 buffer，确认 unmap 前不复用；
4. 增加完成后的 entry/队列状态读取（`ep+4`/`ep+8`、`entry+16/+32/+40/+44`），
   同时记录 post 序号与控制传输计数，用于区分 H1/H2/H3；如果是 H2，再修
   `0x4c70` 的参数/返回值检查。

优点：改动最小，直接复用 driver 的 map/unmap/report/队列；不需要重新
实现 ISO submit。风险：如果 H2 成立，仅删 report hook 不能解决 map 重复，
需要额外的 unmap 修复；这可以用离线模型先确认。

### B. 直接在 cave 里改 entry / unmap / 出队

如果 `0x2c690` 会重复完成或无法安全调用，就在 cave 里直接写
`entry+44`、`entry+40`，调用 `0x4c70`，推进队列索引，再触发 completion
event。缺点：复制 driver 的锁/索引/状态机，代码量和风险都大；只有在 A
被离线证伪后才考虑。

### C. 在 driver 里补一条原生 ISO submit 路径

把 `0x30394` 的拒绝替换成完整的 ISO 实现（等价于 `0x2c520` + TRB +
`0x2c690`），不再依赖 cave。需要新 cave/更大代码空间，当前 684B 放不下；
作为长期方向，不作为本轮方案。

## 6. 推荐方案的补丁草案

### 6.1 report

删除 payload 里的 `REPORT_HOOK` 编辑和 `iso_report` 函数；`0x2cbe0`
保持原指令。若还需要 mailbox 诊断，写到 `private` 日志或另一个不覆盖
report 的位置，不能再用 `x20+16`。

### 6.2 completion

**不改** `w4`：当前 `[x5+20] + 192 = 3072` 已经正确。只保留 3.1 的
report 修复；如果离线模型显示 `entry+44` 没有到 3072，再查 `x5+20` 的
初始化（`iso_enter` 里 `stp xzr,xzr,[x5,#8]` 是否覆盖了 actual）。

### 6.3 拒绝

- app 侧 precheck 继续作为第一道门（endpoint word/interval/speed/ring）；
- cave 的 `fail_accept` 不再返回 0。候选：
  - 返回 `0x1908c` 让 `0x302c0` 走 driver 错误完成，但必须离线证明
    它不会再递归（当前 precheck2 已证伪，需先解决重提）；
  - 或把“小于 3072 的重提”视为已完成，完成 entry 而不是拒绝。
- 在离线仿真确定之前，**不部署**任何 cave 拒绝路径。

### 6.4 app 一次性

```c
if (g_uacCtx.burstPosted) return;
g_uacCtx.burstPosted = true;   /* before the post, not after */
u32 seq = ++g_uacCtx.postSeq;
LOG("UAC U2 post begin seq=%u\n", seq);
```

并把 `g_audioEndpointBuffer` 换成每次 post 取一个未使用的 4KB 对齐槽；
这样即使 completion 仍有残留，也不会在同一个 boot 内复用地址触发
重复 map。它是安全网，不是 completion 修复的替代。

### 6.5 完成后的状态读取

在等待 completion 之后、下一次 SET_CUR 之前，用现有的 dmnt 读：

- post 序号（app 日志）与控制传输失败计数；
- `ep+4` / `ep+8`：队列索引 / count；完成后 count 应回到 post 前的值；
- `entry = ep+0x78 + idx*0x30`；
- `entry+16`（IOVA）、`+32`（requested）、`+40`（status）、`+44`（transferred）。

如果 `count` 没减、`status` 还是 2、或 `+44` 不是 3072，就能区分 H1/H2；
如果 U2 entry 正常而风暴后仍断言，则偏向 H3。这一步是诊断 payload，不是
最终产品。

### 6.6 预算

原 cave 668/684B；删除 `iso_report` 后的 no-report cave 为 **592/684B**，
余 92B。completion 不变；拒绝路径和一次性 guard 在 app 侧。

### 6.7 诊断 payload（已构建）

- 汇编：`patches/iso_burst_uac84_noreport.S`（safe cave 去掉 `iso_report`
  和 `0x2cbe0` hook）；
- payload：29 条（cave + 2 分支 + 18 descriptor + 8 NOP），cave 592/684B；
- NSP：`4fc0247f…`（89445B），工作目录
  `private/analysis/UAC-u2-noreport-20261030`；
- app：`postSeq`、post 前 `burstPosted`、完成后读 `ep+4/+8` 与 entry
  `+16/+32/+40/+44`（`UAC U2 queue` 日志）；
- 边界：`fail_accept` 仍是 safe-accept（返回 0），本版只验证 report 覆盖和
  一次性 post，不是最终拒绝策略；
- **实机一次（2026-10-30 20:29）**：`complete rc=0 requested=3072
  transferred=3072`，report 修复成立；随后第二次 SET_CUR/alt 路径 usb 崩溃
  （同一 map 断言）。build 标 dangerous，已恢复 `52069a44…`。
- **queue-object 修正版（已实机一次，2026-10-31 00:51）**：`56b7f8ee…`
  （89714B，同一 29 条 payload）；`_uacLogQueue` 同时记录 `ep`（0xFC300）和
  `obj`（`0xDB608` 的 table entry）。只发 1 次 SET_CUR，设备未崩溃；但
  `installed=0 table=0`，端点未安装，completion 为空、obj 指针为零——数据
  路径没有被走到。下一步需要把 `installed != 0 && table != 0` 加进 precheck。
- **v3 installed 门（已实机两次）**：`c80fa717…`（89725B，同一 29 条
  payload）；precheck 在 `installed == 0 || table_ptr == 0` 时只记
  `post skipped: endpoint not installed ...` 并返回。第一次 host 停在 alt0，
  门未触发；第二次 `--require-alt1` 先拦截 alt0，`--force-alt1` 显式
  `SET_INTERFACE(1)` 后 `installed=240 table=0xfc0101000027`，门通过，
  completion 3072/3072，无崩溃。
- **v4 patterned burst（已实机三次，2026-10-31）**：`c33d0d07…`（89772B，
  同一 29 条 payload）；一次性 3072B buffer 改为 16 ms/1 kHz 方波。
  第一次 host 已看到 alt1，`--force-alt1` 未发 `SET_INTERFACE(1)`；
  `installed=0 table=0`，门跳过、0 post、WAV 全零。第二次 1→1 重复设置
  回读 alt0，门控退出、未发 SET_CUR。第三次 0→1 后门通过
  （`installed=1 table=0x800501000000`），post/pattern 发生，但 completion
  为空、WAV 全零、无崩溃。**`installed=1` 是部分安装状态，门太弱**。

## 7. 离线验证

### 7.1 静态测试（已完成，除第 4 项）

已实现 `tests/test_uac_u2_queue_compat.py`，从 `usb.elf` 解码并断言：

1. `0x2c520` 在 `blr [vtable+136]` 之前写入 entry（`+32`/`+40`/`+16`）；
2. `0x2c690` 把 transferred 参数加到 `entry+44` 并与 `entry+32` 比较；
3. `0x2cbe0` 是 report 收尾，`iso_report` hook 会覆盖 `x20+16`；
4. 当前 payload 仍包含 `0x2cbe0` 编辑；删 hook 后同一测试应改为断言不存在
   （待 patch）；
5. completion 的 `w4` 来自 `[x5+20] + 192`，等于 3072；
6. `0x2a8b0` 对 attrs `0x05` 返回 0（无 ZLP）。

### 7.2 Unicorn 完成路径仿真（已完成）

`tools/replay_uac_u2_completion.py`：

- 映射 `usb.elf` 的代码段和合成的 endpoint/entry 对象；
- stub `0x30c0`（domain）、`0x4c70`（unmap）、`0x2a8b0`（ZLP 检查）、
  controller `vtable+136`，记录调用参数；
- 固定 `requested=3072`、`transferred=0`、`status=2`、`entry+16=IOVA`，
  调用 `0x2c690(entry, 0, 1, 3072, 1)`：

  预期：
  - `entry+44 == 3072`；
  - `entry+40 == 3`；
  - `0x4c70` 被调用一次，地址等于 `entry+16`；
  - `ep+8` 递减；
  - 无 controller 重提（或按实际语义记录）。

- 再跑 `w4=0`、`w4=192` 作为对照，确认只有 3072 会走 done 分支；
- 如果 `0x4c70` 返回 miss 或 `entry+40` 仍是 2，把结果写进报告，先修
  unmap 再谈 live。

**结果（2026-10-30）**：五组全部通过，报告
`private/analysis/UAC-u2-queue-compat-20261030/completion-replay.json`：

| 组 | transferred | status | unmap | submit | count |
| --- | --- | --- | --- | --- | --- |
| full_force | 3072 | 3 | 1 | 0 | 0 |
| full_no_force | 3072 | 3 | 1 | 0 | 0 |
| partial_force | 192 | 3 | 1 | 0 | 0 |
| partial_retry | 192 | 2 | 0 | 1（2880B） | 1 |
| empty_queue | 0 | 2 | 0 | 0 | 0 |

结论：`0x2c690` 的 full 路径会调用一次 `0x4c70`（地址 = `entry+16`）并把
`count` 清零；partial+force 也会 unmap；只有 partial+no-force 会重提。
因此 H2 只剩“真实 `0x4c70` 在区间树里 miss”这一种可能，需要在下一轮
诊断里单独确认，不能再用“completion 不 unmap”解释。

注意：回放把 entry 初始 status 设为 2（已提交）；`0x2c520` 入队时写的是
1（queued）。full/force 路径不依赖初值（都会写到 3），partial_retry 的
status 保持初值，所以这一组只用于分支判别，不代表真实入队状态。

### 7.3 report 仿真（已完成）

`tools/replay_uac_u2_completion.py --report` 执行真实的 report builder
`0x2c930`（`x0=endpoint`、`x1=report buffer`），用一个已完成 entry：

- `entry+0 id=388`、`+32 requested=3072`、`+44 transferred=3072`、
  `+40 status=3`；
- report buffer 清零后调用，结果：
  `count=1`、`id=388`、`requested=3072`、`transferred=3072`、`status=3`；
- builder 复制后把 entry status 清 0（`entry_status_after=0`）。

报告：`private/analysis/UAC-u2-queue-compat-20261030/report-replay.json`。
结论：**删掉 `iso_report` hook 后，driver 自己生成的 report 正是 app 需要的
`{id, requestedSize, transferredSize, urb_status}` + count=1**；不需要在
cave 里手工拼 report。

### 7.4 构建与回归

- `tools/build_uac_u2_producer.py --check` 复核 cave 大小/编辑数；
- 新 payload 的 `cave_bytes` 必须 ≤ 684；
- `tests/test_uac_u2_queue_compat.py` 与 `tests/test_uac_burst_wav.py` 已加入
  quick suite（23 个文件）；
- `make -C research/usb-ds-iso check` 绿；
- 不访问 USB/SD/硬件。

## 8. 实机验证（两次：2026-10-30 20:29 与 2026-10-31 00:51）

两次均在用户明确“授权，部署”下执行一次。第一次（no-report）：

| 项 | 结果 |
| --- | --- |
| 构建 | `4fc0247f…`（89445B，29 条，cave 592B）；`record=28` 是最后一个索引 |
| precheck | `ok=1 word=0x00c00584 int=4 speed=3 ring=0x59c0f7d000` |
| post | `begin seq=1`、`rc=0x0 urb=388 size=3072` |
| **complete** | **`rc=0x0 requested=3072 transferred=3072`** |
| queue 日志 | `idx=262336` —— 读错对象；`0xFC300+4` 不是 completion 的 table entry，作废 |
| 崩溃 | completion 后 `SET_INTERFACE(0)/(1)`、第二次 SET_CUR 数据阶段 `0xea01`、`EP0 write 0xf601`、usb `User Break`（栈 `0x2c584→0x3ce0→0x40d0`） |
| 判定 | **部分通过**：report/3072B completion 成立；控制/alt 路径仍崩溃，整体不通过 |
| 收尾 | 恢复 `52069a44…`、删日志、安全弹出；无重试 |

原计划（已执行）：

- 一次 boot、一次 alt1、**1–2 次** SET_CUR（不再跑 100 次风暴）；
- 通过条件：
  - 设备 `UAC U2 post rc=0x0`；
  - `UAC U2 complete rc=0x0 requested=3072 transferred=3072`；
  - 无 `post skipped`、无 fatal、无 crash report；
  - host 侧 16/16 个 192B 包；
- 停止条件：任何 fatal / 断连 / 超时；读卡后恢复 `52069a44…`，不重试；
- 不测 PCM、不混短包复测。

第二次（queue-object 修正版，2026-10-31 00:49–00:51）：

| 项 | 结果 |
| --- | --- |
| 构建 | `56b7f8ee…`（89714B，29 条，cave 592B） |
| precheck | `ok=1 word=0x00c00584 int=4 speed=3`，但 **`installed=0 table=0x0`** |
| post | `begin seq=1`、`rc=0x0 urb=388 size=3072` |
| complete | `rc=0x748c requested=0 transferred=0`（空） |
| queue | `ep idx=262336`（仍是 endpoint 对象）；`obj rd=0x0 value=0x0` |
| 宿主 | 只发 1 次 SET_CUR；`GET_CUR=48000`；`failures=0`；无断连 |
| 判定 | **安全但未触发数据路径**：端点未安装，driver 请求/完成路径没走到；precheck 缺 `installed`/`table` 门 |
| 收尾 | 恢复 `52069a44…`、删日志、安全弹出；无重试 |

第三次（v3 installed 门，2026-10-31 00:59–01:01）：

| 项 | 结果 |
| --- | --- |
| 构建 | `c80fa717…`（89725B，29 条，cave 592B） |
| host | `GET_INTERFACE(AS)=0`；2 次 SET_CUR 都在 alt0；`GET_CUR=48000`；`failures=0` |
| 设备 | 2× `UAC U2 skip alt=0`；0 post、0 completion、无 crash |
| 判定 | **未触发**：host 没选中 alt1，installed/table 门没有执行；设备安全 |
| 收尾 | 恢复 `52069a44…`、删日志、安全弹出；无重试 |

第四次（v3 + force-alt1，2026-10-31 01:15–01:17，设备侧通过）：

| 项 | 结果 |
| --- | --- |
| 构建 | `c80fa717…`（89725B，29 条，cave 592B） |
| host | `--require-alt1` 先拦截 alt0；`--force-alt1` 设 alt1、2 次 SET_CUR、`GET_CUR=48000`、恢复 alt0、failures=0 |
| precheck | `ok=1 word=0x00c00584 int=4 speed=3 ring=0x49e537d000`，`installed=240 table=0xfc0101000027` |
| post | `begin seq=1`、`rc=0x0 urb=388 size=3072` |
| **complete** | **`rc=0x0 requested=3072 transferred=3072`** |
| queue | `ep idx=262336`（endpoint 对象）；`obj addr=0xfc0101000027 rd=0xd401`（table pointer 是 handle，不可直接读） |
| 控制路径 | 第二次 SET_CUR 数据阶段仍 `0x25c8c`；无 crash |
| 判定 | **设备侧单次 burst 通过**；host 16/16 包数、PCM 未测；`force-alt1` 是 macOS 的 host workaround |
| 收尾 | 恢复 `52069a44…`、删日志、安全弹出；无重试 |

第五次（v4 patterned burst，2026-10-31 01:25–01:27，门跳过）：

| 项 | 结果 |
| --- | --- |
| 构建 | `c33d0d07…`（89772B，29 条，cave 592B） |
| host | `GET_INTERFACE=1`；`--force-alt1` 因已是 alt1 而没有发 `SET_INTERFACE(1)`；1 SET_CUR；`GET_CUR=48000`；failures=0 |
| precheck | `installed=0 table=0`；`post skipped: endpoint not installed` |
| 设备 | 0 post、0 completion、无 crash |
| WAV | 34816 frames（约 0.73 s），全零；detector FAIL（无 post，预期） |
| 判定 | **未触发**：alt1 状态本身不等于安装器已运行；门正确跳过 |
| 收尾 | 恢复 `52069a44…`、删日志、安全弹出；无重试 |

第六次（v4 重试，2026-10-31 01:41–01:43，1→1 回读 0，未触发）：

| 项 | 结果 |
| --- | --- |
| 构建 | `c33d0d07…`（89772B，29 条，cave 592B） |
| host | 初始 `GET_INTERFACE=1`；`SET_INTERFACE(1)` 返回 0 但回读 alt0；未发 SET_CUR |
| 设备 | 只有 SET_INTERFACE(1/0) 记录；0 post、0 completion、无 crash |
| WAV | 41472 frames，全零；detector FAIL（无 SET_CUR，预期） |
| 判定 | **未触发**：1→1 重复设置不能保持 alt1，必须 0→1 过渡 |
| 收尾 | 恢复 `52069a44…`、删日志、安全弹出；无重试 |

第七次（v4 第三次，2026-10-31 01:47–01:49，门过但空 completion）：

| 项 | 结果 |
| --- | --- |
| 构建 | `c33d0d07…`（89772B，29 条，cave 592B） |
| host | `SET_INTERFACE(0) → SET_INTERFACE(1) → alt1`；1 SET_CUR；`GET_CUR=48000`；failures=0 |
| precheck | `installed=1 table=0x800501000000`；门通过 |
| post | `pattern 1kHz 16ms`；`rc=0x0 urb=388 size=3072` |
| **complete** | **`rc=0x748c requested=0 transferred=0`** |
| WAV | 40960 frames，全零；detector FAIL |
| 判定 | **门太弱**：`installed=1` 是部分安装状态；无 crash，但 completion 空、host 无数据 |
| 收尾 | 恢复 `52069a44…`、删日志、安全弹出；无重试 |

下一步：离线解码安装器在 `manager + 0x14d0 + index*16` 写的字节和 table
tag；要求成功回合的完整值（`0xA2`/`0xF0`）而不是 `!=0`，然后重测 v4
（一次 SET_CUR + WAV）。

## 9. 开放问题

1. **第二次 map 的来源**：H1、H2 还是 H3？no-report 轮只有 1 次 post，
   崩溃在 completion 之后，H2/H3 更可疑；queue-object 轮只发 1 次且端点未
   安装，没有新增数据路径证据。
2. **host alt1 / 安装器**：macOS 可能保持 alt0，也可能显示 alt1 但不运行
   安装器；1→1 的重复设置还会回读 alt0。`--force-alt1` 已做真正的
   `SET_INTERFACE(0) → SET_INTERFACE(1)` 过渡，但 `installed=1` 仍可能只是
   部分安装。需要解码 `manager+0x14d0+index*16` 的字节与 table tag，要求
   成功回合的完整值（`0xA2`/`0xF0`）。产品路径需要标准宿主自然选择 alt1；
   host 侧 16×192 包计数仍未做。
3. **`0x4c70` 是否 miss**：A23 审计已发现 `2c690` 不检查返回值；U2 可能
   同样静默泄漏。若 miss，先修 unmap 参数，再谈 completion。
4. **report count**：driver 的 report 函数是否在 status=3 时写 count=1；
   如果只写 status 不写 count，app 仍会解析失败。
5. **cave 空间**：删除 `iso_report` 后是否真的够；若不够，优先删诊断，
   不要动 TRB 构造。
6. **A23 是否同源**：如果 H2 成立，A23 的 buffer 复用崩溃可能是同一
   unmap 问题；可用同一 Unicorn 模型回归，不额外上硬件。
7. **拒绝路径**：返回 0x1908c 是否一定递归？需要离线重放
   `0x302c0 -> 0x2a980 -> 0x2c690` 的完整链，而不是只看单个函数。

## 10. 决策

- **采用 A**：§7.1/§7.2/§7.3 已完成；no-report 诊断 payload `4fc0247f…`
  no-report 已实机一次：report 修复成立（3072/3072），但 completion 后
  控制/alt 路径仍崩溃，build 标 dangerous、不再部署。queue-object 修正版
  `56b7f8ee…` 实机一次：1 SET_CUR 未崩，但端点未安装（installed=0/table=0），
  空报告，数据路径未走到。v3 `c80fa717…` 两次实机：第一次 host alt=0、门
  未触发；第二次 `--force-alt1` 后门通过、completion 3072/3072、无崩溃，
  设备侧单次 burst 通过。host 16/16、PCM、第二次 SET_CUR 的 `0x25c8c`
  仍待确认；v4 `c33d0d07…` 实机三次：第一次 alt1 但未发 SET_INTERFACE，
  installed=0、门跳过；第二次 1→1 回读 alt0、未发 SET_CUR；第三次 0→1
  门通过（installed=1）但 completion 为空、WAV 全零。**v3/v4 的 installed
  值读错了对象（manager+0x1610），不是安装状态；安装对象是
  `[manager+0x229b8]=base+0x17b038`，见 §11。** v6 `73becbd5…` 改为跟随
  对象读 `+0x1610/+0x1608`，门收紧为 `installed==1 && table!=0`；02:08
  实机一次门通过（`obj=0x40e57b038`，`installed=1`，table 非零）但
  completion 仍为空。空报告问题与门无关，下一步离线查 report/表项/host
  alt1 ISO。拒绝路径仍待单独解决。
- B 仅作为 A 被证伪后的后备；C 不在本轮范围。
- 不恢复 `0x302c0` breaker，不再使用 fake-accept。
- U2 实机线保持暂停；恢复需要新的明确授权。

## 11. 安装对象与 v6 门（离线，2026-10-31）

`0x295d0` 的 8 条 endpoint 安装循环确实只写 `0`/`1`，但**写入对象不是
manager**。`complete_original`（`0x2a980`）的 x0 由调用方从
`manager + 0x229b8` 取出（`0x30294`/`0x30298` 组成 `0x229b8`，
`0x302a8` 执行 `ldr x0, [x21, x22]`，`0x302c0` 调 `0x2a980`）；
`0x2f17c`/`0x2f188` 用同一指针调用 `0x292b0 -> 0x295d0`。因此安装表、
flag 和完成路径都挂在**独立安装对象**上，不是 manager。

两份 2026-10-30 crash report 给出了该对象的实际偏移：

| 报告 | x0（安装对象） | x21（manager） | 差 |
| --- | --- | --- | --- |
| `UAC-u2-precheck2` | `0x712cd7b038` | `0x712ccda000` | `0xa1038` |
| `UAC-u2-burst2` | `0x714857b038` | `0x71484da000` | `0xa1038` |

所以安装对象 = `module base + 0x17b038`（`manager + 0xa1038`）。对 EP `0x84`
（`0x3a30(0x84) = 0x14`）：

- flag：`对象 + 0x14d0 + 0x14*16 = 对象 + 0x1610` = `base + 0x17c648`；
- 表项指针：`对象 + 0x14c8 + 0x14*16 = 对象 + 0x1608` = `base + 0x17c640`。

此前 precheck 读 `manager + 0x1610`（`base + 0xdb610`）和
`manager + 0x1608`（`base + 0xdb608`），读到的是 manager 内无关字节；
`installed=0/1/0x90/0xa2/0xf0` 的跳变正是这个原因。v3/v4 的
“`installed=1` 是部分安装”结论作废；成功回合的 `installed=240` 也只是
碰巧非零，不能当判据。

v6（2026-10-31 02:08 实机一次）：`73becbd5…`（90174B，同一 29 条
payload / cave 592B）。
- 先读 `[manager + 0x229b8]` 得到对象指针，再读 `+0x1610/+0x1611/+0x1608`；
- 门：`install_ok && installed == 1 && table != 0`；
- manager 旧值 `0xdb610/0xdb608` 只写日志，绝不参与门；
- 超时/无完成/报错时读 `[obj+0x1608]` 的表项：`+0x10` IOVA、`+0x20`
  requested、`+0x28` status、`+0x2c` transferred；
- **v6 实机**：`obj=0x40e57b038`、`installed=1`、`table=0x40e5796f0`，
  门通过、post `rc=0`，但 completion 为空 `0x748c/0/0`，WAV 全零，无 crash。
- **v7 实机（只加 report 日志）**：同一对象/门，
  `report count=1 id=388 req=3072 xfer=3072 status=3`、
  `complete rc=0 3072/3072`，v6 空报告未复现；但 WAV 仍全零。
- **host 内核（v7）**：143 个 EP `0x84` IsochronousRequest 以
  `0xe00002ed`（transaction error / not responding）完成，abort 29/31/16
  个请求。不过 host engine 到 02:20:07.788 才 `starting`，触发在
  02:20:04–05，16 ms burst 早于真正的流启动；WAV 只有 0.86 s。错误包含
  启动期失败，不能先断定端点已死；cave 的 3072 是 16×192 记账，不是
  host 数据。下一步先做延迟触发的 host 时序实验；若 WAV 仍零，再查
  EP `0x84` 的 ISO 端点/ED/TRB。U2 实机线暂停，需新的明确授权。

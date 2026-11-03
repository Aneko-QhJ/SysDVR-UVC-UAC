# UAC U2 宿主侧 xHCI 追踪计划（v29w，2026-11-03）

> 目的：v29v 长跑证明设备侧稳态已到边界——每 ~1.5 s 一次**两帧**
> Missed Service（code 23），每次 ~80 ms 静音、丢 1–2 套。设备看不到
> 那两帧为什么没被服务，所以要到**宿主内核**里看。本文件是 item (b)
> 的采集与分析计划；item (a)（非 VM 宿主对照）排在其后。

## 为什么看 xhci-hcd

- 设备的 code 23 是控制器报的“这一帧的 TD 没被及时服务”；从宿主看，
  等价于**这一帧没有发出 IN token**。
- guest 的 xHCI 是 Parallels 模拟的，驱动仍是 Linux `xhci-hcd`；它自带
  tracepoint，能看到每个 TRB 的入队/完成与每个 URB 的 giveback 实际长度。
- 如果 guest 侧也出现 `actual < 3072` 的 ISOC URB、且节律与设备侧的
  code 23 一致（~1.5 s 一次、每次少 384 B = 两帧），就能把“漏服务”落到
  宿主的 URB 调度上，而不是设备环形状。

## 采集（guest 内，一次运行）

```sh
cd /sys/kernel/tracing
echo 0 > tracing_on; echo > trace
echo 16384 > buffer_size_kb            # per-CPU；2 vCPU ≈ 32 MB
for t in xhci_urb_enqueue xhci_urb_giveback xhci_handle_transfer; do
    echo 1 > events/xhci-hcd/$t/enable
done
echo 1 > tracing_on
# 同一轮的 probe（约 5 s）
sudo ./uac-raw-probe --trigger-first --delay-ms 30 --packets 16 --transfers 8 \
     --rearm --max-urbs 512 --timeout-ms 10000 --keep-alt > /tmp/v29w-host.txt 2>&1
echo 0 > tracing_on
for t in xhci_urb_enqueue xhci_urb_giveback xhci_handle_transfer; do
    echo 0 > events/xhci-hcd/$t/enable
done
cp trace /tmp/v29w-trace.txt
grep -c . /tmp/v29w-trace.txt
```

读回时把 `trace` 与 probe 输出一起取回（gzip + base64），并用
`tools/analyze_xhci_iso_trace.py` 解码。

## 分析（本机）

```sh
python3 tools/analyze_xhci_iso_trace.py private/runs/<run>/xhci-trace.txt --json
```

输出：ISOC URB 的 enqueue/giveback 数、**short URB 数**与最大缺口、
`actual/length` 列表、按 ring 类型分组的 transfer event 数与“length 0”
事件数。判定：

| 观察 | 结论 |
| --- | --- |
| short URB 数 ≈ code 23 事件数（3 个 384 B 缺口），时间点均匀分布 | 宿主 URB 层就是漏服务的来源 → 在 guest 侧查 URB 补投/结束处理 |
| 没有 short URB（全部 3072） | 宿主把每帧都“完成”了（设备回 ZLP）→ 漏服务发生在控制器取指，不在 URB 层 |
| transfer event 里有大量 length 0 | 控制器对那几帧没有数据可给，进一步支持“没发 IN token” |

## 已知限制

- trace 行的 TRB 解码**不含 slot/endpoint**，所以对 transfer event 只能
  按 ring 类型（ISOC）粗筛；URB 行带 `ep84in-isoc`，可作为精确锚点。
- 设备日志没有时间戳，无法逐帧对齐；比较的是**节律与数量**，不是同一帧。
- 采集会带来 ftrace 开销（~2000 事件/s），可能轻微改变时序；短跑（5 s）
  可接受，若 short URB 变成 0 需与无追踪的 v29v 结果对照。

## 后续（item a）

若 (b) 指向宿主 URB/控制器时序，再比较非 VM 宿主（或 guest 里用
`usbfs` 直接提交、不经 libusb 的定时器）看 code 23 频率是否变化；设备侧
不再改这个形状。

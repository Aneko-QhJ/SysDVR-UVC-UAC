# UAC U2 宿主侧 xHCI 追踪计划（v29w，2026-11-03）

> 目的：v29v 长跑证明设备侧稳态已到边界——每 ~1.5 s 一次**两帧**
> Missed Service（code 23），每次 ~80 ms 静音、丢 1–2 套。设备看不到
> 那两帧为什么没被服务，所以要到**宿主内核**里看。本文件是 item (b)
> 的采集与分析计划；item (a)（非 VM 宿主对照）排在其后。

## 2026-11-03 20:4x 修正：设备在 EHCI，不在 xHCI

第一次采集（v29w）开了 `xhci-hcd` 的三个 tracepoint，跑完 trace 是空的。
查 `lsusb -t` 才看清：

```text
Bus 001: root_hub  Driver=ehci-pci/15p, 480M
    |__ Port 001: Dev 004, If 3, Class=Audio, 480M      <- SysDVR UAC
Bus 002/003: Driver=xhci_hcd                           <- 键盘鼠标
```

**设备挂在 Bus 001，控制器是 `ehci-pci`（USB 2.0），xhci 的 tracepoint
永远不会看到它。** 而且内核没有 ehci-hcd 的 tracepoint
（`/sys/kernel/tracing/events/` 里只有 `xhci-hcd`）。

## 改用 usbmon（bus 1）

`modprobe usbmon` 之后 `/sys/kernel/debug/usb/usbmon/1u` 给出每个 URB 的
submit/complete 行，ISO 也在内，格式（实测）：

```text
ffff0000744e8cc0 1085935422 S Ii:1:001:1 -115:2048 4 <
ffff000003565300 1085935273 C Ci:1:001:0 0 4 = 07050000
```

- submit：`<status>:<请求长度> <interval>`；
- complete：`<status>[:<未传输包数>] <实际长度>`。
- ISO 完成行的冒号后缀就是**没被传输的包数**——正是“那两帧”，实际长度
  会少 384 B。

采集：

```sh
sudo modprobe usbmon
(sudo timeout 12 cat /sys/kernel/debug/usb/usbmon/1u > /tmp/usbmon1.txt) &
sleep 1
sudo ./uac-raw-probe --trigger-first --delay-ms 30 --packets 16 --transfers 8 \
     --rearm --max-urbs 512 --timeout-ms 10000 --keep-alt > /tmp/v29w-host.txt 2>&1
wait
grep -c " Ii:1:004:4" /tmp/usbmon1.txt
```

分析：

```sh
python3 tools/analyze_xhci_iso_trace.py private/runs/<run>/usbmon1.txt \
        --format usbmon --bus 1 --ep Ii:1:004 --json
```

判定与之前相同：出现与 code 23 同节律的 384 B 缺口（complete 行长度
2688、冒号后缀 2）→ 宿主 URB 层；所有完成行都是 3072 → 控制器取指层。

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

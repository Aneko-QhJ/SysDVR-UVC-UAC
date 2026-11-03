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

## 2026-11-03 21:1x 实测：usbmon 文本 API 不够，改用 probe 自身的 per-packet

v29x 一次：`modprobe usbmon`、`cat /sys/kernel/debug/usb/usbmon/1u` 后台采集，
跑同一条 probe（host 770112 B / 250.7 套）。

- usbmon 抓到的 512 个 ISO URB 全部出现在 **`Zi:1:004:4`**（usbmon 把端点
  标成 interrupt，是 alt setting 视角问题，功能无影响），**512 个 URB 的
  总体 status 都是 0**——宿主 URB 层没有“短传输”这一信号。
- 文本 API 每个 URB **只打印前 5 个 ISO packet 描述符**，也不打印实际
  URB 长度；设备的丢失帧落在槽 5–14，**在文本里看不见**。
- 那 5 个描述符里约一半是 `-71/0`（EPROTO、0 字节），但它们主要来自
  训练结束后的 URB（probe 会提交满 512 个 = 8.2 s，训练只有 4.4 s），
  不能当作漏帧证据。

所以 (b) 改到**最直接的观测点：libusb 自己**。`host/uac-raw-probe.c` 新增
`packet_detail()`：对“丢了 1–4 个包、其余正常”的 URB（正是 miss 的形状）
打印每个未完成包的 `<index>=<status>/<len>`，最多 48 行。下一轮在 guest 里
重新编译该文件再跑同一镜像：

```sh
cc -std=c11 -Wall -Wextra -Werror -o uac-raw-probe2 uac-raw-probe.c -lusb-1.0
sudo ./uac-raw-probe2 --trigger-first --delay-ms 30 --packets 16 --transfers 8 \
     --rearm --max-urbs 512 --timeout-ms 10000 --keep-alt
```

判定：出现 `urb[N] detail p13=-71/0 p14=-71/0` 这种**尾部成对**丢失 →
宿主在 URB 边界漏服务；**分散**或单个 → 另一回事；没有 detail 行但设备仍
报 code 23 → 漏在控制器取指层，宿主 URB 完全不知情。

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

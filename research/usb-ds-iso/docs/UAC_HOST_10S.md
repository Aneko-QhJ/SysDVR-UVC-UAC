# UAC 标准宿主 10s PCM 验证入口（2026-10-29 准备）

目标：在 Linux 标准 `snd-usb-audio` 宿主上，用 48 kHz / 2ch / S16_LE
捕获 SysDVR-UVC 的 UAC AS alt1，连续 10s，无 xrun、无截断、无重连。
本页只定义入口、检查清单和当前设备侧缺口；**没有启用 UAC、没有实机**。

## 分阶段（U0 → U4）

| 阶段 | 内容 | 通过条件 |
| --- | --- | --- |
| U0 | UAC 枚举 | `lsusb`/`dmesg` 出现 AC+AS；`arecord -l` 出现 capture card |
| U1 | AC/AS 控制 | 采样率 48k 的 GET/SET、AS alt0/alt1 `SET_INTERFACE` 均可 ACK |
| U2 | 单 URB | AS alt1 端点打开，host 收到 16×192B = 16ms 数据 |
| U3 | 短 PCM | 1s 捕获，采样率/声道/位深正确，无 xrun |
| U4 | 10s PCM | 10s 捕获，0 xrun、无截断、跨块样本连续、无重连 |

当前只准备 U0–U4 的 host 入口；设备侧 U0 还没有 build。

## 当前设备侧缺口

| 缺口 | 现状 |
| --- | --- |
| `_setupAudioInterfaces5x` | 已实现但 **未调用**，UAC 仍禁用 |
| AC/AS SetupEvent | `_processRequests` 未轮询 AC/AS，控制请求不会到达 `UacStandardHandle` |
| AS 端点 `0x84` | 只注册，未接 ISO producer；A23 hook 只匹配 `0x83` |
| PCM 发送器 | `UacDeviceSendAudio` 是逐 192B post + 等完成，不是 16ms URB/3 条在飞 |
| 接口预算 | UVC 2 + AC/AS 2 = 4；UAC build 不能带 `ISO_PROBE` |
| alt1 安装 | 需要 NOP patch；全局 NOP 只用于实验 |

因此 UAC 标准宿主 10s 不能直接复用当前 A23 诊断 build；下一项设备工作应是
**UAC 枚举探针**（U0），确认 AC/AS/alt1 能被标准宿主看到，再谈 PCM。

## Host 入口

在 Linux 上，设备已运行、USB 已连接后：

```sh
make -C research/usb-ds-iso/host  # 不需要，host 只使用 ALSA
research/usb-ds-iso/tools/uac_host_10s.sh \
  --out /tmp/uac10s --device hw:1,0 --seconds 10
```

脚本会保存：

- `arecord-list.txt`、`lsusb.txt`、`dmesg.txt`、`asound-cards.txt`
- `uac.wav`、`arecord.log`、`check.json`、`host.log`

`--device` 省略时按 `arecord -l` 中的 `SysDVR` 自动选择；多个匹配会要求
显式指定。

## 检查清单

| 检查 | 命令/文件 | 通过标准 |
| --- | --- | --- |
| 枚举 | `lsusb -v -d 1209:ca57` | AC/AS 接口、alt0/alt1、EP `0x84` ISO |
| 音频卡 | `arecord -l` | 出现 SysDVR capture card |
| 内核 | `dmesg` | 无 `cannot set freq`、`usb ... error`、断开重连 |
| 10s 捕获 | `arecord ... -d 10` | 退出 0，WAV 非空 |
| 格式 | `check_uac_wav.py` | 48000/2ch/16bit，frames≈480000 |
| 连续性 | `check.json` | 无 `truncated_data`；warnings 为空或可解释 |
| xrun | `arecord.log` | 无 `overrun`/`underrun`（ALSA 可能不打印，需结合时长） |

`check_uac_wav.py` 只验证容器和简单统计；静音/大跳变作为 warning，不直接判失败。

## 停止条件

- 枚举失败或 dmesg 出现 UAC/ISO 错误；
- `SET_INTERFACE(1)` stall、端点打开失败；
- 10s 内 xrun/截断/重连；
- 设备 usb fatal 或状态未知。

失败不重试；保存 `uac10s/`、设备 log、`dmesg`，恢复安全 build 后离线分析。

## 下一步（离线）

1. 给 `_setupAudioInterfaces5x` 加 `UAC_HOST_PROBE` 编译开关，只做 U0（枚举 +
   AC/AS 控制），不启动 PCM 线程；
2. 在 `_processRequests` 轮询 AC/AS SetupEvent；
3. 用 QEMU/真实 Linux 主机做 U0；通过后再设计 AS `0x84` 的 ISO producer；
4. 最后才是 U2–U4 的 10s PCM。

在这些完成前，UAC 仍保持禁用。

## U0 枚举候选（2026-10-29 离线构建）

- NSP：`private/analysis/UAC-host-probe-20261029/outputs/exefs.nsp`
  SHA256 `3c3bf1458f29a592497c369452eed6269cfcc743eb5ebb056a4b7ef6b06670fc`
  （83942B）；
- 构建：

  ```sh
  make -B -j4 TARGET=exefs \
    BUILD=research/usb-ds-iso/private/analysis/UAC-host-probe-20261029/objects \
    OUTPUT_DIR=research/usb-ds-iso/private/analysis/UAC-host-probe-20261029/outputs \
    DEFINES="-DUAC_HOST_PROBE -DFILE_LOGGING"
  ```

- 行为：`_setupAudioInterfaces5x` 在 VC/VS 之后调用一次；AC/AS SetupEvent
  在 `UvcDeviceProcessRequests` 和 `waitMulti` 中轮询；音频线程保持 idle
  （`UacDeviceIsStreaming()` 在 `UAC_HOST_PROBE` 下返回 false）；不发送 PCM。
- 不包含 `ISO_PROBE`/runtime patch/NOP；AS `0x84` alt1 的安装能力本轮不验证，
  它属于 U1/U2。
- **未部署、未开机**。U0 只需标准宿主看到 AC/AS 和音频卡；如果 init 在
  `_setupAudioInterfaces5x` 失败，设备日志会给出错误码，读卡后恢复安全版本。

### U0 host 检查

macOS（当前 Mac 即可，不做 PCM）：

```sh
system_profiler SPUSBDataType -json > u0-usb.json
ioreg -p IOUSB -l -w0 > u0-iorg.txt
system_profiler SPAudioDataType -json > u0-audio.json
```

Linux：

```sh
lsusb -v -d 1209:ca57 > u0-lsusb.txt
dmesg | tail -n 200 > u0-dmesg.txt
arecord -l > u0-arecord-list.txt
cat /proc/asound/cards > u0-asound-cards.txt
```

通过：AC/AS 接口和音频 capture card 出现，dmesg 无 UAC/ISO 错误。
失败：无 AC/AS、init 错误、crash；不重试，读卡并恢复 `52069a44…`。

## U0 首次实机（2026-10-29 18:13，macOS）

- 设备日志：`UAC initialized: AC=2 AS=3 EP=0x84`，`UVC device initialized`；
  **没有** `USB host connected`，也没有 EP0 请求记录。
- macOS：`ioreg` 看到 `SysDVR-UVC Capture`（IOUSBHostDevice），但
  `system_profiler SPAudioDataType` 没有出现 UAC 音频设备；
  `SPUSBDataType -json` 只返回空数组。
- 判定：**U0 未通过**。设备侧 UAC 初始化成功，但主机没有配置/绑定新的复合
  配置；需要确认是 macOS 对 UVC+UAC 复合配置的拒绝，还是 UAC 描述符/接口
  问题。
- 下一次 U0 应使用更丰富的主机记录：`ioreg -r -c IOUSBHostDevice -l`、
  `ioreg -r -c IOUSBHostInterface -l`、macOS `log show` 中的
  `AppleUSBHost`/`AppleUSBAudio` 错误，或直接换 Linux `lsusb -v`/`dmesg`。
- 证据：`private/runs/UAC-u0-20261029/`（`device-log-u0.txt` `645f12d7…`、
  `iorg.txt`、`audio.txt`、`run.json`）；卡已恢复 `52069a44…`。

## U0b 离线修正（2026-10-29 18:18）

针对 U0 的“USB 设备出现但无音频设备/无 host-connected”做了两处离线修正：

1. **Audio IAD `bFunctionSubClass` 从 1 改为 0**。IAD 的 `bFunctionSubClass`
   应表示 audio function（0），不是 AC 接口的 subclass（1）；lint 同步修正，
   测试新增 `ac[4]==1 && ac[5]==0` 断言。
2. **先 append/register 全部 AC+AS 描述符和 AS 端点，再 enable AC/AS**。
   旧顺序先 `EnableInterface(AC)`，再 append AS 描述符/注册端点，可能让 host
   看到不完整的 audio function。

- 候选 NSP：`private/analysis/UAC-host-probe-20261029-r2/outputs/exefs.nsp`
  SHA256 `bdae4cd606ec11e26ec81c680e410309461e57b6f4bab73353118b71256d5759`
  （83929B）；
- 仍无 ISO producer/PCM，仍是 U0 枚举候选；
- 下一次主机会抓 `ioreg -r -c IOUSBHostInterface`、`IOUSBHostPipe`、
  `system_profiler SPUSBDataType` 文本和 `log show` 的 USB/audio 记录，
  以区分“host 未配置”与“audio driver 未绑定”；
- **未部署、未开机**。

### U0b 实机结果（2026-10-29 18:20，macOS）

- 设备日志仍是 `UAC initialized: AC=2 AS=3 EP=0x84`，**没有**
  `USB host connected`/EP0 记录；
- `ioreg -c IOUSBHostInterface` 没有 SysDVR 的 AC/AS 接口块；
- `system_profiler SPAudioDataType` 没有音频设备；
- U0b 的 IAD subclass/enable 顺序修正 **没有改变** host 不 configure 的结果。

因此下一步先不继续猜描述符，而是直接读配置：

- 新增 [host/usb-config-dump.c](../host/usb-config-dump.c)：libusb 只读打印
  device/config/interface/alt/endpoint 及 class-specific extra，不 claim、不选配置。
- U0c 主机脚本会先跑 `usb-config-dump`，再抓 ioreg/audio/log。
- 判别：配置里若已有 AC/AS 和 `0x84` alt1，问题在 host 类驱动/复合配置；
  若缺 AC/AS，问题在设备 append/配置描述符。

### U0c 配置描述符结果（2026-10-29 18:25）

- 主机 `ioreg` 仍只看到 `SysDVR-UVC Capture` USB 设备；
- `usb-config-dump` 无法打开设备（`0xe00002d8`，host 侧 open 失败）；
- macOS 内核日志给出关键错误：

  ```
  SysDVR-UVC Capture: IOUSBHostDevice::getDescriptorGated:
    type 0x02 index 0 length 9: completed with 0xe00002cd ...
  ```

  `0xE00002CD` 是 `kIOReturnNotReadable`：**host 读不到配置描述符**。
- 同一 `usb-config-dump` 对 safe build 能读出 `wTotalLength=185`、3 接口、
  vendor alt1 EP83；因此工具和 USB 链路正常。
- 设备日志仍是 `UAC initialized: AC=2 AS=3 EP=0x84`，无 `USB host connected`。

结论：问题在设备/usb:ds 侧无法提供新的 UAC 复合配置描述符，不是 macOS
音频类驱动绑定。下一步做隔离构建，按信息量排序：

1. **UAC-only**（跳过 UVC VC/VS，只注册 AC/AS）：配置只有 ~97B；
   能读 → 组合/长度/第二 IAD 问题；不能读 → UAC append 本身问题。
2. **去掉 UAC IAD**：验证 usb:ds 是否不接受第二个 IAD。
3. **只保留 AS alt0（不注册 alt1 端点）**：验证 alt1 端点/描述符。

在这三个分支之前，不再重复部署同一个 U0b。

## UAC-only 隔离候选（2026-10-29 18:29 构建）

- NSP：`private/analysis/UAC-only-probe-20261029/outputs/exefs.nsp`
  SHA256 `7ffdf7338aa3b92a326f6b21dfe8c8849dc1a5993ee48833af0035a88bce7329`
  （81293B）；
- 构建：`-DUAC_HOST_PROBE -DUAC_ONLY -DFILE_LOGGING`，无 UVC VC/VS，
  仅 AC/AS（接口 0/1），配置约 97B；
- 目的：如果这个纯 AC/AS 配置能被 `usb-config-dump` 读出，说明问题在
  UVC+UAC 组合/长度/第二 IAD；如果仍不可读，说明 UAC append 本身或
  usb:ds 不接受该配置。
- **未部署、未开机**。

后续如果 UAC-only 可读，再做“去 UAC IAD”和“AS alt0-only”两个变体。

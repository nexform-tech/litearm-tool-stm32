# litearm-tool-stm32 设计文档

日期：2026-09-07
状态：已与用户逐段确认

## 1. 背景与目标

参考 `/home/llx/dm-tool`（达妙 DM 电机的 PyQt5 桌面调试工具，SocketCAN 直连），为
`/home/llx/litearm-stm32` 固件新做一个对等体验的上位机工具，能够读取电机状态并执行
基础控制与运动下发。

与 dm-tool 的关键差异：litearm-stm32 固件**独占电机 CAN 域**（gs_usb 桥只放行末端
工具帧，电机 ID 0x01–0x07/0x11–0x17 被固件 FDCAN 过滤器拦截），上位机**不能**直接
走 can0 读电机。正确通道是固件的 USB CDC 命令口：

- 设备：复合 USB（gs_usb + CDC VCP），VID:PID `1d50:606f`，Linux 下 `/dev/ttyACM0`
- 协议：`SOF(0xA5) | CMD(1B) | LEN(1B) | PAYLOAD(0..255B) | CRC16(2B, LE)`，
  CRC16-CCITT-FALSE（poly 0x1021, init 0xFFFF），float 一律 float32 LE
- 固件上电即以 100Hz 主动推送 `RSP_STATUS(0x40)`，被动读取即可获得全部电机状态

**安全架构底线（用户明确要求）**：所有硬防护（软限位、命令通道斜率限制、NaN/非法值
拒绝、看门狗 fail-soft、急停兜底）的权威在 STM32 固件，这是必须的、不可移到上位机。
本工具不复刻、不削弱、不替代任何固件防护，只做固件防不了的"操作意图"层交互防护
（防手滑输错数量级等"合法但非本意"的命令）。

## 2. 需求定案（用户已逐项选择）

| 项 | 决定 |
|---|---|
| 形态 | PyQt5 桌面 GUI（对标 dm-tool） |
| 功能范围 | 全功能：监控 + 基础控制 + 运动指令下发 |
| 位置 | 新建独立目录 `/home/llx/litearm-tool-stm32`（独立 git 仓库） |
| 运动安全交互 | 强防护：页面锁定+确认勾选、Δq 确认框、常驻急停 |
| 实时曲线 | 要，pyqtgraph 滚动示波 |
| 打包 | 第一版源码运行，目录结构按可 PyInstaller 打包组织 |

## 3. 代码组织（方案 B：小型分层包）

```
litearm-tool-stm32/
├── main.py                 # 唯一入口
├── requirements.txt        # PyQt5, pyserial, pyqtgraph, PyYAML
├── README.md               # 使用说明 + 真机手工验收清单
├── config.yaml             # 可选：confirm_threshold 等交互参数（无本地限位表）
├── litetool/
│   ├── protocol.py         # 帧编解码（纯函数，无 IO）
│   ├── transport.py        # 串口发现 + SerialLink 后台读线程
│   ├── client.py           # LiteArmClient 高层 API
│   ├── checks.py           # Δq 计算与确认逻辑（意图层，唯一"安全"模块）
│   └── gui/
│       ├── main_window.py  # 顶栏/Tab/日志面板骨架
│       ├── monitor_page.py
│       ├── plot_page.py
│       ├── control_page.py
│       └── motion_page.py
└── tests/                  # pytest，无硬件可跑
```

协议代码从 `litearm-stm32/tools/arm_audit.py`（最新、经审计的 G8 帧格式解码器）
**移植拷贝**，不做跨仓库运行时依赖；`SerialLink` 线程架构借鉴
`litearm-stm32-python`（其 protocol.py 帧格式已过时，不采用）。

## 4. 架构与数据流

三线程模型：

```
读线程(transport) --frames--> LiteArmClient --Qt signal(≤20Hz节流)--> GUI主线程
                                    ^--- 命令调用(互斥锁, send_and_wait_ack)
```

- **读线程**：独占串口读；帧解析状态机（SOF 重同步→CMD/LEN→payload→CRC 校验）；
  容忍开机文本 banner（`"[litearm-usbcdc] ready"`，非帧格式）与半帧粘包。
- **写路径**：GUI 调 `client.xxx()` → `send_and_wait_ack(cmd, timeout=0.5s)` 用
  `threading.Event` 配对 `RSP_ACK(0x45)/RSP_ERR(0x46)`；互斥锁保证同一时刻最多
  一个未完成命令。
- **状态流**：`RSP_STATUS` 解码后写入 client 最新状态缓存，Qt signal 通知 GUI；
  GUI 刷新节流 ~20Hz；曲线数据按 100Hz 全量入环形缓冲（不抽稀）。
- **离线判定**：>500ms 未收到状态帧 → 离线态：顶栏变红、全部命令按钮禁用、曲线
  冻结在最后值。第一版不做自动重连，提供手动"重新连接"。
- **关节数自适应**：连接后由首帧状态长度定 N（`(len-4)/21`），兼容 7 关节整机
  （151B）与 1 关节测试台（25B），GUI 表格行数随 N 生成。

## 5. 协议层（protocol.py）

命令表（源自固件 `User/litearm/hal/usb_cmd.h`，只列本工具用到的）：

| CMD | ID | Payload | 响应 |
|---|---|---|---|
| MOVE_J | 0x01 | q[N]f32 + speed f32 | ACK/ERR |
| MOVE_JS | 0x03 | q[N]+dq[N]f32 (+可选 tau_ff[N]) | ACK/ERR |
| MOVE_MIT | 0x04 | idx u8 + q,dq,kp,kd,tau f32 | ACK/ERR |
| MOVE_MIT_ALL | 0x05 | q,dq,kp,kd,tau 各[N]f32 | ACK/ERR |
| ENABLE | 0x10 | — | ACK/ERR(0x03 未就绪) |
| DISABLE | 0x11 | — | ACK |
| EMERGENCY_STOP | 0x12 | — | ACK |
| CLEAR_FAULTS | 0x13 | — | ACK |
| RESET | 0x14 | — | ACK |
| SET_SPEED_PERCENT | 0x21 | 0–100 u8 | ACK |
| HOME | 0x2A | — | ACK |
| GET_STATUS | 0x40 | — | 立即触发一帧 RSP_STATUS |
| GET_FIRMWARE | 0x41 | — | RSP_FIRMWARE(0x44) ASCII |
| GET_TCP | 0x43 | — | RSP_TCP(0x48) pos[3]+rpy[3]f32 |

RSP_STATUS(0x40) payload（G8 格式，`4+21·N` 字节）：

| 偏移 | 字段 | 类型 |
|---|---|---|
| 0 | flags | u16 LE：bit0–5 = FAULT/WD_TRIPPED/FB_STALE/TEMP_WARN/POS_VIOL/OVERSPEED；bit6–8 = mode(INIT/MOVE_J/MOVE_P/MOVE_JS/MOVE_MIT/MIT_ALL/EMERGENCY) |
| 2 | seq | u16 LE（丢帧检测） |
| 4+21·i | q, dq, tau, t_mos, t_coil | 5×f32 LE |
| 24+21·i | err | u8（DM 电机状态码） |

ERR 错误码：0x01 载荷过短 / 0x02 数值非法(NaN/超限，固件已拒绝) / 0x03 未就绪 /
0x04 需先 disable / 0x05 忙 / 0x00 未知命令。

接口：`build_frame(cmd, payload) -> bytes`、`FrameParser.feed(bytes) -> [(cmd,
payload)]`、`decode_status/ack/err/firmware/tcp(payload)`。

## 6. 安全交互层（checks.py + motion_page）

**不做**（信任固件，避免重复建设与虚假安全感）：本地软限位 clamp、速度上限
clamp、kp/kd/tau 范围 clamp、NaN 拦截。输入值直接下发；固件拒绝时把 ERR 码翻译成
中文显示（如 `ERR 0x02: 数值非法(NaN/超限)，固件已拒绝`）。

**保留**（固件防不了的人为失误，纯交互层）：

1. **运动页默认锁定**：进入时下发按钮全部 disabled，黄色横幅"运动控制已锁定"；
   解锁需同时满足：勾选"我已确认机械臂周围无障碍、急停可及" + 在线且收到过状态帧；
   断线/急停事件立即重新锁定并清空勾选。
2. **Δq 确认框**：move_j/move_mit 下发前计算每关节 |target−current|，任一关节超过
   `confirm_threshold`（默认 0.5 rad，config.yaml 可调）时弹窗逐关节列出
   "J2: 当前 0.12 → 目标 1.40（Δ1.28 rad）"，确认后才发送。
3. **常驻急停**：顶栏红色大按钮，任何页面可见；一键发 EMERGENCY_STOP，无确认框；
   触发后重新锁定运动页并记日志。
4. **不提供连续 MIT 循环**：move_mit 只发单帧，避免上位机成为 100Hz 控制源。

**控制页**（风险低，无需解锁）：enable/disable/clear_faults/home/reset 按钮（等
ACK，ERR 显示中文含义）；enable 前若 FAULT flag 置位则提示先 clear_faults；
speed_percent 滑块(0–100)；GET_TCP 显示末端位姿；连接后自动 GET_FIRMWARE 显示
版本于顶栏。

## 7. GUI 布局

```
┌────────────────────────────────────────────────────────────┐
│ [串口▼] [连接] ●在线 Litearm1.4.0-7J            [急停(红)]   │
├────────────────────────────────────────────────────────────┤
│ Tab: 监控 | 曲线 | 控制 | 运动                                │
├────────────────────────────────────────────────────────────┤
│ 日志面板（暗色控制台风格，时间戳，可清空/暂停滚动）               │
└────────────────────────────────────────────────────────────┘
```

- **监控页**：状态条（模式 + 6 个安全 flag 指示灯 + seq 丢帧计数 + 实测帧率）+
  状态表格 N 行 × `q(rad)|dq(rad/s)|tau(Nm)|T_mos(°C)|T_coil(°C)|err`；20Hz 刷新；
  超温(>85°C)黄色高亮、err≠0 或故障 flag 红色高亮；坏帧计数显示。
- **曲线页**：pyqtgraph 三个联动子图（q/dq/tau），每关节一条曲线；"关节×字段"
  勾选矩阵选通道；30s 滚动窗口（100Hz×3000 点环形缓冲）；[冻结] 按钮。不做导出。
- **运动页**：move_j（N 个目标输入 + speed + 下发）、move_mit 单关节（idx 下拉 +
  q/dq/kp/kd/tau）、锁定横幅与解锁勾选、Δq 确认框。

串口权限：普通用户 + dialout 组即可（无需 root，优于 dm-tool 的 SocketCAN）。

## 8. 错误处理

- ERR 码中文映射表统一在日志与状态栏显示。
- ACK 超时（500ms）→ 日志警告 + 状态栏提示，不弹模态窗。
- 串口拔出异常 → 离线态（见 §4）。
- CRC 错帧/banner → 静默重同步，累加坏帧计数。
- 读线程内所有异常兜底 catch，通过 signal 上报 GUI，不允许线程崩溃静默失联。

## 9. 测试策略

pytest（无硬件可跑）：

- `protocol.py`：build/feed round-trip；CRC16 与固件 golden 字节比对；G8 状态帧
  解码（151B 7 关节、25B 1 关节）；粘包/半包/banner 混入重同步；LEN 与实际不符。
- `checks.py`：Δq 阈值触发/不触发、多关节取最大。
- `client.py`：mock 串口测 ACK/ERR 配对、超时、离线判定、命令互斥。
- GUI：README 附真机手工验收清单（连接→监控→曲线→enable→move_j 小幅→急停→锁定
  复位 的完整步骤）。

## 10. 第一版明确不做（YAGNI）

- 自动重连、PyInstaller 打包（结构预留）、曲线数据导出、寄存器级电机配置
  （波特率/ID 改写——固件架构下上位机无此通道）、多设备同时连接、Windows 适配
  验证（协议层兼容，仅串口枚举按 Linux 优先）。

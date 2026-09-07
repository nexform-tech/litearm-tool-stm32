# LiteArm Tool STM32

LiteArm 运控固件（`litearm-stm32`，STM32H723）的桌面上位机工具。参照 `/home/llx/dm-tool`
的交互风格，走 **USB CDC 命令口**（非 SocketCAN——电机 CAN 域被固件独占），提供电机状态
监控、实时曲线、基础控制与运动指令下发。

- 传输：板载复合 USB（gs_usb + CDC VCP），VID:PID `1d50:606f` → `/dev/ttyACM0`
- 协议：`SOF(0xA5) | CMD | LEN | PAYLOAD | CRC16-CCITT-FALSE`，协议实现移植自
  `litearm-stm32/tools/arm_audit.py`（最新 G8 状态帧布局，经固件审查）

## 安全模型（重要）

**一切硬防护的权威在固件**：斜率限制、软限位、NaN/非法值拒绝、看门狗 fail-soft、
急停兜底均由 STM32 承担，不依赖上位机在线与否。本工具**不**复刻这些防护。

工具只承担固件防不了的**操作意图**层：

1. **运动页默认锁定**，需勾选"已确认机械臂周围无障碍、急停可及"才解锁；
   断线 / 急停 / FAULT / EMERGENCY 自动重新锁定。
2. **Δq 确认框**：`move_j` / `move_mit` 目标与当前位置差 > `confirm_threshold`
   （默认 0.5 rad）时逐关节列出后确认才发送——防手滑输错数量级。
3. **常驻急停**：顶栏红色按钮一键直达，走 `emergency_now()` 旁路通道，
   不会被"在途等待 ACK 的命令"排队阻塞。
4. `reset` 弹确认框；`enable` 在 FAULT/急停锁存时被禁用。
5. `move_mit` 仅支持**单帧**下发，不提供 100Hz 连续流控制。

## 使用

```bash
pip install -r requirements.txt
python3 main.py            # 普通用户即可（串口在 dialout 组则无需 root）
```

启动后：顶栏选串口 → 连接 → 顶栏自动显示固件版本（如 `Litearm1.4.0-7J`）。
监控页随固件 100Hz 主动上报自动刷新；7 关节整臂 / 1 关节台架按状态帧长自动识别。

配置见 [config.yaml](config.yaml)（仅交互层参数，不含限位）。

## 代码组织

```
main.py                 入口
litetool/
  protocol.py           帧编解码/CRC/G8 状态帧/ACK/ERR/TCP（纯函数）
  checks.py             Δq 意图层确认（唯一"安全"模块）
  client.py             状态缓存 + 命令 ACK 配对 + 急停旁路通道
  transport.py          find_ports + SerialLink 后台读线程
  settings.py           config.yaml 合并（容错）
  gui/
    session.py          Qt-free 会话控制器（读线程→client→PlotModel）
    bridge.py           跨线程 Qt 信号桥
    plot_model.py       状态环形缓冲（线程安全）
    monitor_page.py     监控页    plot_page.py  曲线页
    control_page.py     控制页    motion_page.py 运动页
    main_window.py      主窗口组装 + 命令总线 + 急停/锁定/Δq 流程
tests/                  离线测试（无硬件可跑）
```

线程模型：串口读线程（收帧→状态缓存→环形缓冲全量入）｜ 命令工作线程（每次一条，
`_tx_lock` 保证串行）｜ GUI 主线程（20Hz 采样刷新表格/状态灯，30Hz 重绘曲线）。

## 测试

```bash
python3 -m pytest          # 51 用例：协议(黄金向量)/checks/客户端(FakeLink)/传输/配置/曲线模型
```

## 真机验收清单（需 STM32 + 电机/CAN 在线）

> 首次/改动后按顺序执行；任何一步与预期不符即停下排查，不跳过。

1. **只读连接**（不使能，安全）：
   - [ ] 顶栏选串口 → 连接 → 状态点变绿"● 在线"，顶栏出现固件版本
   - [ ] 监控页模式=INIT，帧率 ≈ 100Hz，seq 递增无跳变（丢帧≈0）
   - [ ] 表格每关节显示 q/dq/tau/温度/err；拔串口 → 变红"● 离线"，命令按钮全禁用
2. **曲线**：
   - [ ] 曲线页随状态滚动；勾选 J1~J7 通道切换；"冻结"暂停、"清屏"重绘
3. **基础控制**（会加磁锁位，臂需受支撑）：
   - [ ] 使能 enable → ACK；mode 经 move 验证可进入 MOVE_J
   - [ ] 失能 disable / 清故障 / 速度倍率滑块生效
   - [ ] 急停 → mode=EMERGENCY + FAULT 灯亮；enable 被拒；**复位 reset** → 回到 INIT、灯全灭
4. **运动下发**（低速起步，sp=0.1）：
   - [ ] 运动页锁定横幅显示；勾选确认解锁
   - [ ] move_j 目标=当前位置+0.1 rad → 下发到位，幅度小
   - [ ] move_j 目标与当前差 >0.5 rad → 弹 Δq 确认框；取消则不下发
   - [ ] 下发途中按急停 → 立即锁定 + mode=EMERGENCY；复位后解锁可再动
5. **异常路径**：
   - [ ] 命令执行中快速连点其它按钮 → 提示"忙"，不并发下发
   - [ ] 手动给 move_j 输入 NaN/极大值 → 日志显示固件 ERR 0x02 拒绝，臂不动

## 固件版本兼容性（1.4.x / 1.5.0）

- **状态帧双布局自适应**：≤1.4.0 = `4+21N`；1.5.0(M7) = `6+21N`（尾部 joint_fault
  u16 断轴位图，flags bit9=enabled）。解码器按帧长自动识别。
- 旧固件下降级表现："臂"使能指示恒为失能（无 bit9）、无"断轴"标记、seq 为 8 位
  回绕（丢帧统计在 1.5.0 下才精确——1.5.0 起 seq 为真 u16 且仅发送成功才计数）。
- **1.5.0 语义变化**（M3/M8/L4）：
  - 急停/EMERGENCY 锁存**仅 [复位 reset] 可退出**，[失能] 不再解除锁存；
  - 未使能时发运动命令回 `ERR 0x03`（不再假 ACK），日志显示"被固件拒绝：未就绪/未使能"；
  - enable 锁存类拒绝回 `ERR 0x06`（须先复位，重试无效），与可重试的 0x03 区分——
    GUI enable 重试逻辑只对 0x03 重试；
  - 监控页状态列新增"断轴"（红）：固件 G7 单轴锁存位图直接可见，不再靠 err 推断。

## 已知边界

- 状态丢帧只在**接收侧**累积（seq 差分），固件 100Hz 主动推，无 ACK 状态流。
- 曲线数据 100Hz 全量入环形缓冲（最近 30s），绘图 30Hz 重绘不抽稀。
- 第一版无自动重连（离线后手动重新连接）。

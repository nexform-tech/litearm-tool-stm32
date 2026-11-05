[English](architecture.md) | 简体中文

本文面向修改 GUI、命令链路或参数目录的开发者，说明 LiteArm Tool STM32 的结构。

# 架构

## 背景

本工具是 PyQt5 桌面应用，通过 USB CDC 串口与 LiteArm STM32 固件通信。它以 100Hz 显示电机状态、绘制近期曲线、下发控制与运动命令，并编辑运行时参数。

工具不实现硬安全。斜率限制、软限位、非法值拒绝、看门狗和急停兜底属于固件。工具只实现操作意图层：确认对话框、运动页锁定、参数范围校验和急停旁路。

约束：

- 一个串口只有一个所有者。固件以 100Hz 主动推送状态，不等待上位机。
- 命令是带 ACK/ERR 的请求/响应。排队中的命令绝不能阻塞急停。
- 参数目录必须能在无 Qt 的环境使用，测试与 YAML 导入导出共用同一份定义。

## 组件

| 组件 | 职责 | 依赖 |
|---|---|---|
| `litetool/protocol.py` | 帧编解码、CRC、G8 状态帧、ACK/ERR、调参命令编解码 | 仅标准库 |
| `litetool/param_catalog.py` | 参数镜像：schema、范围、diff、ff_mask、role/hint/detail | `protocol.py` |
| `litetool/tuning_guide.py` | 调参指南文本：公式、符号映射、读前须知、症状速查 | 仅标准库 |
| `litetool/checks.py` | Δq 意图确认与运动页锁定校验 | 仅标准库 |
| `litetool/client.py` | 状态缓存、ACK 配对、急停旁路、参数读写 | `protocol.py`、`transport.py` |
| `litetool/transport.py` | 串口发现与 `SerialLink` 后台读线程 | `pyserial` |
| `litetool/settings.py` | 容错的 `config.yaml` 合并 | `PyYAML` |
| `litetool/gui/session.py` | 无 Qt 的会话控制器：读线程 → client → 曲线模型 | `client.py`、`plot_model.py` |
| `litetool/gui/bridge.py` | 跨线程 Qt 信号桥 | PyQt5 |
| `litetool/gui/plot_model.py` | 线程安全的近期状态环形缓冲 | 仅标准库 |
| `litetool/gui/*_page.py` | 监控、曲线、控制、运动、参数、调参指南页 | PyQt5、`pyqtgraph` |
| `litetool/gui/main_window.py` | 窗口组装、命令总线、急停/锁定/Δq 流程 | 所有 GUI 模块 |

## 数据流

```text
USB CDC ──帧──▶ SerialLink 读线程 ──▶ Client 状态缓存 ──▶ PlotModel 环形缓冲
                                              │
GUI 20Hz 采样 ────────────────────────────────┘
                                              │
GUI 命令 ──▶ 命令工作线程（每次一条）──▶ Client ──▶ SerialLink ──▶ USB CDC
```

读路径：串口读线程解码帧、更新状态缓存，并把每个样本写入环形缓冲。GUI 以 20Hz 采样缓存刷新表格和状态灯，以 30Hz 重绘曲线。

写路径：GUI 操作把一条命令提交给工作线程。工作线程用 `_tx_lock` 串行化命令并等待 ACK 或 ERR。参数页运行自己的批量写入，但共享忙标志，因此不会与主命令链路交错。急停通过 `emergency_now()` 绕过队列。

## 边界

- 本仓库包含上位机工具、参数镜像、预设和离线测试。
- 固件、电机控制和硬安全属于 `litearm-stm32`。
- 串口协议 SDK 属于 `litearm-python`。
- 真机验收步骤记录在 README 中，不在此自动化。

## 决策

- **不用 SocketCAN。** 固件独占电机 CAN 域，上位机走 USB CDC 命令口。
- **固件是安全权威。** 在 GUI 复刻限位会产生两个可能不一致的真源。
- **单一命令工作线程。** 一个串口无法安全服务并发读线程；串行化命令让 ACK 配对无歧义。
- **纯 Python 参数目录。** `param_catalog.py` 与 `tuning_guide.py` 不引入 Qt，测试、YAML 导入导出和 UI 共用同一份定义。
- **状态帧布局自动识别。** 固件 1.4.x 与 1.5.0 的帧长不同；解码器按长度选择布局，不要求版本标志。

[English](README.md) | 简体中文

# LiteArm Tool STM32

LiteArm 运控固件（`litearm-stm32`，STM32H723）的桌面上位机工具。

**应用层交互一律经 [`litearm-python`](https://github.com/nexform-tech/litearm-python) 完成** ——
本工具不再自带协议实现，只做界面、意图层安全与调参台账。传输走板载复合 USB 的 CDC 口
（gs_usb + CDC VCP，VID:PID `1d50:606f` → `/dev/ttyACM0`）。**唯一的例外**是固件升级页：
STM32 ROM bootloader 是另一个 USB DFU 设备（`0483:DF11`），由 pyusb 直接驱动（见
[固件升级](#固件升级usb-dfu)）—— 它不是应用层命令，SDK 里也没有对应 API。

要求 `litearm-python >= 2.4.0`（固件 1.12.3 的故障详情按需查询）。

## 架构

```text
GUI 主线程 ──submit(fn)──▶ 任务队列 ──▶ SdkWorker 线程 ──▶ litearm.Arm ──▶ USB CDC
     ▲                                        │
     └────── 20Hz 读 worker.state  ◀──────────┘   100Hz 状态钩子 → 曲线环形缓冲
```

**串口只有一个所有者。** `litearm.Arm` 是按单消费者设计的：`_Ack.expect` /
`pump` / `_read_status` 都直接从同一条串口抢帧。若 GUI 一边轮询状态、一边下命令
（两条读线程），状态轮询会把命令的 ACK 吃掉 —— 表现为**随机**的"无应答(超时)"。

所以全部 SDK 调用都收进 `litetool/sdk_worker.py` 的 `SdkWorker` 线程：空闲时
`get_state(refresh=True)`（固件 100Hz 主动推，这一调用天然就是 100Hz 状态源），
有任务时执行任务，两者串行。SDK **零改动**。

**唯一一处私有耦合**（`tests/test_sdk_hook.py` 守着）：把 `Arm._a._on_status` 包一层，
于是 `movej` 这类阻塞调用内部消费的帧也会进曲线 —— 否则运动期间曲线会冻住，而那正是
最该看波形的时刻。挂不上时 `_attach_state_hook()` **抛错**，不静默降级。

## 界面

顶栏（串口 / 连接 / 固件版本 / 运动解锁 / ⛔急停）＋ **常驻状态条**（模式 / 使能 /
6 个安全 flag 灯 / seq / 丢帧 / 帧率）＋ 左侧三组导航 ＋ 底部可折叠日志。

| 分组 | 页面 | 干什么 |
| --- | --- | --- |
| 监视 | **总览** | 逐关节状态表 + 100Hz 三段联动曲线（原「监控」「曲线」两页合并，可一键放大曲线；可把勾选关节导出为带单位、温度与驱动错误码的 CSV） |
| | **采集** | 固件 300Hz 控制拍采集：录制 / 查进度 / 读回预览 / 导出原始字节 / 导出解析 CSV |
| | **日志** | 结构化 JSONL：实时视图 / 按级别、类别、文本筛选 / 原始记录详情 / 重启后历史回读 / 导出 JSONL |
| | **故障** | 按轴故障原因（`flags` bit11 为真时按需查一次 `0x51`）+ flags + `drop_hold`；7 轴一屏，原因/处置分列 |
| 操作 | **整机** | 使能 / 失能 / 复位 / 清故障 / 回零 / 全局调速器 / park / 读状态 / 启动原因 |
| | **关节** | `move_j` / `move_js` / `move_mit` 单关节 / `move_mit_all` 整臂；一键就绪姿态 `[0, 0.5, 0, -1, 0, 0.6, 0]`（按轴数裁剪/补 0）；显式 `movej` 接管 |
| | **笛卡尔** | 读 TCP / `ik` 求解 / `move_p` / `movel` 直线 / 基座或工具系点动（按住连续、松手停止）/ 受控停止 |
| | **零重力** | 拖动示教（保活由 SDK 后台线程维持，本工具不发心跳帧） |
| | **夹爪** | LiteGrip（仅 Linux）：连接 / 使能 / 张开 / 闭合 / 抓取 / 零力矩停止 / 遥测 / 标定 / 写零 |
| 参数 | **参数表** | 关节级参数与 0x26/0x27/0x28 前馈族：读回 / 编辑下发 / ff_mask / 批量导入导出 / 固化 Flash / 恢复出厂 |
| | **调参指南** | 公式与符号映射、读前须知、"症状→建议参数"速查、可展开逐参数详解 |
| | **诊断** | `KIN_BENCH` 自检、启动复位原因、链路计数（CRC / 队满 / CAN 失败 / 控制拍超预算）、错误码文案、诊断包 |
| | **授权** | 读设备授权记录（UID / 状态 / 客户号 / 签发日）；未激活设备可在线提交注册信息激活（`0x2F` / `0x3F`） |
| | **固件升级** | USB DFU（`0483:DF11`）：选镜像并校验（版本 / 大小 / 地址范围 / SHA / 空洞），失能后进 ROM bootloader —— 或直接从已停在 bootloader 的板子起跑 —— 烧录并读回校验，进度 / 取消 / 结果 |

## 覆盖：SDK 公开面 → UI 入口

`litearm-python` v2.4.0+ 的公开方法逐条对应（`tests/test_sdk_hook.py` 会盯住这张表的
SDK 侧是否还在；`tests/test_pages_sdk.py` 会盯住 UI 是否真的接到）。

| SDK | UI 入口 |
| --- | --- |
| `connect` / `close` / `reconnect` | 顶栏 连接 / 断开（重连 = 断开后再连） |
| `firmware` / `n` / `last_reset_reason` | 顶栏固件版本、整机页、诊断页 |
| `enable` / `disable` / `reset` / `clear_faults` | 整机页（后三者二次确认） |
| `emergency_stop` | 顶栏 ⛔ 急停（**插队**通道，见下"安全模型"） |
| `home` | 整机页 [回零 home]（二次确认 + Δq 提示） |
| `set_speed` | 整机页全局调速器（0..100 整数百分比） |
| `park` / `set_motion_mode` | 整机页 [park]。固件只识别 `mode=0`（就是 park），其余值回 ACK 而模式不变，故不给无效旋钮 |
| `movej` | 关节页（Δq 超阈值弹确认） |
| `move_js` | 关节页单发（页面明示 0.1s 看门狗语义） |
| `send_mit` / `send_mit_all` | 关节页单关节 / 整臂单帧 |
| `move_p` | 笛卡尔页（位姿幅度超阈值弹确认） |
| `move_l` | 笛卡尔页 [movel] 与按住点动（需固件 `LITEARM_CART_PLAN`） |
| `ik` | 笛卡尔页 [求解 IK]（只算不动；种子可选当前实测角） |
| `get_tcp` | 笛卡尔页 [读取当前末端位姿]、总览 |
| `get_state` | 100Hz 常驻（状态条 + 总览表 + 曲线） |
| `get_status_now` | 整机页 [读取状态 GET_STATUS] |
| `get_state().fault_detail_available` / `get_fault_detail()` | 故障页（bit11 为真时按需查一次 `0x51`；旧固件显示"原因不可知"） |
| `describe` / `describe_fault` / `describe_exc` | 故障页 / 日志：错误码 → 标题 + 原因 + 处置；未登记码不空白 |
| `zero_g` / `zero_g_start` / `zero_g_stop` / `zero_g_active` / `zero_g_error` | 零重力页（按钮跟**实际**状态走，保活中断会显示原因） |
| `set_ff_mask` / `get_ff_mask` / `ff_preset` | 参数表页 ff_mask 复选框组 |
| `set_ff_vec` / `get_ff_vec` | 参数表页逐关节向量（1.12.3：1..11、15、16；12..14 已删） |
| `set_ff_scalar` / `get_ff_scalar` | 参数表页全局标量（1.12.3：1..8、11、17、18；10 与 12..16 已删） |
| `set_gravity_scale` / `set_inertia_scale` | 参数表页 `gravity_scale` / `inertia_scale` 向量（同一写口 0x26 item 7/8 的具名封装） |
| `set_payload` / `set_gravity_vector` | 参数表页 `payload_mass`/`payload_com`/`gravity` 标量（0x28 item 4/5/6） |
| `save_params` | 参数表页 [固化到 Flash]（二次确认，须先失能） |
| `params.get_joint_param` / `all_joint_params` | 参数表页 [刷新当前] |
| `params.set_joint_param` / `set_joint_limits` | 参数表页逐关节下发（限位写成组整发） |
| `params.reset_factory` | 参数表页 [恢复出厂] |
| `license` / `activate` | 授权页（读 UID/状态；未激活时在线提交注册信息并回读确认） |
| `enter_dfu` | 固件升级页（失能 → 进 ROM bootloader；DfuSe 引擎在 `litetool/dfu/`，不在 SDK 里） |
| `log.start` / `stop` / `reader` / `capture` / `dump` | 采集页 |
| `LogReader.total` / `wait_for` / `read_all` / `iter_chunks` / `samples` | 采集页 查进度 / 读回预览 / 采集全程 |
| `diag.kin_bench` | 诊断页 [运行 KIN_BENCH 自检] |
| `find_cdc_port` | 顶栏串口下拉（`litetool/ports.py` 另列全部候选口，板载 CDC 恒排最前） |

## 安全模型（重要）

**一切硬防护的权威在固件**：斜率限制、软限位、NaN/非法值拒绝、看门狗 fail-soft、
急停兜底均由 STM32 承担，不依赖上位机在线与否。本工具**不**复刻这些防护。

工具只承担固件防不了的**操作意图**层：

1. **运动解锁（全局一把）**：顶栏勾选"我已确认机械臂周围无障碍、急停可及"后，
   整机[回零]/关节/笛卡尔/零重力四个页面才放行。**断线、急停、FAULT/锁存、复位**
   都会自动收回解锁。未连接时勾选会被拒绝。
   *为什么是全局一把而不是每页一把*：要防的是"手滑下发一个大幅运动"，风险属于命令
   而非页面；四把独立开关只会诱导人条件反射地把它们全勾上。
   **闸门在 `MainWindow._motion_denied()` 收口，不是各页按钮的 `setEnabled`** ——
   按钮灰态只是 UX，任何能到达处理函数的路径（代码 emit / 某页漏禁一个控件 / 快捷键）
   都必须在这里被挡住。
2. **Δq 确认框**：`movej` / `move_js` / `move_mit` / `move_mit_all` 的目标与当前差
   超过 `confirm_threshold`（默认 0.5 rad）时逐关节列出后确认；`move_p` 另有位姿幅度
   确认（位置 0.05 m / 姿态 0.30 rad）。
   **拿不到基线时一律拒绝**，不是免检：状态帧还没到 / 没读过 TCP 时，输入框往往还是
   默认值，正是最容易手滑的时刻。`move_p` 在无 TCP 基线时会**自动先读一次**再判幅度。
3. **常驻急停**：顶栏红色按钮，走 `SdkWorker.emergency_now()` —— GUI 线程**直接写帧**，
   不排队、不等 ACK。在途的 `movej` 可能把所有者线程占住十几秒，急停必须绕开队列。
   该通道**只写不读**，故不会被在途命令挡住，也不会与所有者线程抢帧。
   代价是它**不能**声称"已失能"：帧发出 ≠ 固件已执行。界面文案严格区分
   「急停帧已发出 — 请目视确认臂已停止」与「急停未发出 — 请立即用硬件急停/断电」。
   急停还会**丢掉排队中的命令**（语义是"停下"，不是"先做完手上的"）并**收掉零重力
   保活**（否则那条线程会每 40ms 继续空转发帧，而界面还显示"拖动中"）。
   在途的那一条命令没法抢占，但它的结果会被固件的 EMERGENCY 锁存拒掉，不会真的动臂。
4. **急停/故障自动重新锁定**，`reset` 之后重新锁定（旧解锁态不跨过急停继续有效）。
5. 参数页：必须**先 [刷新当前] 成功**才允许下发；臂 enable 态下写控制律弹二次确认；
   限位写前逐关节校验当前 q 在新 [q_min,q_max] 内；固化 Flash、批量应用、ff_mask 改动
   均二次确认。
   **参数项按板子实测能力显示**：[刷新当前] 时逐 item 探测 `0x2B`/`0x2C`，板子回
   `ERR{cmd,0x02}` 的项隐藏且不参与下发 —— 界面不再靠本地目录去猜某版固件有什么
   （目录只提供标签/范围，是否显示由板子回答）。超时/链路错误仍按故障上报，不会
   被误当成"板子没有这项"。
6. 所有运动页明确标注"单帧/单发"语义 —— 固件 0.1s 看门狗下，`move_js` 连续伺服需
   调用方 ≥10Hz 重发，本工具不提供连续流。
7. **点动 / movel**：都需要固件笛卡尔规划（`LITEARM_CART_PLAN`）；连接探测给出"不支持"
   或"未获确认"时按钮保持灰色，页面写明原因。点动每一步都从**实测** TCP 重新起步（不做
   积分）：按住持续续段，松手作废链路；若松手时还有一段在途，会走与急停相同的**只写不读**
   旁路发一条 `movej` 到当前实测角受控收口。该帧**不等 ACK** —— 日志只说"帧已发出"，
   不说"已停止"。[接管在途运动] 勾选后写一条 `movej` 旁路帧，作废在途笛卡尔规划；
   若在途的是另一条 `movej`，SDK 仍要等原目标收尾（固件已改道），日志会如实说明。

## 固件升级（USB DFU）

**固件升级**页通过 STM32 ROM bootloader（`0483:DF11`）烧录 `.hex` / `.bin`。烧录引擎逐字
复用 studio 的 DfuSe 实现（`litetool/dfu/engine.py`；时序来自上游 `dfu-flash`，不许在这里
重写）。

- **两条合法起点**：连着应用态时先失能，再发 `CMD_ENTER_DFU (0x15)` 进 bootloader；
  板子已经停在 bootloader 里时没有应用态会话（连不上是正常的），页面检测到 `0483:DF11`
  就直接烧 —— 这是"救援"路径，页面上会明确说是哪一种。
- **安全**：升级会先失能 —— 电机会松开，有重力负载的臂会下垂，先确认已放稳/有支撑。
  软件急停对停在 bootloader 的板子无效，只能靠硬件急停/断电。许可证扇区与出厂标定扇区
  （`0x080C0000..0x08100000`）不会被触碰：覆盖该区的镜像在任何硬件动作之前就被拒绝。
- **镜像准入**：摘要显示版本、大小、地址范围、格式、空洞、SHA-256；不在 `0x08000000`、
  超过 1MB Flash、覆盖受保护扇区的镜像不允许开始。
- **进度与取消**：相位 + 字节 + 明细可见；取消在相位之间与等待类相位生效。烧录相位开始后
  取消不再中止（擦一半比烧完更糟），结果/摘要会说明这一点。
- **依赖**：`pyusb` + `libusb-package`（都在 `requirements.txt`，PyInstaller 也会收进去）。
  Windows 上 DFU 设备还需要 ST 的 WinUSB 驱动。Linux 上加一条 udev 规则并重新插拔：
  ```bash
  echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="df11", MODE="0666"' \
    | sudo tee /etc/udev/rules.d/49-litearm-dfu.rules
  sudo udevadm control --reload-rules && sudo udevadm trigger
  ```
- **真机验收**：离线测试覆盖引擎、镜像判据与整条流水线（假件）；成功/取消/拔线仍须真板
  验证（见下面的真机验收清单）；引擎的擦除忙时长下界、读回校验、失败擦回空白正是那几次
  要验的保护。

## 使用

```bash
pip install -e ../litearm-python     # 交互层依赖（>= 2.4.0）
pip install -r requirements.txt
python3 main.py                       # 普通用户即可（串口在 dialout 组则无需 root）
python3 main.py --activation-url https://act.nexform.tech   # 指定激活服务（默认即生产地址）
```

启动后：顶栏选串口 → 连接 → 顶栏显示固件版本（如 `Litearm1.12.3-7J`）。
连接时会校验固件版本约定（最低 1.5.0）。总览页随 100Hz 主动上报自动刷新；
整臂 7J / 台架 1J 按状态帧长自动识别。

配置见 [config.yaml](config.yaml)（仅交互层参数，不含限位）。

**同一时间只允许一个实例。** 第二次启动不会打开串口，而是把已在运行的窗口提到前台后退出；
锁是本地套接字（`QLocalServer`），上次崩溃留下的陈旧锁会在下次启动时自动清理。第二个
进程会弹一条简短提示说明退出原因。

**断线自愈。** 状态流静默或传输异常时判离线并自动重拨：先试上次成功的口，再按枚举顺序
试其它候选，指数退避（0.5s → 5s）。旧链路上排队的命令一律丢弃，运动解锁不会恢复；
点 [断开] 会停止重试 —— 用户的主动操作不被自动重连覆盖。

结构化日志写到 `$XDG_STATE_HOME/litearm-tool/tool.jsonl`（默认 `~/.local/state/...`；
Windows 是 `%LOCALAPPDATA%\litearm-tool\Logs`），单文件 5 MB、保留 5 份轮转备份；
`LITEARM_TOOL_LOG_DIR` 可改目录。「日志」页读当前文件与备份，所以重启后历史仍在；
诊断包只附日志路径，不内联内容。

**LiteGrip（可选，仅 Linux）。** 安装 `requirements-gripper.txt`，把 SocketCAN 以 1 Mbit/s
拉起（`sudo ip link set can0 type can bitrate 1000000; sudo ip link set can0 up`），再进
「夹爪」页。通道下拉列出内核枚举到的 CAN 接口（`/sys/class/net/*/type` = `ARPHRD_CAN` 280），
也允许手填未列出的名字。Windows 或未安装 `litegrip-python` 时页面保留但禁用连接并写明原因。
通道 / CAN ID / MST ID 断开重连后生效；标定决定行程与方向，未标定时 SDK 拒绝运动。停止按钮发
零力矩帧，动作在途时并失能电机以中止，不是机械臂急停。

**Windows 打包。** 在仓库根目录运行
`powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build-windows.ps1`。脚本会建干净
venv、从同级 `litearm-python`（或 `-SdkSrc`）装 SDK、跑离线测试，然后产出
`packaging\out\litearm-tool-stm32-<版本>-windows-x86_64\` 与同名 zip。Windows 10/11 自带
USB CDC 驱动；端口列表为空时装 STM32 VCP 驱动。夹爪仅 Linux，不进 Windows 包；DFU（WinUSB）
与 3D OpenGL 的 Windows 验收分别留在 #19 / #17。

固件升级页需要 `pyusb` + `libusb-package`（`requirements.txt` 已包含）。Linux 上按
[固件升级](#固件升级usb-dfu) 里的 udev 规则配置；Windows 上给 DFU 设备安装 ST 的 WinUSB
驱动。

## 代码组织

```text
main.py                 入口（薄壳, 转调 litetool.app:main）
litetool/
  app.py                启动入口（`python3 -m litetool` / `litearm-tool` 命令共用）
  instance.py           单实例锁（本地套接字；第二次启动只把已有窗口提到前台）
  sdk_worker.py         ★ 唯一持有 pa.Arm 的线程 + 任务队列 + 状态钩子 + 断线自愈
  params_io.py          在 pa.Arm 之上的参数读写形状层（页面要 (ok, code)）
  diagnostics.py        错误码文案 / 诊断包 / 链路计数汇总
  model_io.py           HYY 模型与参数的导入/导出
  hyy_config.py         HYY 配置文件解析
  ports.py              串口枚举（板载 CDC 排最前）
  gripper.py            LiteGrip 所有者线程（独立线程，SocketCAN；仅 Linux）
  plot_model.py         状态环形缓冲（线程安全, 含实测帧率）
  checks.py             意图层确认（Δq / 位姿幅度；唯一的"安全"模块）
  pose_math.py          点动位姿数学（基座/工具系、rpy ↔ 旋转矩阵）
  param_catalog.py      调参参数目录镜像表 + schema/diff/ff_mask + role/hint/detail
  tuning_guide.py       调参指南内容（公式/符号映射/症状速查）
  firmware_defaults.py  解析固件 defaults.c（presets/ 生成与一致性断言的真源）
  settings.py           config.yaml 合并（类型 + 区间校验）
  csv_export.py         曲线窗口 / 300Hz 采集的 CSV 写出（列名带单位）
  obs.py                结构化日志（JSONL、OpenTelemetry 字段名、脱敏）
  activation.py         激活服务客户端（唯一出网点；凭据/注册信息校验）
  license_io.py         授权记录（0x2F/0x3F）的形状层 + 聚合错误 0x02 的回读判定
  dfu/
    engine.py           DfuSe 烧录引擎（逐字来自 studio / 上游 dfu-flash；只依赖 pyusb）
    image.py            镜像离线解析与准入判据（基址 / 1MB 上界 / 受保护扇区）
    job.py              升级流水线（失能 → 进 DFU → 烧录 → 复位 → 重连）
    fake.py             离线测试/演示用的假 DFU 引擎
    controller.py       tool 侧适配：SdkWorker + pyusb 引擎 + GUI 线程重连
  gui/
    bridge.py           跨线程 Qt 信号桥（日志 / 任务结果 / 在线态）
    widgets.py          日志面板 / 常驻状态条 / 关节表 / 横幅 / 左侧导航
    pages/
      overview_page.py  总览      capture_page.py  采集
      fault_page.py     故障      machine_page.py  整机
      joint_page.py     关节      cart_page.py     笛卡尔
      zerog_page.py     零重力    params_page.py   参数表
      gripper_page.py   夹爪      log_page.py      日志
      guide_page.py     调参指南  diag_page.py     诊断
      installation_page.py 安装方向
      activation_page.py 授权（读 UID / 在线激活）
      firmware_page.py 固件升级（USB DFU）
      common.py         pose/关节输入组等共用件
      plot_pane.py      三段联动曲线组件
    main_window.py      主窗口组装 + 命令收口（Δq 确认/解锁/急停流程）
templates/params_example.yaml   导入模板（含单位/范围注释）
presets/                        出厂 / SE1 摩擦 预设
tests/                  离线测试（无硬件可跑）
```

**线程模型**：SDK 所有者线程（唯一碰 `Arm`）｜ GUI 主线程（20Hz 读快照刷界面、
30Hz 重绘曲线）。参数页与采集页不再自建线程，一律 `submit` 到所有者线程。

## 测试

```bash
python3 -m pytest          # 617 passed（全部离线，无需硬件）
```

| 文件 | 盯什么 |
| --- | --- |
| `test_sdk_worker.py` | 串口所有权 / 任务队列 / 状态钩子 / 离线判定 / 丢帧统计 / **急停旁路插队** |
| `test_sdk_hook.py` | 工具对 SDK 的私有耦合（`_a._on_status`、`_write_cmd(guarded=)`）与公开面仍在 |
| `test_pages_sdk.py` | 页面 → SDK 的**接线**（每个按钮真的落到哪个 SDK 调用） |
| `test_params_io.py` | 参数读写形状层（含 ERR code 透传） |
| `test_params_flow.py` | 参数页安全闸（未刷新禁下发 / enable 态确认 / 限位越界拒绝） |
| `test_safety_ui.py` | 急停不谎报 / 危险命令二次确认 / 解锁自动收回 / Δq 确认 |
| `test_fault_query.py` | bit11 → `0x51` 的触发 / 去重 / 清故障失效 |
| `test_fault_display.py` | 旧固件 `fault_reason` 为空时的回退 |
| `test_fault_page.py` | 故障页布局与 7 轴一屏 |
| `test_diagnostics.py` | 错误码文案与诊断包 |
| `test_gui_smoke.py` | 构建与布局回归（导航 3 组 13 页、台架 1J、运动页默认锁定） |
| `test_activation.py` | 激活客户端：凭据解析 / 注册信息校验 / 服务错误映射 / 内部通道令牌（含 studio 的配置路径覆盖）；**不出网** |
| `test_activation_page.py` | 授权页：三态记录、失败重读/断线保留、同意书文案、提交门禁、使能拦截、0x02 与未确认回读、连上自动读取 |
| `test_app_flags.py` | `--activation-url` 解析（空格/`=` 两种形态；缺值不能吞掉后面的 Qt 参数） |
| `test_dfu_engine.py` | DfuSe 引擎（从 studio 搬入）：擦除忙时长下界、读回校验、失败擦回空白、受保护区 `skip` / `wipe` |
| `test_dfu_image.py` | 镜像准入（基址 / 1MB / 受保护区 / HEX vs BIN）与假 hooks 的流水线相位 |
| `test_dfu_controller.py` | tool 侧适配：失能/进 DFU 失败映射、`enter_dfu` 后放串口、udev 权限重试、开跑前闸门 |
| `test_firmware_page.py` | 固件升级页（假引擎 + 假 SDK）：摘要、from-DFU 路径、完整流水线、失败、取消、重连 RPC |
| `test_checks.py` `test_plot_model.py` `test_param_catalog.py` `test_settings.py` `test_tuning_guide.py` | 意图层与纯数据层 |
| `test_preset_sync.py` | `presets/` 与 `templates/` 逐字段比对固件 `defaults.c`（固件仓在场时生效，`LITEARM_FW_DIR` 可指定） |

## 真机验收清单（需 STM32 + 电机/CAN 在线）

> 首次/改动后按顺序执行；任何一步与预期不符即停下排查，不跳过。

1. **只读连接**（不使能，安全）：
   - [ ] 顶栏选串口 → 连接 → 状态点变绿"● 在线"，顶栏出现固件版本
   - [ ] 常驻状态条模式=INIT，帧率 ≈ 100Hz，seq 递增无跳变（丢帧≈0）
   - [ ] 总览页表格每关节显示 q/dq/tau/温度/err；拔串口 → 变红"● 离线"，命令按钮全禁用
   - [ ] 拔线后顶栏显示 `● 重连中(n)`；插回 → 自动恢复在线且仍保持运动锁定；断线前排队的命令已被丢弃
   - [ ] 断线状态下点急停 → 显眼处必须显示"急停未发出"，不得显示"已失能"
2. **曲线**：总览页随状态滚动；勾选 J1~J7 通道切换；"冻结"暂停、"清屏"重绘；
   [曲线放大] 收起状态表。**下发一次 movej，确认运动期间曲线仍在更新**（状态钩子）。
3. **基础控制**（会加磁锁位，臂需受支撑）：
   - [ ] 未勾选解锁时 [回零] 不可点；勾选后可点
   - [ ] 使能 enable → ACK；失能 disable / 清故障 / 复位 / 全局调速器生效
   - [ ] 急停 → 模式=EMERGENCY + FAULT 灯亮；解锁被收回；enable 被拒；
         复位 reset → 回到 INIT、灯全灭、仍保持锁定
4. **运动下发**（低速起步，sp=0.1）：
   - [ ] move_j 目标=当前位置+0.1 rad → 下发到位，幅度小
   - [ ] move_j 目标与当前差 >0.5 rad → 弹 Δq 确认框；取消则不下发
   - [ ] [就绪姿态] 把目标填成 `[0, 0.5, 0, -1, 0, 0.6, 0]` 并走同一条确认链路下发
   - [ ] 笛卡尔页 [读取当前末端位姿] 有值；[求解 IK] 返回 7 个数；move_p 小幅度到位
   - [ ] 按住一个点动方向约 1s → 连续走若干小步；松手 → 停住并保持；[停止点动] 也能停住
   - [ ] movel 10mm 直线 → 到位；运动结束后页面回读 TCP
   - [ ] 固件未编入 `LITEARM_CART_PLAN`（或探测无应答）时点动/movel 按钮保持灰色，页面写明原因
   - [ ] 关节页 move_mit 单帧单关节，幅度小
5. **零重力**：进入后可用手拖动；按钮与状态条显示一致；退出后关节回到软限内；
   拔线 → 状态栏显示"保活中断"，按钮自动复位
6. **采集**：设 n=300 → [开始记录] → 等 1s → [查进度] 应显示 ~300 拍 →
   [读回并预览] 出三条曲线 → [导出原始字节…] 落盘
7. **诊断**：[运行 KIN_BENCH 自检] 出原文与计数（crc/rfd/txf 等）
8. **参数**：见下节
9. **故障页**（按验收计划制造可控故障）：状态帧 bit11=1 → 故障页自动显示按轴原因；
   清故障后原因清空。旧固件（无 `0x51`）显示"原因不可知"，不表示没有故障。
10. **异常路径**：
   - [ ] 命令执行中快速连点其它按钮 → 提示"忙"，不并发下发
   - [ ] 手动给 move_j 输入极大值 → 日志显示固件 ERR 拒绝，臂不动
11. **夹爪**（Linux，LiteGrip 接在 `can0`）：
   - [ ] 连接 → 使能 → 张开/闭合；遥测显示新的位置、夹持力与温度
   - [ ] 以 20N 抓取 3s → 保持住；[停止 / 释放] 中止在途抓取、把力矩拉到 0 并失能
   - [ ] [读取标定] 显示行程与安装方向；保存并重新加载标定文件
   - [ ] Windows（或未安装 `litegrip-python`）时页面写明平台限制并禁用连接
12. **固件升级**（需测试镜像且臂有支撑）：
   - [ ] 连着应用态：选镜像 → 摘要一致；开始 → 先失能、进 bootloader、显示相位 + 字节
         进度，结束后带预期版本重新连上
   - [ ] 在烧录相位之前取消 → 一个字节都不写，板子回到应用态
   - [ ] 烧录中途拔线 → 结果说明失败；重新升级（页面会检测到仍停在 DFU 的板子）把它救回来
   - [ ] 板子已经停在 bootloader：页面显示"DFU"与 USB 位置；不需要串口会话即可开始烧录

## 参数调参页（"参数表"页）

读口 `0x24` / `0x2B` / `0x2C` 需固件 1.5.x（参数读回）。

| 区 | 写口 | 读口 | 说明 |
| --- | --- | --- | --- |
| 关节控制/限位 | `0x22` kp/kd/tau_max、`0x23` q_min/q_max | `0x24` | 逐关节 |
| 逐关节向量 | `0x26` item 1..11 + 15/16 | `0x2B` | 一次一整组（7 值）；12..14 已随 1.11.0 删除；16=drag_gain（1.12.0） |
| 全局标量 | `0x28` item 1..8 + 11 + 17,18 | `0x2C` | 含 payload_mass/gravity/friction_model/drag_db/hold_kp_gain；item10 已于 1.12.0 删除 |
| ff_mask | `0x27` u32 | `0x2C` item 9 | 复选框组 |
| 出厂复位 | `0x36` param_reset（须失能） | — | 二次确认 |
| 固化 | `0x25` param_save（须失能） | — | 二次确认 |

⚠ **1.12.3 的精确合法集**（工具按板子实测能力显示，不靠本地白名单猜）：

- `0x26`：**1..11、15、16**（12..14 已删）
- `0x28`：**1..8、11、17、18**（item 9 保留给 `0x2C` 读 `ff_mask`；10 与 12..16 已删）
- `0x2B` / `0x2C` 读口与写口同集合

用法：

1. 连接后切到 **参数表** 页 → [刷新当前]：`0x24×7` + `0x2B` 逐 item + `0x2C` 逐 item
   一次读回并落表（不支持项由固件回 `ERR{cmd,0x02}`, 自动跳过）。
2. 双击表格单元格改值：黄=已改未发，红=越界/下发失败；[下发选中行]（kp/kd/tau_max
   与 q_min/q_max 成组整发）或 [下发全部]，每个写口等 ACK，失败格标红并打日志。
3. 全局标量用下侧 spin/编辑框；ff_mask 用复选框组，[下发全局] 发送（改动会先确认）。
4. 批量：`presets/` 或 [导入 YAML/JSON…]（模板 `templates/params_example.yaml` 含
   单位/范围注释）→ **diff 预览对话框**逐格显示旧→新 → [应用] 顺序全 ACK →
   可勾选"下发后固化 Flash"（会再弹二次确认；须先在整机页 [失能]）。
   [导出当前]：读回全量写 YAML，与导入同构 —— 同文件再导入 diff 应为空（闭环）。
5. 状态行显示最近操作结果/ACK/ERR；断线自动禁用并提示，重连后恢复。

**出厂基线**（与固件 `defaults.c` 一致，由 `tests/test_preset_sync.py` 逐字段守着）：
`kp=[400,400,300,300,50,50,50]`、`ff_mask=0x1BF`（= G + 惯量 + 科氏 + 摩擦 + 积分，
见下表位定义）。这两组数字是最容易过期的副本 —— 改了固件就得同步改这里与 `presets/`。

参数范围镜像表在 `litetool/param_catalog.py`（纯 Python，无 Qt，供测试/yaml/UI 共用），
数值以固件 `params.c` 与 `flash_store.c apply_loaded` 为准。

- 逐关节：kp[0,500] kd[0,5] tau_max[0.1,120] q_min/q_max[-15,15](须 min<max)
  friction[0,50] ki[0,1000] i_max[0,100] wall_stiff[0,2000] wall_damp[0,50]
  wall_tau_max[0,50] gs/is[0,20] friction_v[0,20] fc0[0,50] fc1[-50,0]
  drag_gain[0,5]（1.12.0 起逐关节，0x26 item16）
- 全局：fric_db[1e-4,0.5] wall_margin[0,0.5] friction_slew[0,500]
  payload_mass[0,20] payload_com[-1,1]×3 gravity[-50,50]×3
  friction_model{0=v1 误差方向, 1=v2 SE1 速度方向, 2=drag 拖动版} fric_v2_eps[1e-3,0.5]
  drag_db[0,0.5](0=硬 sign) wall_fw_kd[0,5] hold_kp_gain[0,5]
- ff_mask 位：MASTER=0x01 G=0x02 INERTIA=0x04 CORIOLIS=0x08 FRICTION=0x10
  INTEGRAL=0x20 WALL=0x40 QUANT=0x80 VELREF=0x100

## 固件版本兼容性

- **状态帧双布局自适应**：≤1.4.0 = `4+21N`；1.5.0+ = `6+21N`（尾部 joint_fault
  u16 断轴位图，flags bit9=enabled）。由 `litearm._protocol` 按帧长识别。
- **SDK 连接时卡版本门**：< 1.5.0 直接拒连（`FirmwareMismatchError`）。
- **1.5.0 语义变化**（M3/M8/L4）：急停锁存**仅 [复位 reset] 可退出**；未使能时发运动
  命令回 `ERR 0x03`；enable 锁存类拒绝回 `ERR 0x06`（须先复位，重试无效）；
  总览页状态列新增"断轴"（红）。
- **1.5.1（2026-09-08）**：控制频率 400→300Hz。上位机无感：状态流仍 100Hz。
  **速度语义（L5 调速器）**：整机页滑块 = 全局封顶，实际速度 = min(move_j 的 sp, 滑块值)；
  HOME 不再静默改写全局速度；`sp>1.0` 被固件显式拒绝 `ERR 0x02`。
  KIN_BENCH 应答含 LINK 诊断行（crc/ovf/rfdrop/txfail）。
- **1.5.2**：M6b 电机超时保护（`RID_TIMEOUT=9`）。监控页 err 列会把 13 显示为
  "超时保护"。
- **1.11.0（2026-11-07）**：零重力改为无状态律（RNEA + drag + wall），删除
  `zg_kp/zg_kd/zg_damping/engage/vel_thr` 等弹簧机参数。
- **1.12.0（2026-11-12）**：拖动摩擦补偿比例改为**逐关节**（`0x26` item16），
  `0x28` item10 全局 `drag_gain` 删除；flash 升 **v11**，刷机后需重新导入模型与参数。
- **1.12.1（2026-11-12）**：零重力退出 / INIT 持位补重力前馈；协议无变更。
- **1.12.3（2026-11-13）**：状态帧回到 **153B**；`flags` bit11 = 故障详情可查；
  新增 `CMD_GET_FAULT 0x51`（7J=13B）。工具在 bit11=1 时按需查询一次；
  1.12.2 的 161B 过渡布局由 SDK 解析。旧固件无 `0x51` → 原因显示"不可知"。

## 已知边界

- 状态丢帧只在**接收侧**累积（seq 差分），固件 100Hz 主动推，无 ACK 状态流。
- 曲线数据 100Hz 全量入环形缓冲（最近 `plot_window_s`），绘图 30Hz 重绘不抽稀。
- 无自动重连：离线后手动重新连接（连接时自动收回运动解锁）。
- 参数页的关节列固定 7 列（`param_catalog.NUM_JOINTS`）。台架 1J 上只读得到 J1，
  J2..J7 显示"—"且封禁编辑、不参与下发（固件只有 1 个关节，SDK 的 `_check_idx` 会拒）。
- 断线后不再回显最后一帧：`SdkWorker` 在离线/关闭时丢弃状态快照，状态条与表格留白 ——
  把陈旧遥测当实时数据显示会让人以为臂还在原地。
- 故障原因只在 `flags` bit11=1 时查询；旧固件（无 `0x51`）故障页显示"原因不可知"，
  不能据此判断"没有故障"。
- 笛卡尔点动/movel 需要固件的 `LITEARM_CART_PLAN`；台架 1J 或旧固件会禁用它们。
  `movej` 接管会立即作废在途笛卡尔规划；但若在途的 SDK 调用本身是另一条 `movej`，
  该调用仍要等原目标收尾 —— 固件已改道，所有者线程在跑完旧等待后才释放。
- 工具 UI 的固件错误显示是命令名 + 通用码义（`describe`）；逐命令细节在 SDK 异常的
  `err_reason` 消息里（`CommandRejectedError` 的 `str(e)`）。
- 夹爪仅 Linux，且需要 `litegrip-python` 与已拉起的 1 Mbit/s SocketCAN 接口；
  改通道 / CAN ID / MST ID 后需重新连接。零力矩停止不能替代机械臂急停，夹爪链路也
  不做自动重连。

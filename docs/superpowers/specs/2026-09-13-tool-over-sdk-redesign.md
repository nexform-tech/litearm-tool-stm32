# litearm-tool-stm32 重设计：改为 pylitearm-stm32 之上的纯 GUI 层

> ⚠ **历史文档（2026-09-13）**：文中 `pylitearm-stm32` / `pylitearm_stm32` 是**当时的名字**，
> 该仓库先后改名为 `litearm-core`，**`litearm-core` 现已废弃**。
> 现行交互层 = `litearm-python`（import 名 `litearm`）；本工具已于 2026-10-30 完成迁移
> （见提交 `refactor(tool): 交互层迁到 litearm-python`）。

- **日期**：2026-09-13
- **目标**：①排版重设计；②功能**全覆盖** `pylitearm-stm32` v1.6.0 的公开面；③交互一律经该 SDK。
- **不改动**：`pylitearm-stm32` 源码（SDK 保持 1.6.0 原样）。

## 1. 问题：两份协议栈

改造前本工具自带 `litetool/protocol.py` + `client.py` + `transport.py`，与 `pylitearm_stm32`
的 `_protocol.py` + `transport.py` + `arm.py` **各实现一遍**同一套帧协议。后果：

- SDK 已把固件 32/32 条命令补齐到 v1.6.0（见 `pylitearm-stm32/COVERAGE_REPORT_20260913.md`），
  而工具只接了其中一小部分 —— 差距不会自己收敛，两份实现只会继续漂移
  （历史事故：状态帧 4+21N→6+21N 漏同步一端，桩测试全绿、真机必挂）。

**结论**：删除工具自带的协议栈，SDK 成为唯一的协议/命令实现。

## 2. 架构：SDK 所有者线程

`sdk_worker.SdkWorker` 是**唯一持有 `pa.Arm` 的线程**，也是串口的唯一读者。

```text
GUI 主线程 ──submit(fn)──▶ 任务队列 ──▶ SdkWorker 线程 ──▶ pa.Arm ──▶ USB CDC
     ▲                                      │
     └────── 20Hz QTimer 读 worker.state ◀───┘  100Hz 状态钩子 → PlotModel
```

线程空闲时循环 `arm.get_state(refresh=True)`（固件 100Hz 主动推，故这一调用天然
就是 100Hz 状态源）；有任务时执行任务。两者在同一线程串行 ⇒ SDK 的「单消费者 +
读写各一把锁」假设始终成立，永远不会有两条读线程互相偷 ACK。

### 2.1 状态钩子（唯一一处私有耦合）

问题：`arm.movej()` 这类阻塞调用内部会 `_Ack.pump()` 消费串口帧，但**不会**把它们
交给 GUI —— 运动期间曲线会冻住，而那正是最需要看曲线的时刻。

解法：在 `connect()` 之后把 `arm._a._on_status` 包一层，解码出的 `RobotState` 除了
喂给 SDK 自己也推给 `PlotModel`。所有路径（`expect`/`pump`/`_read_status`/
`get_status_now`）都收敛到这一个方法，故一处挂钩即全覆盖。

这是**唯一**的私有属性依赖（`Arm._a`、`_Ack._on_status`）。`_attach_state_hook()`
在挂不上时**抛错而静默降级**，并有 `tests/test_sdk_hook.py` 守着该缝隙存在 ——
SDK 若重命名，测试先红，而不是曲线悄悄不画了。

### 2.2 离线判定

`_read_status` 超时返回 `None`（不抛），故连续 `None` 累计超过 `offline_timeout`
（默认 1.0s）才判离线；`TransportError` 立即判离线。离线后线程退出循环，由用户重连。

## 3. 排版：左侧分组导航

顶栏（串口 / 连接 / 在线灯 / 固件版本 / **常驻急停**）与底部可折叠日志不变，中部
由 6 个平铺页签改为**左侧分组导航 + 右侧内容区**：

| 分组 | 页面 | 覆盖的 SDK 面 |
| --- | --- | --- |
| 监视 | **总览** | `get_state` / `RobotState` 全字段 / `get_status_now` / 100Hz 曲线 |
| | **采集** | `log.start/stop/reader/capture/dump`、`LogReader` 全方法 |
| 操作 | **整机** | `enable` `disable` `reset` `clear_faults` `set_speed` `park` `set_motion_mode` `last_reset_reason` |
| | **关节** | `movej` `move_js` `send_mit` `send_mit_all` `home` |
| | **笛卡尔** | `get_tcp` `ik` `movep` |
| | **零重力** | `zero_g` / `zero_g_start` / `zero_g_stop` / `zero_g_active` / `zero_g_error` |
| 参数 | **参数表** | `params.*`（0x22/0x23/0x24/0x36）、`set_ff_vec/scalar/mask`、`get_ff_*`、`set_gravity_scale` `set_inertia_scale` `set_payload` `set_gravity_vector`、`ff_preset`、`save_params` |
| | **调参指南** | （工具自有：公式/症状速查/逐参数详解） |
| | **诊断** | `diag.kin_bench`、`last_reset_reason`、seq 丢帧 |

**总览 = 监控 + 曲线合并**：状态条 + 逐关节表在上、三段联动曲线在下。两者本就吃
同一份 100Hz 流，拆成两页只会让人来回切。另给「曲线放大」把曲线区占比拉到最大。

## 4. 保留的工具侧职责

SDK 是库、不是 UI，下列属于**意图层**，SDK 不提供，继续由工具承担：

1. **运动解锁**：关节/笛卡尔/零重力页默认锁定，勾选确认后解锁；断线 / 急停 /
   FAULT / 复位后自动重新锁定。
2. **Δq 确认框**（`checks.plan_motion`）：`movej` 目标与当前差 > 阈值时逐关节列出后确认。
3. **常驻急停**：顶栏红色按钮，走 `arm.emergency_stop()`，不被在途命令排队阻塞
   （急停在 worker 队列里**插队**：见 `SdkWorker.emergency()`）。
4. **调参闸门**：必须先 [刷新当前] 成功才允许下发；enable 态下发弹二次确认；
   限位写前校验当前 q 在新限位内；固化前要求失能。
5. `param_catalog.py`（范围/角色/提示）、`presets/`、`firmware_defaults.py`、
   `tuning_guide.py` —— 与协议无关，原样保留。

## 5. 删除清单

- `litetool/protocol.py`、`litetool/client.py`、`litetool/transport.py`
- `litetool/gui/session.py`（职责并入 `sdk_worker.py`）
- 对应测试 `test_protocol.py` / `test_client.py` / `test_transport.py` / `test_session.py`

## 6. 测试策略

- 全部离线：`tests/fake_arm.py` 提供一个假的 `pa.Arm`（鸭子类型），`SdkWorker` 接受
  注入工厂，故可无硬件跑线程/队列/离线判定/状态钩子。
- 新增 `test_sdk_hook.py`：断言 `pa.Arm` 上 `_a._on_status` 缝隙仍在。
- 页面冒烟测试沿用 `test_gui_smoke.py` 的思路，直接构造页面并喂 `RobotState`。
- 新增 `test_pages_sdk.py`：页面 → SDK 的**接线**端到端（真 `SdkWorker` + 假 `Arm`）。
  "功能全覆盖"这句话只有在这里才被真正验证 —— 少接一根线就会红。

## 7. 实现期补充的决定（原设计未覆盖）

1. **运动解锁改成全局一把**（不是原设想的每页一把）。要防的是"手滑下发一个大幅运动"，
   风险属于命令而非页面；四把独立开关只会诱导人条件反射地把它们全勾上。四个运动页
   共享一个解锁态，各自显示自己的横幅。

2. **急停通道改走 `Arm._write_cmd(guarded=False)`**（原设计只说"插队"）。它在 SDK 的
   写锁内原子交帧，**只写不读**，故既不被在途长命令挡住，也不与所有者线程抢帧。
   SDK 自己的 `zero_g` 保活线程用的就是这条路径。代价：不能声称"已失能"——
   界面文案严格区分「急停帧已发出」与「急停未发出」。

3. **参数页不自建线程**：改为经 `set_submit` 注入的投递函数排到所有者线程。
   原设计的"命令工作线程"与 SDK 的单消费者假设冲突。

4. **`params_io.py` 这层形状适配器**是新增的：页面要「逐写口一个 (ok, code)」以便把
   失败标到具体单元格，而 SDK 是「失败即抛异常」。适配器把 `CommandRejectedError.code`
   取出来，其余异常归 None。

5. **每页套 `QScrollArea`**：`QStackedWidget` 的最小高度取所有页的 max——关节页原本
   用竖排关节输入，页面 2500px 高，把整个窗口的最小高度顶到 2500px。两个修法都做了：
   关节输入改横排 + 每页可滚动。`test_gui_smoke.py::test_window_min_height_is_usable`
   守着这条。

6. **急停结果留在显眼处**（顶栏常驻标签），不只在日志里 —— 日志会滚，而现场用户只看
   显眼处（这正是 2026-09-13 评审的原始教训）。

## 8. 验收

`python3 -m pytest` → 209 passed。界面渲染在 offscreen 下逐页截图核对过
（分组导航 / 7 关节状态表 / 曲线轴标签 / 参数页按钮灰态）。

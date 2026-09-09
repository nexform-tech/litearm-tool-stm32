# 整臂限位自动标定 + 手动设零（zero_offset）设计

日期：2026-09-08 ｜ 范围：非中空版 v5 整臂（7 关节）
涉及仓库：`litearm-tool-stm32`（上位机工具，功能入口）＋ `litearm-stm32`（固件，权威/收口）
参考图纸：`docs/非中空版机械臂L1-B2 20260825(1).pdf`（物理碰撞限位角度图 L1-B2-00）

## 1. 背景与目标

非中空版 v5 为 DM 电机直驱（无减速）。目前固件 `q = 电机16bit编码器角 × direction`，
`zero_offset_rad` 字段虽在参数表却**未被任何代码应用**——即当前假设"电机编码器零点 = URDF
机械零点"。换电机、重新装配、相位偏移时，编码器零点与机械零点错位，导致：
- q 坐标系整体平移，软限位不再对称贴合挡块；
- `HOME`（回 q=0）回到的不是舒展姿；
- 运动学/动力学（以 URDF q=0 为基准）全部失真。

**目标**：给上位机工具增加「限位标定」能力，让装机/换电机后能可靠地把每轴编码器零点与
URDF 机械零点对齐。提供两种互补标定方式：

1. **自动贴挡标定**：逐轴伺服低速自动逼近两侧物理挡块，利用挡块名义角反推各轴
   `zero_offset`（自校验、可重复，用于整机精标）。
2. **手动设零**：人工把轴转到目标机械位置（通常零点，或工装基准角），一键把该位置定义为
   目标角，固件据当前反馈直接重算 offset（快速、用于单轴更换/兜底）。

标定结果写入固件 Flash，断电重启保持。

## 2. 名词与基准数据

- **URDF 零位（q=0）**：运动学/动力学的关节角坐标零点；`HOME` 目标。
- **机械零点**：由装配/图纸定义的关节零位。目标 = 令电机在机械零点时读数 q=0。
- **软限位** q_min/q_max：固件已有，= 图纸名义角 − 安全裕量(约 1°)，运动目标被 clamp。
- **物理挡块 / 名义挡块角 θ**：挡块相对 URDF 零位的角度，来自图纸（**工具侧 config 携带**）。
- **zero_offset**：令 `q = (pos − zero_offset)·direction` 的补偿量（pos=电机反馈角）。

名义挡块角默认表（来自 PDF，rad，四舍五入 6 位）：

| 轴 | θ₋ (deg) | θ₋ (rad) | θ₊ (deg) | θ₊ (rad) | 备注 |
|----|---------|---------|---------|---------|------|
| J1 | −162 | −2.827433 | +162 | +2.827433 | 对称 |
| J2 | −100 | −1.745329 | +100 | +1.745329 | 对称 |
| J3 | −162 | −2.827433 | +162 | +2.827433 | 对称 |
| J4 | −177 | −3.089233 | +2 | +0.034907 | **非对称**，正向仅 ~2° 行程 |
| J5 | −162 | −2.827433 | +162 | +2.827433 | 对称 |
| J6 | −90 | −1.570796 | +90 | +1.570796 | 对称 |
| J7 | −90 | −1.570796 | +90 | +1.570796 | 对称 |

> 该表可随机械改型由 config 覆盖；固件不内置机械表。

## 3. 现状机制（改动前基线）

**固件 litearm-stm32**
- 反馈换算 `User/litearm/control/control_loop.c` `can_feedback_update()`：
  `st->q = p->pos * direction; st->dq = p->vel * direction;`（offset 未用）。
- 软限 clamp 覆盖所有运动入口（move_j / move_js / MIT / MIT_ALL），目标不可越软限；
  挡块在软限外侧 ⇒ 要贴挡必须临时外扩软限。
- 跟随误差超限 → POS_VIOL → FAULT 锁存（普通命令推挡会先失能，不能直接复用）。
- 参数管理 `User/litearm/params/params.{h,c}`：`params_set_joint_ctrl/limits` 写 RAM+标脏。
- 持久化 `flash_store.{h,c}`：`joint_mutable_t` 每关节子集目前不含 offset；
  `FLASH_STORE_VERSION=2`，布局变更须 bump；CRC/长度失配回退默认。
- 命令协议 `User/litearm/hal/usb_cmd.{h,c}`：下行 0x01..0x33，上行 0x40..0x4A 已占用，
  0x4B 空闲。`CMD_PARAM_SAVE 0x25`（[M7] 使能中禁止整扇区擦写，须先 disable）。
- 安全：斜率/slew、看门狗 fail-soft、急停、tau 钳幅、软限 clamp 均由固件承担。

**工具 litearm-tool-stm32**
- 纯上位机：USB CDC 命令口，读 100Hz G8 状态帧（q/dq/tau/temp/err + flags）；
  只发命令不闭环。运动页锁定 + Δq 确认 + 常驻急停（`emergency_now` 旁路）。
- 客户端 `client.py` 现仅 ACK/RSP 配对；无 pending 时忽略除状态帧外的上行帧
  （异步事件通道需扩展）。
- 页签：监控 / 曲线 / 控制 / 运动。安全模型："不保存/不下发限位，权威在固件"。

## 4. 核心原理与公式（方向假定现 direction=+1；一般式见附注）

定义 `q = (pos − offset)·direction`。设当前（可能含旧的错 offset）贴住挡块时的读数为
`q_stop`。若挡块名义机械角为 θ：

- 单侧定 offset：令 `q_stop − offset_new = θ·direction`，即
  `offset_new = offset_cur + (q_stop − θ·direction)·?`（推导见实现；direction=+1 时
  `offset_new = offset_cur + (q_stop − θ)`）。
- **对称轴两侧自校验**：独立做 `θ₊`、`θ₋` 两次得两个建议 `offset₊、offset₋`；
  两者一致性 `|offset₊ − offset₋|`（等价于 `|q_stop₊ + q_stop₋|`）应≈0。
  接受判定：差值 < 0.0087 rad（0.5°）。通过则取平均 `offset_final = (offset₊+offset₋)/2`，
  挡块装配误差在中点被对消。
- **非对称轴 J4**：两侧各自按 θ 单点即可；正侧行程 ~2° 自动逼近不可靠 → 允许：
  (a) 只做负侧单点；或 (b) 切手动设零。
- **手动设零**：当前反馈 pos_cur，目标机械角 θt（默认 0，可任意）：
  `offset_new = pos_cur − θt·?`（direction=+1 时 `offset = pos_cur − θt`）；固件内部算，工具只发指令。

> 附注：direction=−1 的轴，电机反向安装，上述公式统一改为在固件内用
> `q=(pos−offset)·direction` 语义实现，offset 恒在 pos 空间表达，不另设符号。

## 5. 方案 A — 固件改动清单（litearm-stm32）

### A1. 换算接入 zero_offset
`can_feedback_update()`：`st->q = (p->pos − jp.zero_offset_rad) * direction;`
`st->dq` 同步考虑（dq 一般同乘 dir 不变，offset 常量为 0 对 dq 无影响，仅 q 加项）。
同时核对软限 clamp、HOME、FK 是否均消费 `g_arm.joint[].q`（是，则一处接入全局生效）。

### A2. 持久化扩展
- `joint_mutable_t` 增加 `float zero_offset_rad;`
- `FLASH_STORE_VERSION` 2 → 3（布局变更，CRC/长度失配自动回退默认，安全）；
- `flash_store.c` load/save 拷贝映射补 offset 字段。

### A3. 参数接口 + 命令
- `params.h/.c`：新增 `bool params_set_joint_zero(uint8_t idx, float offset);`
  （写 RAM + `flash_store_mark_dirty`；idx 越界 / !isfinite 返回 false）。
- `usb_cmd.h/.c` 下行：
  - `CMD_SET_JOINT_ZERO 0x2C { idx(1B) + offset(f32 LE) }` → ACK/ERR。
    安全门禁：整臂 `ctrl_is_armed()`（在使能/标定运动中）时拒绝 `ERR 0x04`（须先 disable），
    防止 offset 突变引发 q 读数/目标瞬时错位。偏移只允许在失能下写入。
  - `CMD_CALIB_APPROACH 0x2B { idx(1B) + sign(1B: 0=+ 1=−) + θ_nominal(f32 LE) }`
    → 立即 ACK，结果异步经上行帧回传（见 A4/A5）。
- 上行新增 `RSP_CALIB_RESULT 0x4B`（0x4A 后空闲 ID）。

### A4. 自动贴挡引擎（固件内状态机，400Hz tick 内推进）
逐轴、逐方向独立执行一次 `CALIB_APPROACH`：

1. 快照该轴原软限 `q_min/q_max` 与运行参数；**临时外扩软限**越过挡块
   （如扩到 θ_nominal ± 0.5 rad，仅 RAM，不保存——目标 clamp 仍以它为准）。
2. 低刚度位置逼近：推力受控（接触力矩钳 ~20–30% tau_max）、推进速度上限低
   （~0.15 rad/s，远低于 vel_max，复用现有 slew/斜率限制防跳变）。
3. **贴挡判定**（核心，避免误触 FAULT）：速度≈0 且位置停滞 |Δq|<ε 持续满 N 拍
   （~200 ms）即判到位；**不置 POS_VIOL/FAULT**。采集 `q_stop`。
4. 停推 → 回退到原软限内侧 ~0.2 rad → 恢复原软限值。
5. 由固件按 θ_nominal 算出该方向建议 offset（见 §4），组 `RSP_CALIB_RESULT` 上报：
   payload = `idx(1B) + sign(1B) + q_stop(f32) + offset_sugg(f32) + status(1B)`
   status: 0=ok 1=贴挡超时 2=行程异常/未识别 3=被取消。
6. 全程：超时兜底（~15 s）、可被急停打断、断链即停并回退软限；执行期间状态帧照常
   100Hz。单次只允许一个轴在标定（互斥，其余命令收到 ERR 0x05 忙）。

引擎复用 move 轨迹通道还是独立低层推进在实现阶段定；验收点是不新增"乱飞"路径、
贴挡不锁存、可急停。

### A5. 命令/事件调度
- `CMD_CALIB_APPROACH` 在使能或失能均可（引擎自身先使能该轴）；与状态帧、急停并发
  安全（见 §8）。
- `RSP_CALIB_RESULT` 走 `usb_cmd_reply` 现有可靠补发通道（F4 机制，不被周期上报抢占丢弃）。

## 6. 方案 B — 工具改动清单（litearm-tool-stm32）

### B1. 协议层 `protocol.py`
- 新下行常量 `CMD_CALIB_APPROACH 0x2B`、`CMD_SET_JOINT_ZERO 0x2C`；
  新上行 `RSP_CALIB_RESULT 0x4B`；编解码纯函数 + 黄金向量测试。
- config：`limits_calib.yaml` 或 config.yaml 增 `nominal_stop_deg` 每轴 [θ−, θ+] 表
  （默认取 PDF，§2 表）。

### B2. 客户端 `client.py`
- 方法：`set_joint_zero(idx, offset)`、`calib_approach(idx, sign, theta)`、
  复用现有 `disable/reset/emergency_now`。
- **异步事件支持**：`handle_frame` 增加无 pending 时也分发 `RSP_CALIB_RESULT`
  （现实现只认 ACK/ERR 与状态帧）→ 注入上层回调 / bridge 信号。

### B3. GUI：新增「标定」页签
状态机向导（每轴步骤推进），复用现有安全锁与常驻急停：

1. **预检**：勾选"每轴挡块刚性、臂周无障碍、急停可及"；检查在线/固件版本 ≥ 支持版本。
2. **起点**：提示把臂摆到零位舒展姿（必要时 HOME；若 offset 错得离谱可选手动先设零粗对齐）。
3. **逐轴二选一**（每轴可独立选择，未选轴跳过）：
   - **自动贴挡**：依次发 +向、−向 `CALIB_APPROACH`，等 `RSP_CALIB_RESULT`；
     对称轴做一致性校验（§4），非对称 J4 提示单侧或手动；
   - **手动设零**：提示人工转到目标位 → 等状态帧静止稳定 → 一键 `set_joint_zero(idx, 目标角θt)`。
4. **结果确认表**：每轴显示 旧 offset → 建议 offset + 变化量(deg) + 一致性状态；
   人工逐轴确认。
5. **落盘**：整臂 `disable → set_joint_zero×各确认轴 → PARAM_SAVE → 完成`；
   登记一次标定日志（旧→新、日期、轴、方式）到工具本地，供追溯（呼应调参台账）。

UI 提示语覆盖：自动逼近会短暂"贴挡压紧"；手动设零需在静止下进行；
写 flash 前会 disable（臂会掉磁，需支撑）。

### B4. 测试（工具，离线可跑）
- protocol：0x2B/0x2C/0x4B 帧黄金向量、CRC；
- offset 计算纯函数：对称轴中点、一致性阈值、J4 单侧、手动设零；
- client FakeLink：异步 `RSP_CALIB_RESULT` 分发、超时、急停中断；
- 向导状态机：预检未过禁止、逐轴跳过、结果确认、写盘顺序、中途断链/急停复位。

## 7. 与既有安全模型的衔接（对照"不允乱飞"铁律）

| 铁律要求 | 本设计落实 |
|---|---|
| 命令通道斜率限制，q_ref 跳变 ≤ v·dt | 引擎复用固件 slew/斜坡；推进速度上限 0.15 rad/s |
| 单一收口 | 贴挡推进为固件内新状态机唯一入口（0x2B），不新增上位机闭环路径 |
| 看门狗 fail-soft | 引擎在 400Hz 中断 tick 推进，随控制循环喂狗；异常即回退软限 |
| 固件兜底 | 超时 15 s、急停即停、断链回退、贴挡不置 FAULT、软限临时外扩不落 flash |
| 工具侧意图确认 | 运动页锁定 + 无障碍勾选 + 逐轴结果确认 + 写 flash 需 disable |

## 8. 测试与验收

**固件单测/离线**：offset 换算正/负向用例、`params_set_joint_zero` 边界、flash v3
读写与回退；引擎贴挡判据与超时路径（可 host-golden 风格仿真）。真机：

1. 换单电机后**手动设零**：对到机械零位 → 设零 → enable 后 HOME 到舒展姿，q 表全部≈0。
2. 整机**自动标定**：7 轴逐轴 ± 贴挡，全轴一致性 <0.5°；写 flash 后断电重启，offset 保持；
   HOME 舒展姿正确；软限/挡块间隙符合预期。
3. 急停/断链中断标定：引擎回退软限、无 FAULT 锁存、工具向导可复位重来。
4. J4 手动或单侧路径单独演练。

## 9. 阶段切分（推荐先小闭环后精标）

- **阶段 1（固件小改 + 工具基础）**：offset 换算接入 + flash v3 + `0x2C` 手动设零 +
  工具"标定向导（先只含手动设零路径）+ 结果确认/写盘"。 快速闭环单轴更换场景。
- **阶段 2（自动贴挡）**：`0x2B` 引擎 + `0x4B` 结果 + 工具自动路径与一致性校验。

## 10. 待决策（建议见括号）

1. 手动设零目标角：仅支持 0，还是任意角 θt？
   （建议：命令按任意 θt 实现，UI 默认 0，覆盖"对工装基准角"场景。）
2. 是否按阶段 1→2 分批落地，还是一次全做？（建议分批：阶段 1 先形成可用闭环。）
3. 贴挡接触力比例（~20–30% tau_max）与推进速度需真机手感定，先按保守值实现。

## 11. 风险

- **挡块/电机柔性**：贴挡压紧读数可能受结构压缩影响 → 用最小贴挡力 + 两侧中点对消。
- **符号方向**：direction 现全 +1，负向轴未实机验证 → 阶段验收第一项先验手动设零符号。
- **flash v3 兼容**：老固件存档 CRC/长度失配会回退默认（安全但丢调参）→ 升级提示明确。
- **引擎实现复杂度**：贴挡判据在直驱低速下需实测整定，阶段 2 预留真机联调窗口。

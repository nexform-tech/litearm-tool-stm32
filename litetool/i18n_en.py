"""English translations (source Chinese text -> English).

Generated from the UI/core string inventory; keys are the Chinese source
texts passed to ``i18n.tr()``. Missing entries fall back to the source.
"""

EN = {'{0=v1 误差方向, 1=v2 SE1 速度方向, 2=drag 版(拖动用)}': '{0=v1 error direction, 1=v2 SE1 velocity direction, 2=drag '
                                              'version (for hand-guiding)}',
 'global.ff_mask 须为 [0, {mask}] 的整数, 实际 {value}': 'global.ff_mask must be an integer in [0, {mask}], got '
                                                  '{value}',
 'global.ff_mask 须为整数': 'global.ff_mask must be an integer',
 'global.{key} 须为长度 {n} 的数组': 'global.{key} must be an array of length {n}',
 'global 须为对象': 'global must be an object',
 'joints[{i}].name 应为 J{axis}, 实际 {name}': 'joints[{i}].name should be J{axis}, got {name}',
 'joints[{i}] 须为对象': 'joints[{i}] must be an object',
 'joints 须为长度 {n} 的数组 (J1..J7, 顺序即关节号)': 'joints must be an array of length {n} (J1..J7, in joint order)',
 '参数文件顶层须为对象 (joints + global)': 'The parameter file must be an object with joints + global',
 '关节限位非法: q_min({qmin}) ≥ q_max({qmax})': 'Invalid joint limits: q_min({qmin}) ≥ q_max({qmax})',
 '{label}={value} 超出范围 [{lo}, {hi}]': '{label}={value} is outside the range [{lo}, {hi}]',
 '{label} 摩擦模型仅允许 0/1/2': '{label}: friction model must be 0/1/2',
 '{label} 为 NaN': '{label} is NaN',
 '{label} 须为数值': '{label} must be a number',
 '夹爪任务': 'gripper task',
 '未预期错误': 'unexpected error',
 'g = R(base_rpy)ᵀ·(0,0,-{g0})，与固件 kin.c 同式。改 rpy 会自动重算向量；直接改向量则 rpy 标为「(自定义)」（反向不唯一，不做反解）。': 'g = '
                                                                                              'R(base_rpy)ᵀ·(0,0,-{g0}), '
                                                                                              'the same '
                                                                                              'formula as '
                                                                                              'firmware '
                                                                                              'kin.c. '
                                                                                              'Changing rpy '
                                                                                              'recomputes '
                                                                                              'the vector; '
                                                                                              'editing the '
                                                                                              'vector '
                                                                                              'directly '
                                                                                              'marks rpy as '
                                                                                              '"(custom)" '
                                                                                              '(the inverse '
                                                                                              'is not '
                                                                                              'unique, so no '
                                                                                              'inverse solve '
                                                                                              'is '
                                                                                              'attempted).',
 '监视': 'Monitor',
 '操作': 'Operate',
 '参数': 'Parameters',
 '刷新': 'Refresh',
 '连接': 'Connect',
 '我已确认机械臂周围无障碍、急停可及': 'Arm area clear; E-stop reachable',
 '运动类页面（整机的回零 / 关节 / 笛卡尔 / 零重力）在此勾选前一律锁定。\n断线、急停、FAULT、复位会自动重新锁定。': 'Motion pages (whole-arm homing / joint '
                                                                    '/ Cartesian / zero-G) stay locked until '
                                                                    'this box is checked.\n'
                                                                    'Disconnect, emergency stop, FAULT, and '
                                                                    'reset re-lock them automatically.',
 '⛔ 急停': '⛔ E-STOP',
 '点击复制诊断包': 'Click to copy diagnostics bundle',
 '总览': 'Overview',
 '状态表 + 100Hz 曲线': 'Status table + 100Hz plot',
 '数字孪生（只读，不碰串口）': 'Digital twin (read-only, no serial port access)',
 '采集': 'Capture',
 '固件 300Hz 控制拍采集与导出': 'Capture and export firmware 300Hz control ticks',
 '日志': 'Log',
 '结构化 JSONL：实时/筛选/历史回读/导出': 'Structured JSONL: live / filter / history read-back / export',
 '整机': 'Whole arm',
 '使能/复位/清故障/回零/限速/park': 'Enable/reset/clear faults/home/speed limit/park',
 '故障': 'Faults',
 '当前故障/原因/处置/事件历史/诊断包': 'Current faults/causes/remedies/event history/diagnostics bundle',
 '关节': 'Joint',
 '笛卡尔': 'Cartesian',
 '零重力': 'Zero-G',
 '拖动示教（保活由 SDK 维持）': 'Drag teaching (keep-alive maintained by SDK)',
 '夹爪': 'Gripper',
 '夹爪（仅 Linux）': 'Gripper (Linux only)',
 'LiteGrip（仅 Linux）：连接/使能/开合/抓取/标定': 'LiteGrip (Linux only): connect/enable/open-close/grasp/calibration',
 '参数表': 'Parameters',
 '关节/前馈参数读写与批量导入导出': 'Read/write joint and feedforward parameters, batch import/export',
 '调参指南': 'Tuning guide',
 '公式 / 症状速查 / 逐参数详解': 'Formulas / symptom quick reference / per-parameter details',
 '诊断': 'Diagnostics',
 'KIN_BENCH / 启动原因 / 链路计数': 'KIN_BENCH / boot reason / link counters',
 '安装方向': 'Mounting',
 'gravity 向量 (0x28 item6) —— 正装/侧装/倒装': 'gravity vector (0x28 item6) — upright/side/inverted mounting',
 '授权': 'Activation',
 '读取 UID / 在线激活（0x2F / 0x3F）': 'Read UID / online activation (0x2F / 0x3F)',
 '固件升级': 'Firmware',
 'USB DFU (0483:DF11) —— 选镜像 / 烧录 / 回读校验': 'USB DFU (0483:DF11) — select image / flash / read-back '
                                           'verification',
 '设置': 'Settings',
 '界面语言与运行偏好': 'UI language and runtime preferences',
 '没有发现 STM32 CDC 设备': 'No STM32 CDC device found',
 '未连接': 'Not connected',
 '[INFO] LiteArm Tool STM32 —— 交互层经 litearm；硬防护权威仍在固件': '[INFO] LiteArm Tool STM32 — interaction layer via '
                                                        'litearm; hard safeguards remain in firmware',
 '串口:': 'Serial port:',
 '● 离线': '● Offline',
 '固件: —': 'Firmware: —',
 '已断开': 'Disconnected',
 '[INFO] 已断开（用户操作）': '[INFO] Disconnected (user action)',
 '● 重连中({n})': '● Reconnecting ({n})',
 '[ERR] 升级后重连失败: {detail}': '[ERR] Reconnect after update failed: {detail}',
 '急停': 'Emergency stop',
 '\n\n当前各轴: {q}': '\n\nCurrent axes: {q}',
 '读故障详情': 'Read fault details',
 '\n\n将被恢复出力的轴: {axes}': '\n\nAxes to re-energize: {axes}',
 '全局限速 {percent}%': 'Global speed limit {percent}%',
 '读状态': 'Read status',
 '读 TCP': 'Read TCP',
 '读 TCP（movel 后）': 'Read TCP (after movel)',
 '点动 {axis}': 'Jog {axis}',
 '[INFO] --fake 模式：SDK 假传输，不连接真实串口': '[INFO] --fake mode: SDK fake transport, no real serial connection',
 '已连接': 'Connected',
 '[OK] 诊断包已复制并保存: {path}': '[OK] Diagnostics bundle copied and saved: {path}',
 '[OK] 已到位': '[OK] In position',
 '假设备 (--fake)': 'Fake device (--fake)',
 '无可选串口': 'No serial ports available',
 '未发现串口设备，请检查 USB 连接。': 'No serial device found. Check the USB connection.',
 '用户断开': 'User disconnect',
 '断开': 'Disconnect',
 '● 升级中': '● Updating',
 '固件: 升级中': 'Firmware: updating',
 '链路断开': 'Link lost',
 '[INFO] 固件升级期间：连接/解锁已禁用，升级结束后自动恢复': '[INFO] During firmware update: connect/unlock are disabled and restore '
                                     'automatically when the update ends',
 '升级结束': 'Update finished',
 '[OK] 升级后已重新连接: {port} · {fw}': '[OK] Reconnected after update: {port} · {fw}',
 '[WARN] 未连接，解锁无效': '[WARN] Not connected; unlock has no effect',
 '[WARN] 运动控制已解锁': '[WARN] Motion control unlocked',
 '[INFO] 运动控制已锁定': '[INFO] Motion control locked',
 '[WARN] 运动控制已锁定 — {reason}': '[WARN] Motion control locked — {reason}',
 '[WARN] 拒绝 {op} — 未连接': '[WARN] {op} rejected — not connected',
 '[WARN] 拒绝 {op} — FAULT/急停锁存中，先 [清故障] 或 [复位]': '[WARN] {op} rejected — FAULT/emergency stop latched; [Clear '
                                                'faults] or [Reset] first',
 '[WARN] 拒绝 {op} — 运动未解锁（先勾选顶栏的确认项）': '[WARN] {op} rejected — motion not unlocked (check the confirmation '
                                      'box in the top bar first)',
 '[WARN] 急停：已丢弃 {n} 条排队中的命令': '[WARN] Emergency stop: dropped {n} queued commands',
 '[WARN] 急停：零重力会话未能正常收尾（{err}）': '[WARN] Emergency stop: zero-G session did not close cleanly ({err})',
 '[WARN] 急停帧已发出 —— 请目视确认臂已停止（帧发出≠固件已执行）': '[WARN] Emergency stop frame sent — visually confirm the arm has '
                                          'stopped (frame sent ≠ firmware executed)',
 '[ERR] 急停未发出（{why}）—— 请立即用硬件急停/断电': '[ERR] Emergency stop not sent ({why}) — use the hardware emergency '
                                     'stop / cut power immediately',
 '急停帧已发出 — 请目视确认臂已停止': 'Emergency stop frame sent — visually confirm the arm has stopped',
 '⚠ 急停未发出 — 请立即用硬件急停/断电': '⚠ Emergency stop not sent — use the hardware emergency stop / cut power '
                          'immediately',
 '[INFO] 识别到 {n} 个关节': '[INFO] Detected {n} joints',
 '[WARN] 故障 J{axis} {title}': '[WARN] Fault J{axis} {title}',
 '回零 home': 'Home (home)',
 '已复位': 'Reset complete',
 '确认回零 home': 'Confirm home (home)',
 '各臂轴将回到 URDF 零位（固件把速度写死为 0.10 的低速）。{q}\n\n确认下发？': 'All arm axes will return to the URDF zero position '
                                                   '(firmware hard-codes the speed to a low 0.10).{q}\n'
                                                   '\n'
                                                   'Send now?',
 '[WARN] 故障详情不可用: {text}': '[WARN] Fault details unavailable: {text}',
 '确认清故障 clear_faults': 'Confirm clear faults (clear_faults)',
 '清除故障锁存。若臂处于使能态，被锁轴会重新出力。{axes}\n\n确认下发？': 'Clear the fault latch. If the arm is enabled, latched axes will '
                                            're-energize.{axes}\n'
                                            '\n'
                                            'Send now?',
 '确认复位 reset': 'Confirm reset (reset)',
 '复位会清除故障并退出急停锁存 —— 之后固件不再阻止运动。\n\n确认下发？': 'Reset clears faults and exits the emergency stop latch — '
                                           'firmware will no longer block motion afterwards.\n'
                                           '\n'
                                           'Send now?',
 '[WARN] 拒绝 {op} — 拿不到当前关节角作基线（等一帧状态再试）': '[WARN] {op} rejected — no current joint angles for a baseline '
                                          '(wait for a status frame and retry)',
 '[INFO] 当前没有在途运动，按普通 movej 下发': '[INFO] No motion in flight; sending as a normal movej',
 '确认运动幅度': 'Confirm motion range',
 '以下关节与当前位置差异超过 {threshold} rad：\n\n{lines}\n\n确认下发？': 'The following joints differ from the current '
                                                       'position by more than {threshold} rad:\n'
                                                       '\n'
                                                       '{lines}\n'
                                                       '\n'
                                                       'Send now?',
 '[INFO] 尚无当前位姿基线，先读一次 TCP 再判幅度': '[INFO] No current pose baseline yet; read TCP once before judging the '
                                  'range',
 '读 TCP（movep 前置）': 'Read TCP (before movep)',
 '[WARN] 拒绝 movep — 读不到当前 TCP，无法判断幅度（{why}）': '[WARN] movep rejected — cannot read current TCP, so the range '
                                              'cannot be judged ({why})',
 '读 TCP（movel 前置）': 'Read TCP (before movel)',
 '[WARN] 拒绝 movel — 读不到当前 TCP，无法判断幅度（{why}）': '[WARN] movel rejected — cannot read current TCP, so the range '
                                              'cannot be judged ({why})',
 '[OK] movel 到位': '[OK] movel in position',
 '[WARN] movel 规划完成但未停在目标（settled=False，settle_err={err:.3f} rad）': '[WARN] movel planned but did not settle '
                                                                    'at target (settled=False, '
                                                                    'settle_err={err:.3f} rad)',
 '[WARN] 受控停止帧已发出 —— 在途点动/直线规划将被固件作废': '[WARN] Controlled stop frame sent — firmware will void in-flight '
                                       'jog/linear plans',
 '[ERR] 受控停止未发出: {why}': '[ERR] Controlled stop not sent: {why}',
 '零重力进入': 'Enter zero-G',
 '零重力进入 (保活 {period:.3f}s)': 'Enter zero-G (keep-alive {period:.3f}s)',
 '零重力退出 + 保持': 'Exit zero-G + hold',
 '固件升级进行中': 'Firmware update in progress',
 '固件正在烧录/升级。现在退出会中断升级，可能让板子停在 bootloader 或导致变砖。\n\n确定要退出吗？': 'Firmware is being flashed/updated. Exiting now '
                                                             'interrupts the update and may leave the board '
                                                             'stuck in the bootloader or brick it.\n'
                                                             '\n'
                                                             'Exit anyway?',
 '[WARN] {text}（已被新的运动接管）': '[WARN] {text} (superseded by new motion)',
 '[ERR] 诊断包导出失败: {err}': '[ERR] Failed to export diagnostics bundle: {err}',
 '[ERR] 连接失败: {err}': '[ERR] Connection failed: {err}',
 '连接失败': 'Connection failed',
 '● 在线': '● Online',
 '固件: {version}': 'Firmware: {version}',
 '[WARN] 升级重连前关闭串口失败: {err}': '[WARN] Failed to close serial port before reconnect after update: {err}',
 '原因 {reason}': 'Reason {reason}',
 '检测到 FAULT/急停锁存': 'FAULT/emergency stop latch detected',
 '清故障 clear_faults': 'Clear faults (clear_faults)',
 '[WARN] 接管 movej 已发出（sp={speed:.2f}）—— 固件会作废在途点动/直线规划': '[WARN] Takeover movej sent (sp={speed:.2f}) — '
                                                         'firmware will void in-flight jog/linear plans',
 '[ERR] 接管 movej 未发出: {why}': '[ERR] Takeover movej not sent: {why}',
 '[OK] IK 求解成功: {q}': '[OK] IK solved: {q}',
 '确认位姿幅度': 'Confirm pose range',
 'movep 目标与当前位姿：\n\n{summary}\n\n确认下发？': 'movep target vs. current pose:\n\n{summary}\n\nSend now?',
 'movel 目标与当前位姿：\n\n{summary}\n\n确认下发？': 'movel target vs. current pose:\n\n{summary}\n\nSend now?',
 '读不到当前 TCP，点动中止': 'Cannot read current TCP; jog aborted',
 '[OK] KIN_BENCH 完成': '[OK] KIN_BENCH complete',
 '离线': 'Offline',
 '链路': 'Link',
 '\n\n检测到一块停在 bootloader (DFU) 里的控制器：它没有应用态可连，「连接」不会成功。请到「参数 → 固件升级」直接烧录，或断电重新上电。': '\n'
                                                                                    '\n'
                                                                                    'A controller stuck in '
                                                                                    'the bootloader (DFU) '
                                                                                    'was detected: it has no '
                                                                                    'application to connect '
                                                                                    'to, so Connect will not '
                                                                                    'succeed. Go to '
                                                                                    'Parameters → Firmware '
                                                                                    'Update to flash it '
                                                                                    'directly, or '
                                                                                    'power-cycle the board.',
 '[WARN] 升级后重连失败 {detail}': '[WARN] Reconnect after update failed {detail}',
 '[WARN] 故障: {detail}': '[WARN] Fault: {detail}',
 '复位 reset': 'Reset (reset)',
 'J{axis}: 原因 {reason}': 'J{axis}: reason {reason}',
 '使能 enable': 'Enable (enable)',
 '固件无应答': 'No response from firmware',
 '失能 disable': 'Disable (disable)',
 "<b>激活注册信息同意书</b><br>激活会把下面这些内容发送给激活服务（act.nexform.tech）。每一项后面写了为什么要它——没有别的用途，也没有别的字段。<br><br><b>姓名、手机号、单位、邮箱、微信号</b> —— 用于签发授权凭据，并在需要时联系到你（现场排障电话更快）。<br><b>所在地区、所属行业、用途说明</b> —— 用于登记这台设备用在哪里、做什么，作为服务与统计的依据。<br><b>设备 UID（24 位十六进制）</b> —— 用来定位这台机器：凭据只对它有效，换一台要重新签发。<br><b>上位机 / SDK / 固件版本</b> —— 排查问题时判断你用的是哪一套，省一轮来回。<br><br>以上内容只用于签发授权、售后联系与服务登记；需要更正或删除请联系供应商。详见 <a href='{privacy_url}'>隐私政策</a>。<br><span style='color:#6b7683'>同意书版本 {version}</span>": '<b>Activation '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'Registration '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'Consent</b><br>Activation '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'sends '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'following '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'information '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'activation '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'service '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '(act.nexform.tech). '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'Each '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'item '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'states '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'why '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'it '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'needed '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'there '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'no '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'other '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'purpose, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'no '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'other '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'fields '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'are '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'collected.<br><br><b>Name, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'phone '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'number, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'organization, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'email, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'WeChat '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'ID</b> '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'used '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'issue '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'activation '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'credential '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'contact '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'you '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'when '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'needed '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '(a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'phone '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'call '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'faster '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'on-site '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'troubleshooting).<br><b>Region, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'industry, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'intended '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'use</b> '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'used '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'record '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'where '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'what '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'this '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'device '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'used, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'as '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'basis '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'service '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'statistics.<br><b>Device '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'UID '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '(24-digit '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'hex)</b> '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'used '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'identify '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'this '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'machine: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'credential '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'valid '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'only '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'it, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'different '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'unit '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'requires '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'new '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'credential.<br><b>Host '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'tool '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'SDK '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'firmware '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'versions</b> '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'used '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'determine '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'which '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'build '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'you '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'are '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'running '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'when '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'troubleshooting, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'saving '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'round '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'trip.<br><br>The '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'above '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'used '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'only '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'issue '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'activation, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'after-sales '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'contact, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'service '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'registration; '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'contact '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'your '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'supplier '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'correct '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'or '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'delete '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'it. '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'See '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '<a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      "href='{privacy_url}'>Privacy "
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'Policy</a> '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'details.<br><span '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      "style='color:#6b7683'>Consent "
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      'version '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                      '{version}</span>',
 '未激活': 'Not activated',
 '已激活': 'Activated',
 '已激活（产线模式）': 'Activated (production-line mode)',
 '设备未应答（固件过旧或链路异常）': 'Device not responding (firmware too old or link error)',
 '请先勾选同意发送注册信息。': 'Check the box to agree to sending registration information first.',
 '设备 UID 形态不对 —— 请重新读取设备信息。': 'Device UID has an invalid format — please read the device info again.',
 '设备 UID 不是合法的 24 位十六进制 —— 请重新连接机械臂后重试。': 'Device UID is not a valid 24-digit hex string — please reconnect '
                                          'the robot arm and try again.',
 '服务端返回的凭据不是这台机器的 —— 请联系供应商核对。': 'The credential returned by the server is not for this machine — please '
                                 'contact the supplier to verify.',
 '服务端凭据格式比本上位机新 —— 请升级上位机。': 'The server credential format is newer than this host tool — please upgrade the '
                             'host tool.',
 '注册信息没填完 —— 带 * 的字段都要填。': 'Registration info is incomplete — all fields marked with * are required.',
 '注册信息有一项过长 —— 请核对姓名、手机号、单位、邮箱、微信号、地区、行业与用途说明的长度。': 'One registration field is too long — check the length '
                                                    'of name, phone number, organization, email, WeChat ID, '
                                                    'region, industry and intended use.',
 '手机号不符合要求 —— 需为 11 位手机号。': 'Phone number is invalid — must be an 11-digit mobile number.',
 '邮箱不符合要求 —— 格式不正确。': 'Email is invalid — incorrect format.',
 '姓名不符合要求 —— 只能是文字，2–32 个字，不能含数字。': 'Name is invalid — letters only, 2–32 characters, no digits.',
 '本地程序没有配置激活服务地址 —— 请用 --activation-url 启动。': 'No activation service URL configured for this host tool — '
                                              'start it with --activation-url.',
 '连不上激活服务 —— 请检查这台机器的网络。': "Cannot reach the activation service — check this machine's network.",
 '激活服务上没有这台机器的凭据 —— 请把设备 UID 发给供应商核对补录，然后重新提交。': 'No credential for this machine on the activation service — '
                                                 'send the device UID to the supplier to verify and add it, '
                                                 'then submit again.',
 '激活服务暂时拒绝了本次请求（请求过于频繁）—— 请过一会儿再试。': 'The activation service temporarily rejected this request (too many '
                                     'requests) — try again in a while.',
 '激活服务正在维护 —— 请稍后重试。': 'The activation service is under maintenance — please try again later.',
 '激活服务要求提供订单号 / 激活码 —— 请升级上位机，或联系供应商。': 'The activation service requires an order number / activation code — '
                                        'please upgrade the host tool or contact the supplier.',
 '激活服务拒绝了这份注册信息 —— 请核对带 * 的字段后重新提交（若反复出现，说明网站的字段规则已更新）。': 'The activation service rejected this registration '
                                                          'info — check the fields marked * and submit again '
                                                          "(if it keeps happening, the website's field rules "
                                                          'have changed).',
 '激活服务出错了 —— 请稍后重试；一直失败请联系供应商。': 'The activation service encountered an error — please try again later; '
                                 'contact the supplier if it keeps failing.',
 '激活服务的应答不可用 —— 请稍后重试。': 'The activation service response is unusable — please try again later.',
 '读不到设备的授权记录 —— 请检查 USB 链路后重试。': "Cannot read the device's activation record — check the USB link and try "
                                 'again.',
 '这台固件没有授权功能（需要 1.8.0 及以上）—— 请升级固件。': 'This firmware has no activation support (requires 1.8.0 or later) — '
                                      'please upgrade the firmware.',
 '固件只在失能状态下接受写入授权记录 —— 请先按「失能」，再重新提交。': 'Firmware only accepts activation record writes while disabled — '
                                        'click "Disable" first, then submit again.',
 '固件拒绝了这次写入（已激活过 / 凭据与本机不符 / 写入失败共用一个错误码）—— 请点「读取授权记录」看授权状态；仍未激活就核对 UID 后重新申请凭据。': 'Firmware rejected this '
                                                                                   'write (already activated '
                                                                                   '/ credential mismatch / '
                                                                                   'write failure share one '
                                                                                   'error code) — click '
                                                                                   '"Read activation record" '
                                                                                   'to check activation '
                                                                                   'status; if still not '
                                                                                   'activated, verify the '
                                                                                   'UID and request a new '
                                                                                   'credential.',
 '读取授权记录': 'Read activation record',
 '复制 UID': 'Copy UID',
 '设备授权记录': 'Device activation record',
 '在线激活（未激活设备）': 'Online activation (unactivated device)',
 '查看《激活注册信息同意书》': 'View the Activation Registration Info Consent',
 '我已阅读并同意《激活注册信息同意书》': 'I have read and agree to the Activation Registration Info Consent',
 '提交并激活': 'Submit and activate',
 '这台固件没有授权功能（需要 {major}.{minor}.{patch} 及以上）—— 请升级固件': 'This firmware has no activation support (requires '
                                                       '{major}.{minor}.{patch} or later) — please upgrade '
                                                       'the firmware',
 '激活服务: {url}': 'Activation service: {url}',
 '状态': 'Status',
 '记录版本': 'Record version',
 '客户号': 'Customer ID',
 '签发日': 'Issue date',
 '连接设备后点「读取授权记录」。': 'Connect the device, then click "Read activation record".',
 '联系人*': 'Contact*',
 '手机号*': 'Phone number*',
 '单位*': 'Organization*',
 '微信（可选）': 'WeChat (optional)',
 '邮箱*': 'Email*',
 '地区*': 'Region*',
 '行业（可选）': 'Industry (optional)',
 '用途（可选）': 'Intended use (optional)',
 '正在读取授权记录…': 'Reading activation record…',
 '这台固件没有授权命令（版本过旧）—— 请升级固件': 'This firmware has no activation commands (version too old) — please upgrade '
                             'the firmware',
 '正在处理…': 'Processing…',
 '未连接设备': 'No device connected',
 '请先读取授权记录': 'Please read the activation record first',
 '这台设备已激活': 'This device is already activated',
 '设备已使能 —— 请先在「整机」页失能': 'Device is enabled — please disable it on the "Whole machine" page first',
 '请先阅读并勾选同意书': 'Please read and check the consent first',
 '激活前读取 UID': 'Read UID before activation',
 '凭据已领到，正在写入设备…': 'Credential obtained, writing to device…',
 '写入授权凭据': 'Write activation credential',
 '[OK] 设备 UID 已复制到剪贴板': '[OK] Device UID copied to clipboard',
 '读取失败：{text} —— 下面是上一次读数（提交前会重新核对 UID）。': 'Read failed: {text} — below is the previous reading (UID will be '
                                           're-verified before submitting).',
 '读取失败：{text}': 'Read failed: {text}',
 '{why}。下面是上一次读数（提交前会重新核对 UID）。': '{why}. Below is the previous reading (UID will be re-verified before '
                                  'submitting).',
 '{why}。无法确认授权状态，也不会提交注册信息。': '{why}. Activation status cannot be confirmed, and registration info will not '
                              'be submitted.',
 '还没有可信的设备 UID': 'No trusted device UID yet',
 '未连接设备。': 'No device connected.',
 '请先阅读并勾选同意书。': 'Please read and check the consent first.',
 '还没有可信的设备 UID —— 请先点「读取授权记录」。': 'No trusted device UID yet — click "Read activation record" first.',
 '设备已使能 —— 请先在「整机」页失能，再提交激活。': 'Device is enabled — please disable it on the "Whole machine" page before '
                               'submitting activation.',
 '连接已变化 —— 请重新读取设备信息后再提交。': 'Connection changed — please read the device info again before submitting.',
 '读取设备 UID 失败：{text}': 'Failed to read device UID: {text}',
 '读不到可信 UID —— 不会提交注册信息。': 'Cannot read a trusted UID — registration info will not be submitted.',
 '设备 UID 与刚才读取的不一致 —— 请核对后重试。': 'Device UID differs from the earlier reading — please verify and try again.',
 '[WARN] 连接已变化 —— 丢弃这次激活结果': '[WARN] Connection changed — discarding this activation result',
 '[ERR] 激活请求失败({reason}): {err}': '[ERR] Activation request failed ({reason}): {err}',
 '[WARN] 连接已变化 —— 丢弃这次写入结果': '[WARN] Connection changed — discarding this write result',
 '[OK] 激活成功 —— 授权记录已回读确认': '[OK] Activation successful — activation record confirmed by read-back',
 '未知': 'Unknown',
 '写入已受理，但回读未确认激活 —— 请点「读取授权记录」再确认。': 'Write accepted, but read-back did not confirm activation — click "Read '
                                     'activation record" to confirm.',
 '[WARN] 授权写入已受理，但回读未确认激活（设备状态 {state}）': '[WARN] Activation write accepted, but read-back did not confirm '
                                          'activation (device state {state})',
 '收起《激活注册信息同意书》': 'Collapse the Activation Registration Info Consent',
 '处理中…': 'Processing…',
 '产线码': 'Production line code',
 '已激活 —— 使能可用；授权记录不可修改。': 'Activated — enable is available; the activation record cannot be modified.',
 '未激活：`enable` 会被固件拒绝（0x10/0x08）。填写下方注册信息并提交即可激活。': 'Not activated: `enable` will be rejected by firmware '
                                                    '(0x10/0x08). Fill in the registration info below and '
                                                    'submit to activate.',
 '激活失败：{err}': 'Activation failed: {err}',
 '[ERR] 写入授权失败: {err}': '[ERR] Activation write failed: {err}',
 '写入授权失败：{text}': 'Activation write failed: {text}',
 '[ERR] 写入授权失败: {text}': '[ERR] Activation write failed: {text}',
 '[WARN] 复制 UID 失败: {err}': '[WARN] Copy UID failed: {err}',
 '执行参考 q_ref (rad)': 'q_ref (rad)',
 '执行速度 dq (rad/s)': 'dq (rad/s)',
 '实测力矩 tau (Nm)': 'tau (Nm)',
 '开始记录': 'Start recording',
 '停止/清空': 'Stop/Clear',
 '读回并预览': 'Read back and preview',
 '采集全程（等录满后读回）': 'Capture entire session (read back after buffer fills)',
 '`log.capture(n)`：开始记录 → 等录满 n 拍 → 读回 → 解析。\nn 拍要 n/300 秒才录满，故会阻塞 SDK 所有者线程（界面不卡）。': '`log.capture(n)`: '
                                                                                      'start recording → '
                                                                                      'wait for n ticks to '
                                                                                      'fill → read back → '
                                                                                      'parse.\n'
                                                                                      'Capturing n ticks '
                                                                                      'takes n/300 seconds '
                                                                                      'to fill, so it blocks '
                                                                                      'the SDK owner thread '
                                                                                      '(the UI stays '
                                                                                      'responsive).',
 '查进度': 'Check progress',
 '导出原始字节…': 'Export raw bytes…',
 '导出解析 CSV…': 'Export parsed CSV…',
 '把最近一次读回的样本写成 CSV：tick、时间、q_ref/dq/tau。\n采集缓冲里没有温度与错误码 —— 那些请到总览页导出曲线 CSV。': 'Write the most recently '
                                                                              'read-back samples to CSV: '
                                                                              'tick, time, q_ref/dq/tau.\n'
                                                                              'The capture buffer has no '
                                                                              'temperature or error codes — '
                                                                              'export the plot CSV from the '
                                                                              'Overview page for those.',
 '录制': 'Recording',
 '时间 (s)': 'Time (s)',
 '预览（读回后绘制）': 'Preview (plotted after read-back)',
 '固件缓冲上限 {n} 拍（≈{secs:.1f}s @ {hz}Hz），记满自停。可导出原始字节，也可把最近一次读回的样本写成解析 CSV。': 'Firmware buffer holds up to {n} '
                                                                           'ticks (≈{secs:.1f}s @ {hz}Hz) '
                                                                           'and stops when full. You can '
                                                                           'export raw bytes, or write the '
                                                                           'most recently read-back samples '
                                                                           'to a parsed CSV.',
 '⚠ 固件是逐拍记录的：点开始后缓冲里还没有数据，要等 n/300 秒才录满。读回在未录满时也能拿到已录部分。': '⚠ Firmware records tick by tick: after you click '
                                                           'Start the buffer has no data yet and takes n/300 '
                                                           'seconds to fill. Reading back before it fills '
                                                           'still returns the captured portion.',
 '采集缓冲只有 tick/q_ref/dq/tau —— 温度与错误码在 100Hz 状态流里，请到「总览」页用曲线右上角的 [导出 CSV…]。': 'The capture buffer only holds '
                                                                             'tick/q_ref/dq/tau — '
                                                                             'temperature and error codes '
                                                                             'are in the 100Hz status '
                                                                             'stream; use [Export CSV…] at '
                                                                             'the top-right of the plot on '
                                                                             'the "Overview" page.',
 '读回 {n} 拍': 'Read back {n} ticks',
 '导出采集原始字节': 'Export capture raw bytes',
 '二进制 (*.bin);;全部 (*)': 'Binary (*.bin);;All (*)',
 '导出采集解析 CSV': 'Export capture parsed CSV',
 'CSV (*.csv);;全部 (*)': 'CSV (*.csv);;All (*)',
 '已导出 {n} 行 → {path}': 'Exported {n} rows → {path}',
 '拍数': 'Ticks',
 '预计': 'Estimated',
 '进度': 'Progress',
 '已开始记录 {n} 拍 …': 'Started recording {n} ticks …',
 '已停止/清空': 'Stopped/Cleared',
 '读回失败：{err}': 'Read-back failed: {err}',
 '还没有可导出的样本 —— 先读回并预览': 'No samples to export yet — read back and preview first',
 '导出失败：{err}': 'Export failed: {err}',
 '已记录 {n} 拍': 'Recorded {n} ticks',
 '查进度失败：{err}': 'Check progress failed: {err}',
 '已导出 {n} 字节 → {path}': 'Exported {n} bytes → {path}',
 '读取当前末端位姿 (GET_TCP)': 'Read current end-effector pose (GET_TCP)',
 '填入下方目标位姿': 'Fill in the target pose below',
 '当前末端位姿 pos[3] + rpy[3]': 'Current end-effector pose pos[3] + rpy[3]',
 '停止点动（受控停止）': 'Stop jog (controlled stop)',
 '写一条 movej 到**当前实测关节角**，作废在途点动/直线规划。\n走旁路，不排在在途命令后面。': 'Write a movej to the **current measured joint '
                                                        'angles**, cancelling any in-flight jog/linear '
                                                        'plan.\n'
                                                        'Takes a bypass path and is not queued behind '
                                                        'in-flight commands.',
 '点动（按住连续趋近，松手受控停止）': 'Jog (hold to move continuously, release for controlled stop)',
 '下发 movep': 'Send movep',
 '关节空间插值到目标位姿；不是直线，不需要笛卡尔规划。': 'Joint-space interpolation to the target pose; not a straight line and needs '
                               'no Cartesian planning.',
 '下发 movel（直线）': 'Send movel (straight line)',
 '固件笛卡尔直线：末端沿起点→目标直线运动，姿态 slerp。\n到位判据 6mm / 0.03rad；需要固件支持 LITEARM_CART_PLAN。': 'Firmware Cartesian '
                                                                                 'straight line: the end '
                                                                                 'effector moves in a '
                                                                                 'straight line from start '
                                                                                 'to target, orientation '
                                                                                 'slerped.\n'
                                                                                 'Arrival tolerance 6mm / '
                                                                                 '0.03rad; requires firmware '
                                                                                 'support for '
                                                                                 'LITEARM_CART_PLAN.',
 '求解 IK（只算不动）': 'Solve IK (compute only, no motion)',
 '用当前实测关节角作 IK 种子': 'Use current measured joint angles as IK seed',
 '目标位姿（movel / movep 与 ik 共用这组数值）': 'Target pose (movel / movep and ik share these values)',
 '⚠ 运动按输入框里的位姿下发 —— 下发前请核对数值。': '⚠ Motion is sent using the pose in the input fields — verify the values '
                                'before sending.',
 '⚠ 点动与 movel 需要固件编入笛卡尔规划；固件不支持时按钮保持灰色。每一段都从实测 TCP 重新起步，段间会停一下。': '⚠ Jog and movel require Cartesian '
                                                                  'planning compiled into the firmware; the '
                                                                  'buttons stay grayed out if unsupported. '
                                                                  'Each segment restarts from the measured '
                                                                  'TCP, so there is a brief pause between '
                                                                  'segments.',
 'move_p：固件后台 IK → S 曲线 → 按 TCP 到位判定。move_l：固件笛卡尔直线规划（需 LITEARM_CART_PLAN）。ik：只求解不动臂；种子恒为**模型 7 轴**（与关节数解耦）。': 'move_p: '
                                                                                                               'firmware '
                                                                                                               'background '
                                                                                                               'IK '
                                                                                                               '→ '
                                                                                                               'S-curve '
                                                                                                               '→ '
                                                                                                               'TCP-based '
                                                                                                               'arrival '
                                                                                                               'check. '
                                                                                                               'move_l: '
                                                                                                               'firmware '
                                                                                                               'Cartesian '
                                                                                                               'straight-line '
                                                                                                               'planning '
                                                                                                               '(requires '
                                                                                                               'LITEARM_CART_PLAN). '
                                                                                                               'ik: '
                                                                                                               'solve '
                                                                                                               'only '
                                                                                                               'without '
                                                                                                               'moving '
                                                                                                               'the '
                                                                                                               'arm; '
                                                                                                               'the '
                                                                                                               'seed '
                                                                                                               'is '
                                                                                                               'always '
                                                                                                               'the '
                                                                                                               "**model's "
                                                                                                               '7 '
                                                                                                               'axes** '
                                                                                                               '(decoupled '
                                                                                                               'from '
                                                                                                               'joint '
                                                                                                               'count).',
 '点动 {button} …': 'Jog {button} …',
 '受控停止…': 'Controlled stop…',
 '失败：{msg}': 'Failed: {msg}',
 '基座系': 'Base',
 '工具系': 'Tool',
 '坐标系': 'Coordinate frame',
 '平移步长': 'Translation step',
 '旋转步长': 'Rotation step',
 '速度倍率 (0..1)': 'Speed scale (0..1)',
 '已离线': 'Offline',
 '运动已锁定': 'Motion locked',
 'FAULT/急停锁存': 'FAULT/emergency stop latched',
 '笛卡尔能力探测未获确认（上行无应答）—— 点动/movel 已禁用；请重连或检查链路': 'Cartesian capability probe unconfirmed (no response on '
                                               'uplink) — jog/movel are disabled; please reconnect or check '
                                               'the link',
 '点动不可用：未连接/未解锁/固件不支持': 'Jog unavailable: not connected / motion not unlocked / firmware unsupported',
 '忙：等当前命令结束再点动': 'Busy: wait for the current command to finish before jogging',
 '点动未下发（运动未解锁/未连接）': 'Jog not sent (motion not unlocked / not connected)',
 '已停止': 'Stopped',
 '固件未编入笛卡尔规划（LITEARM_CART_PLAN）—— 点动/movel 不可用': 'Firmware does not include Cartesian planning '
                                                 '(LITEARM_CART_PLAN) — jog/movel unavailable',
 '未连接 —— 点动/movel 需要先连接设备': 'Not connected — jog/movel require a device connection first',
 '点动失败：{err}': 'Jog failed: {err}',
 '完成': 'Done',
 '运动已锁定 — 请勾选顶栏的「我已确认机械臂周围无障碍、急停可及」': 'Motion locked — tick “I have confirmed there are no obstacles around '
                                      'the robot arm and the emergency stop is within reach” in the top bar',
 '未连接 — 连接后才可操作': 'Not connected — connect before operating',
 'FAULT / 急停锁存中 — 先 [清故障] 或 [复位]': 'FAULT / emergency stop latched — use [Clear Fault] or [Reset] first',
 '运行 KIN_BENCH 自检': 'Run KIN_BENCH self-test',
 '触发固件运动学/动力学单拍开销自测（固件侧最长窗口 5s，期间控制循环\n心跳监督豁免）。注意：该命令不检查载荷长度，发出即产生一次真实测量。': 'Trigger a firmware self-test of '
                                                                            'the per-cycle '
                                                                            'kinematics/dynamics cost '
                                                                            '(firmware-side window up to 5s; '
                                                                            'control-loop\n'
                                                                            'heartbeat supervision is waived '
                                                                            'during it). Note: this command '
                                                                            'does not check payload length, '
                                                                            'sending it takes a real '
                                                                            'measurement.',
 '链路与运行计数': 'Link and runtime counters',
 'KIN_BENCH 原文（含逐项计时与 LINK 诊断行）会显示在这里': 'The raw KIN_BENCH output (including per-item timings and the LINK '
                                        'diagnostics line) will appear here',
 'KIN_BENCH 回执原文': 'Raw KIN_BENCH response',
 'CRC/队满/CAN 失败来自固件侧计数器（KIN_BENCH 回执里的 LINK 行）；丢帧是上位机按 seq 差分算的接收侧数字。': 'CRC/FIFO-full/CAN failures come '
                                                                        'from firmware-side counters (the '
                                                                        'LINK line in the KIN_BENCH '
                                                                        'response); dropped frames are '
                                                                        'host-side receive figures computed '
                                                                        'from seq differences.',
 '固件累计 CRC 坏帧': 'Firmware cumulative CRC bad frames',
 '应答 FIFO 队满丢弃': 'Response FIFO full drops',
 'CAN 发送失败': 'CAN transmit failures',
 '控制拍峰值 (kcycle)': 'Control cycle peak (kcycle)',
 '控制拍超预算次数': 'Control cycles over budget',
 '上位机接收侧丢帧': 'Host-side dropped frames',
 '状态帧率 (Hz)': 'Status frame rate (Hz)',
 '固件版本': 'Firmware version',
 '关节数': 'Joint count',
 '上次启动原因': 'Last boot reason',
 '当前故障原因': 'Current fault reason',
 '无': 'None',
 '当前状态': 'Current status',
 '逐轴故障': 'Per-axis faults',
 '本次会话内新出现的故障会按时间记录在这里': 'Faults that newly appear in this session are logged here in time order',
 '事件历史': 'Event history',
 '复制诊断包': 'Copy diagnostics bundle',
 '无故障': 'No faults',
 '故障锁存后运动页面会被禁用；必须清故障或复位才能恢复出力。': 'After a fault latches, motion pages are disabled; you must clear the '
                                  'fault or reset to restore output.',
 '轴': 'Axis',
 '原因': 'Cause',
 '处置': 'Action',
 '模式 {mode} · {enabled} · 整臂持位：{hold}': 'Mode {mode} · {enabled} · Whole-arm hold: {hold}',
 '故障锁存：{axes}': 'Fault latched: {axes}',
 '断轴': 'Joint lost',
 '正常': 'Normal',
 '已使能': 'Enabled',
 '未使能': 'Not enabled',
 '原因不可知（旧固件）': 'Cause unknown (older firmware)',
 '校验镜像': 'Verify image',
 '失能机械臂': 'Disable robot arm',
 '进入 bootloader': 'Enter bootloader',
 '等待 DFU 设备': 'Wait for DFU device',
 '擦写并读回校验': 'Erase, write, and read-back verify',
 '复位回应用': 'Resetting back to application',
 '重新连接控制器': 'Reconnect controller',
 '读不出这份镜像：它既不是合法的 Intel HEX，也不是 .bin。请向供应商索取官方的 .hex': 'Cannot read this image: it is neither valid Intel '
                                                       'HEX nor .bin. Ask the vendor for the official .hex',
 '镜像的起始地址不是 0x08000000：应用只能烧到那里。请确认选的是固件而不是别的固件段': 'The image does not start at 0x08000000: the application '
                                                   'can only be flashed there. Make sure you selected the '
                                                   'firmware, not another firmware section',
 '镜像超出控制器 1 MB 的 Flash：请确认选对了文件': "The image exceeds the controller's 1 MB flash: check that you selected "
                                  'the right file',
 '镜像覆盖了许可证与出厂标定所在的扇区（擦掉不可恢复）：这份镜像不能用，请向供应商索取正确的固件': 'The image covers the sectors holding the license and '
                                                    'factory calibration (erasing them is irreversible): '
                                                    'this image cannot be used, ask the vendor for the '
                                                    'correct firmware',
 '机械臂没有失能，已中止：带着使能进 bootloader 会让电机松开、臂下垂': 'The robot arm is not disabled; aborted: entering the bootloader '
                                            'while enabled lets the motors go slack and the arm droop',
 '控制器没有接受进入 bootloader 的请求（登记被撤销或未执行）：机械臂原样可用，确认已失能后重试': 'The controller did not accept the request to enter '
                                                         'the bootloader (it was withdrawn or not executed): '
                                                         'the robot arm is usable as-is; confirm it is '
                                                         'disabled and retry',
 '进入 bootloader 后没有找到 DFU 设备（0483:DF11）：请检查 USB 线；Windows 上需要 ST 的 WinUSB 驱动': 'No DFU device (0483:DF11) '
                                                                               'found after entering the '
                                                                               'bootloader: check the USB '
                                                                               'cable; on Windows you need '
                                                                               "ST's WinUSB driver",
 '打不开 DFU 设备（权限不足）：板子已经在 bootloader 里，但当前用户没有权限访问它。Linux 上需要一条 udev 规则：SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="df11", MODE="0666"': 'Cannot '
                                                                                                                                                        'open '
                                                                                                                                                        'the '
                                                                                                                                                        'DFU '
                                                                                                                                                        'device '
                                                                                                                                                        '(permission '
                                                                                                                                                        'denied): '
                                                                                                                                                        'the '
                                                                                                                                                        'board '
                                                                                                                                                        'is '
                                                                                                                                                        'already '
                                                                                                                                                        'in '
                                                                                                                                                        'the '
                                                                                                                                                        'bootloader, '
                                                                                                                                                        'but '
                                                                                                                                                        'the '
                                                                                                                                                        'current '
                                                                                                                                                        'user '
                                                                                                                                                        'cannot '
                                                                                                                                                        'access '
                                                                                                                                                        'it. '
                                                                                                                                                        'On '
                                                                                                                                                        'Linux '
                                                                                                                                                        'you '
                                                                                                                                                        'need '
                                                                                                                                                        'a '
                                                                                                                                                        'udev '
                                                                                                                                                        'rule: '
                                                                                                                                                        'SUBSYSTEM=="usb", '
                                                                                                                                                        'ATTR{idVendor}=="0483", '
                                                                                                                                                        'ATTR{idProduct}=="df11", '
                                                                                                                                                        'MODE="0666"',
 '这台机器上没有可用的 USB 烧录引擎': 'No usable USB flashing engine on this machine',
 '烧录失败': 'Flash failed',
 '固件已经写入并通过读回校验，但没能重新连上控制器': 'The firmware was written and passed read-back verification, but the controller '
                             'could not be reconnected',
 '升级已取消（若已进入烧录相位，取消不再生效）': 'Upgrade cancelled (cancellation no longer takes effect once the flashing phase '
                           'has started)',
 '机械臂未连接：请先在顶栏连接设备': 'Robot arm not connected: connect the device in the top bar first',
 '这台机器上没有可用的 USB 烧录引擎：{detail}（需要 pyusb 与 libusb；Windows 上还要装 ST 的 WinUSB 驱动）': 'No usable USB flashing '
                                                                                'engine on this machine: '
                                                                                '{detail} (requires pyusb '
                                                                                'and libusb; on Windows you '
                                                                                "also need ST's WinUSB "
                                                                                'driver)',
 '升级失败': 'Upgrade failed',
 '固件升级（USB DFU）': 'Firmware upgrade (USB DFU)',
 '选择固件文件': 'Select firmware file',
 '镜像文件': 'Image file',
 '镜像摘要': 'Image summary',
 '我确定机械臂在安全状态下，且升级期间不再控制它': 'I confirm the robot arm is in a safe state and I will not control it during the '
                            'upgrade',
 '开始之前必须确认': 'Required before starting',
 '开始升级': 'Start upgrade',
 '取消升级': 'Cancel upgrade',
 '重置': 'Reset',
 '升级进度': 'Upgrade progress',
 '结果': 'Result',
 '选择固件镜像': 'Select firmware image',
 '固件镜像 (*.hex *.bin);;所有文件 (*)': 'Firmware image (*.hex *.bin);;All files (*)',
 '未找到 libusb 后端': 'libusb backend not found',
 '设备已被尽量擦回空白，可以直接重试；若反复失败需要 SWD 探针救机': 'The device has been erased back to blank as far as possible; you can '
                                       'retry directly. If it keeps failing, an SWD probe is needed to '
                                       'recover it',
 '请重试': 'Retry',
 '烧录失败：{message}。{tail}': 'Flash failed: {message}. {tail}',
 '界面没有响应重连请求': 'The interface did not respond to the reconnect request',
 '没有重连结果': 'No reconnect result',
 '版本': 'Version',
 '大小': 'Size',
 '地址范围': 'Address range',
 '格式': 'Format',
 '空洞': 'Gaps',
 '[INFO] 镜像已校验: {name} · {size} B · 版本 {version} · sha256 {sha}': '[INFO] Image verified: {name} · {size} B '
                                                                  '· version {version} · sha256 {sha}',
 '{n} 段（按 0xFF 填充）': '{n} segments (padded with 0xFF)',
 '这次不会再失能一次 —— 应用早已停下，电机保持松开；烧录完成后板子会复位回应用态': 'The arm will not be disabled again — the application has '
                                              'already stopped and the motors stay released; after flashing '
                                              'the board resets back to the application',
 '升级会先让机械臂失能 —— 中途电机会松开，有重力负载就会下垂': 'The upgrade first disables the robot arm — the motors release partway '
                                    'through, so the arm droops under gravity load',
 '• {disarm}\n• 升级期间无法急停 —— 设备在 bootloader 里，应用已停摆\n• 许可证与出厂标定所在的扇区不会被触碰；镜像若覆盖该区会被直接拒绝': '• {disarm}\n'
                                                                                         '• No emergency '
                                                                                         'stop during the '
                                                                                         'upgrade — the '
                                                                                         'device is in the '
                                                                                         'bootloader and the '
                                                                                         'application is '
                                                                                         'stopped\n'
                                                                                         '• The sectors '
                                                                                         'holding the '
                                                                                         'license and '
                                                                                         'factory '
                                                                                         'calibration are '
                                                                                         'never touched; an '
                                                                                         'image that covers '
                                                                                         'them is rejected '
                                                                                         'outright',
 '升级进行中': 'Upgrade in progress',
 '内部错误：SDK 未接入': 'Internal error: SDK not attached',
 '烧录引擎不可用 —— 需要 pyusb 与 libusb；Windows 上还要装 ST 的 WinUSB 驱动': 'Flashing engine unavailable — requires pyusb '
                                                             "and libusb; on Windows you also need ST's "
                                                             'WinUSB driver',
 '请先选择并校验一份固件镜像': 'Select and verify a firmware image first',
 '请先连接控制器；若板子停在 bootloader 里，等它被检测到后可直接烧录': 'Connect the controller first; if the board is in the '
                                            'bootloader, you can flash directly once it is detected',
 '请先确认机械臂处于安全状态': 'Confirm the robot arm is in a safe state first',
 '准备…': 'Preparing…',
 '[INFO] 固件升级开始: {name} ({size} B) · {route}': '[INFO] Firmware upgrade started: {name} ({size} B) · {route}',
 '升级进行中 · {phase}': 'Upgrade in progress · {phase}',
 '升级完成，设备已回到应用态并通过读回校验。': 'Upgrade complete; the device is back in the application and passed read-back '
                          'verification.',
 '板子停在 bootloader 里：应用没有在跑，机械臂此刻没有力矩。\n\n升级期间无法控制机械臂，也无法软件急停。烧录完成后会自动复位回应用态。\n\n继续吗？': 'The board is in the '
                                                                                       'bootloader: the '
                                                                                       'application is not '
                                                                                       'running and the '
                                                                                       'robot arm has no '
                                                                                       'torque right now.\n'
                                                                                       '\n'
                                                                                       'During the upgrade '
                                                                                       'you cannot control '
                                                                                       'the robot arm or '
                                                                                       'trigger a software '
                                                                                       'emergency stop. '
                                                                                       'After flashing it '
                                                                                       'resets back to the '
                                                                                       'application '
                                                                                       'automatically.\n'
                                                                                       '\n'
                                                                                       'Continue?',
 '升级会先让机械臂失能 —— 电机会松开，有重力负载的机械臂会下垂。\n\n升级期间无法控制机械臂，也无法软件急停。请确认手臂已放稳或有支撑。\n\n继续吗？': 'The upgrade first '
                                                                                   'disables the robot arm — '
                                                                                   'the motors release and '
                                                                                   'an arm under gravity '
                                                                                   'load will droop.\n'
                                                                                   '\n'
                                                                                   'During the upgrade you '
                                                                                   'cannot control the robot '
                                                                                   'arm or trigger a '
                                                                                   'software emergency stop. '
                                                                                   'Make sure the arm is '
                                                                                   'resting securely or is '
                                                                                   'supported.\n'
                                                                                   '\n'
                                                                                   'Continue?',
 '未识别（{note}）': 'Unrecognized ({note})',
 '引擎状态读取失败': 'Failed to read engine status',
 '升级中': 'Upgrading',
 '烧录引擎：检查中…': 'Flashing engine: checking…',
 '升级进行中 —— 控制器在 bootloader 里，升级结束前界面连不上它，这是正常的。': 'Upgrade in progress — the controller is in the '
                                                  'bootloader; the interface cannot connect to it until the '
                                                  'upgrade finishes, which is normal.',
 '检测到控制器停在 bootloader（DFU）里：它不在应用态，所以顶栏连不上它 —— 这不是没插线。点下面的「烧录并复位回应用」把它写回来。': 'The controller is detected in '
                                                                             'the bootloader (DFU): it is '
                                                                             'not in the application, so the '
                                                                             'top bar cannot connect to it — '
                                                                             'this does not mean the cable '
                                                                             'is unplugged. Click “Flash and '
                                                                             'reset to application” below to '
                                                                             'write it back.',
 '烧录并复位回应用': 'Flash and reset to application',
 '请先连接控制器，或把板子置于 DFU 状态。': 'Connect the controller first, or put the board into DFU mode.',
 '请先勾选安全确认。': 'Tick the safety confirmation first.',
 '正在取消…': 'Cancelling…',
 '[WARN] 已请求取消升级（烧录相位内不生效）': '[WARN] Upgrade cancellation requested (no effect during the flashing phase)',
 '[OK] 固件升级完成 · 设备版本 {version}': '[OK] Firmware upgrade complete · device version {version}',
 '[ERR] 固件升级失败({reason}): {message}': '[ERR] Firmware upgrade failed ({reason}): {message}',
 ' 设备现在报告的版本：{version}': ' Version reported by the device now: {version}',
 '升级失败：{detail}': 'Upgrade failed: {detail}',
 '开始固件升级': 'Start firmware upgrade',
 '读不出文件: {err}': 'Cannot read file: {err}',
 '文件 {size} B 超过 {limit} B 上限': 'File {size} B exceeds the {limit} B limit',
 '烧录引擎可用：{label}': 'Flashing engine available: {label}',
 '烧录引擎不可用：{label}（需要 pyusb 与 libusb；Windows 上还要装 ST 的 WinUSB 驱动）': 'Flashing engine unavailable: {label} '
                                                                   '(requires pyusb and libusb; on Windows '
                                                                   "you also need ST's WinUSB driver)",
 '\n找到的控制器位于 USB {loc}，请确认这就是你要烧录的控制器。': '\n'
                                         'The controller found is on USB {loc}; confirm this is the '
                                         'controller you want to flash.',
 '未识别': 'Unidentified',
 '[WARN] 枚举 USB 设备失败: {detail}': '[WARN] USB device enumeration failed: {detail}',
 '当前固件：{fw} · 端口：{port}': 'Current firmware: {fw} · Port: {port}',
 '未连接控制器 —— 连上之后才能升级。若板子停在 DFU 里，这里会单独提示。': 'Controller not connected — connect it before upgrading. If the '
                                            'board is in DFU, a separate notice appears here.',
 '从 bootloader 起跑': 'Starting from bootloader',
 '从应用态起跑': 'Starting from application',
 '校验': 'Verify',
 '擦除': 'Erase',
 '内核枚举到的 CAN 接口；也可以手动输入未列出的名字': 'CAN interfaces enumerated by the kernel; you can also type a name that is '
                                'not listed',
 '重新枚举 /sys/class/net 里的 CAN 接口': 'Re-enumerate CAN interfaces in /sys/class/net',
 '0 = 自动探测；非 0 时作为状态帧的 master ID': '0 = auto-detect; non-zero sets the master ID for status frames',
 '可选：标定 JSON（留空则用上面的模板/出厂标定）': 'Optional: calibration JSON (leave blank to use the template above / factory '
                               'calibration)',
 '浏览…': 'Browse…',
 '连接与身份（更改通道 / CAN ID / MST ID 后需断开重连）': 'Connection and identity (disconnect and reconnect after changing '
                                         'channel / CAN ID / MST ID)',
 '使能': 'Enable',
 '张开': 'Open',
 '闭合': 'Close',
 '抓取': 'Grasp',
 '停止 / 释放': 'Stop / Release',
 '旁路发零力矩帧；若有动作在途，再失能电机以中止它（否则保力循环下一帧\n就会把力矩写回来），并丢弃排队中的动作。不代替机械臂急停。': 'Send a zero-torque frame on the '
                                                                      'bypass; if a motion is underway, also '
                                                                      'disable the motor to abort it '
                                                                      '(otherwise the force-hold loop will\n'
                                                                      'write the torque back on the next '
                                                                      'frame), and discard queued motions. '
                                                                      "Does not replace the robot arm's "
                                                                      'emergency stop.',
 '刷新状态': 'Refresh Status',
 '动作': 'Action',
 '遥测（10Hz 轮询）': 'Telemetry (10 Hz polling)',
 '读取标定': 'Read calibration',
 '加载标定…': 'Load Calibration…',
 '保存标定…': 'Save Calibration…',
 '写零（不可逆）': 'Write Zero (irreversible)',
 '把当前编码器角写为电机零位，写入电机 Flash。不可逆。': 'Write the current encoder angle as the motor zero position to motor '
                                  'flash. Irreversible.',
 '标定': 'Calibration',
 '⚠ 夹爪与机械臂共用现场空间：抓取前确认手指路径上没有人。「停止 / 释放」会发零力矩帧并中止在途动作，但不是机械臂急停。': '⚠ The gripper shares workspace with the '
                                                                  'robot arm: make sure no one is in the '
                                                                  'finger path before grasping. "Stop / '
                                                                  'Release" sends a zero-torque frame and '
                                                                  'aborts in-flight motion, but it is not '
                                                                  "the robot arm's emergency stop.",
 '标定决定行程与开合方向；未标定时 SDK 拒绝一切运动。写零会改写电机 Flash，臂/手指需支撑好。': 'Calibration determines travel and open/close '
                                                        'direction; the SDK rejects all motion when '
                                                        'uncalibrated. Writing zero rewrites motor flash, so '
                                                        'the arm/fingers must be supported.',
 '选择标定文件': 'Select Calibration File',
 'JSON (*.json);;全部 (*)': 'JSON (*.json);;All (*)',
 '加载标定文件': 'Load Calibration File',
 '保存标定文件': 'Save Calibration File',
 '通道 {channel} · CAN 0x{can_id:02X} · MST {mst} · 方向 {mount} · 行程 {travel:.1f} mm · {state}': 'Channel '
                                                                                              '{channel} · '
                                                                                              'CAN '
                                                                                              '0x{can_id:02X} '
                                                                                              '· MST {mst} · '
                                                                                              'Direction '
                                                                                              '{mount} · '
                                                                                              'Travel '
                                                                                              '{travel:.1f} '
                                                                                              'mm · {state}',
 '出厂（正装）': 'Factory',
 '正装模板': 'Standard',
 '反装模板': 'Reverse',
 '通道': 'Channel',
 '安装': 'Mount',
 '标定文件': 'Calibration File',
 '抓取力 (N)': 'Grip Force (N)',
 '保持 (s)': 'Hold (s)',
 '位置 (mm)': 'Position (mm)',
 '夹持力 (N)': 'Clamping Force (N)',
 '力矩 (Nm)': 'Torque (Nm)',
 '温度 mos/coil (°C)': 'Temperature mos/coil (°C)',
 '错误码': 'Error Code',
 '新鲜度': 'Freshness',
 '[WARN] 夹爪未连接': '[WARN] Gripper not connected',
 '确认写零': 'Confirm Write Zero',
 '写零会把当前编码器角写为电机零位并写入电机 Flash，不可逆。\n标定行程保持不变。确认继续？': 'Writing zero sets the current encoder angle as the '
                                                     'motor zero position and writes it to motor flash. '
                                                     'Irreversible.\n'
                                                     'Calibration travel stays unchanged. Continue?',
 '● 已连接': '● Connected',
 '● 未连接': '● Not connected',
 '● 不可用 — {why}': '● Unavailable — {why}',
 '失能': 'Disable',
 '[ERR] 夹爪连接失败: {err}': '[ERR] Gripper connection failed: {err}',
 '夹爪连接失败': 'Gripper Connection Failed',
 '[WARN] 夹爪停止: ': '[WARN] Gripper stop: ',
 '[ERR] 夹爪停止未完整生效: ': '[ERR] Gripper stop did not fully take effect: ',
 '未标定': 'Uncalibrated',
 '已标定': 'Calibrated',
 '新帧': 'New frame',
 '缓存': 'Cached',
 '关节控制 / 软限位 (kp,kd,tau_max,q_min,q_max)': 'Joint control / soft limits (kp,kd,tau_max,q_min,q_max)',
 '摩擦 v1 / 积分 / 限位墙': 'Friction v1 / integral / limit walls',
 '动力学缩放 (gs / is)': 'Dynamics scaling (gs / is)',
 '摩擦 v2 (friction_model=1 时生效)': 'Friction v2 (active when friction_model=1)',
 '0x26 item {item} (7 关节整组)': '0x26 item {item} (all 7 joints as a group)',
 "<h3>参数逐项详解</h3><span style='color:#666;'>内容与参数页悬停提示同源 (param_catalog role/hint/detail); 点分组标题收起/展开。</span>": '<h3>Parameter-by-Parameter '
                                                                                                               'Details</h3><span '
                                                                                                               "style='color:#666;'>Content "
                                                                                                               'is '
                                                                                                               'the '
                                                                                                               'same '
                                                                                                               'as '
                                                                                                               'the '
                                                                                                               'parameter '
                                                                                                               'page '
                                                                                                               'hover '
                                                                                                               'hints '
                                                                                                               '(param_catalog '
                                                                                                               'role/hint/detail); '
                                                                                                               'click '
                                                                                                               'a '
                                                                                                               'group '
                                                                                                               'heading '
                                                                                                               'to '
                                                                                                               'collapse/expand.</span>',
 '全局标量 (fric_db/wall_margin/friction_slew/payload_mass/payload_com/gravity/friction_model/fric_v2_eps)': 'Global '
                                                                                                         'scalars',
 'ff_mask 使能位': 'ff_mask enable bits',
 '范围 {range} · 写口 {write}': 'Range {range} · write port {write}',
 '0x22 (kp/kd/tau_max 成组)': '0x22 (kp/kd/tau_max as a group)',
 '0x23 (q_min/q_max 成组)': '0x23 (q_min/q_max as a group)',
 '范围 {range}': 'Range {range}',
 'ff_mask 位 bit{bit} = 0x{mask:02X}': 'ff_mask flag bit{bit} = 0x{mask:02X}',
 '{name} 位': '{name} bit',
 '(自定义)': '(Custom)',
 '正装': 'Upright',
 '倒装': 'Inverted',
 '侧装 +x': 'Side-mount +x',
 '侧装 -x': 'Side-mount -x',
 '侧装 +y': 'Side-mount +y',
 '侧装 -y': 'Side-mount -y',
 '未连接 — 连接后可用': 'Not connected — available after connecting',
 '自定义': 'Custom',
 '不选预设，直接用下面的 base_rpy 或 gravity 向量': "Don't pick a preset; use the base_rpy or gravity vector below "
                                      'directly',
 '① 选择安装方向': '① Select Mounting Orientation',
 '读当前': 'Read Current',
 '读 0x2C item6 三轴 —— 这是本页所有下发的前置（未读不许写）': 'Read the three axes of 0x2C item6 — this is a prerequisite for '
                                          'every write on this page (no write without a read)',
 '下发（须失能）': 'Apply (requires disable)',
 '写 0x28 item6 sub0/1/2。须先失能：改 gravity 会让重力前馈当拍阶跃，\n且三条非原子（中途经过模长 13.87 的中间态）。本页不会替你失能。': 'Writes 0x28 item6 '
                                                                                          'sub0/1/2. Disable '
                                                                                          'first: changing '
                                                                                          'gravity makes the '
                                                                                          'gravity '
                                                                                          'feedforward step '
                                                                                          'in one sample,\n'
                                                                                          'and the three '
                                                                                          'writes are not '
                                                                                          'atomic (passing '
                                                                                          'through an '
                                                                                          'intermediate '
                                                                                          'state with '
                                                                                          'magnitude 13.87). '
                                                                                          'This page will '
                                                                                          'not disable the '
                                                                                          'arm for you.',
 '固化到 Flash': 'Persist to Flash',
 '写 0x25 保存当前 RAM 参数到 flash（同样须失能）': 'Write 0x25 to save the current RAM parameters to flash (also requires '
                                     'disable)',
 '③ 读 / 下发 / 固化': '③ Read / Apply / Persist',
 '已拒绝 — 请先 [读当前]': 'Rejected — please [Read Current] first',
 '已拒绝 — 须先失能': 'Rejected — disable required first',
 '执行中：{what} …': 'Running: {what} …',
 '已读取设备当前装向（{name}）': "Read the device's current mounting orientation ({name})",
 '读回差异 {dmax:.2e} {ok_rb}；|g|={mag:.4f} {ok_mag}；{gq}': 'Read-back diff {dmax:.2e} {ok_rb}; |g|={mag:.4f} '
                                                        '{ok_mag}; {gq}',
 '写入 gravity = ({x:+.2f}, {y:+.2f}, {z:+.2f}) m/s²': 'Writing gravity = ({x:+.2f}, {y:+.2f}, {z:+.2f}) m/s²',
 '按钮上写的就是将下发的 base 系重力向量 —— 别去猜「侧装 +y」是哪一边。不确定就用 base_rpy 推导，或在 pylitearm 侧 set_installation/get_installation 取同一组值。': 'The '
                                                                                                                       'button '
                                                                                                                       'label '
                                                                                                                       'is '
                                                                                                                       'exactly '
                                                                                                                       'the '
                                                                                                                       'base-frame '
                                                                                                                       'gravity '
                                                                                                                       'vector '
                                                                                                                       'that '
                                                                                                                       'will '
                                                                                                                       'be '
                                                                                                                       'sent '
                                                                                                                       '— '
                                                                                                                       "don't "
                                                                                                                       'guess '
                                                                                                                       'which '
                                                                                                                       'side '
                                                                                                                       '"Side-mount '
                                                                                                                       '+y" '
                                                                                                                       'is. '
                                                                                                                       'If '
                                                                                                                       'unsure, '
                                                                                                                       'derive '
                                                                                                                       'it '
                                                                                                                       'from '
                                                                                                                       'base_rpy, '
                                                                                                                       'or '
                                                                                                                       'read '
                                                                                                                       'the '
                                                                                                                       'same '
                                                                                                                       'values '
                                                                                                                       'via '
                                                                                                                       'set_installation/get_installation '
                                                                                                                       'on '
                                                                                                                       'the '
                                                                                                                       'pylitearm '
                                                                                                                       'side.',
 '② 安装姿态与向量（': '② Mounting orientation and vector (',
 '设备当前：—': 'Device current: —',
 '设备当前：({x:+.4f}, {y:+.4f}, {z:+.4f}) = {name}   |g|={mag:.4f}': 'Device current: ({x:+.4f}, {y:+.4f}, '
                                                                 '{z:+.4f}) = {name}   |g|={mag:.4f}',
 '已连接 — 尚未读取设备当前装向，请先 [读当前]；在此之前禁下发': 'Connected — device mounting orientation not read yet; please [Read '
                                      'Current] first; writes are blocked until then',
 '离线，忽略操作': 'Offline, action ignored',
 '忙：前一条操作仍在执行，已忽略 {what}': 'Busy: previous operation still running; ignored {what}',
 '忙：运动/控制命令在途（MainWindow），已忽略本页操作': "Busy: motion/control command in flight (MainWindow); this page's action "
                                    'was ignored',
 '请先读取设备参数': 'Please read the device parameters first',
 '{what}\n\n尚未成功 [读当前]，此时下发等于把控件里的默认值盲写进设备。\n请先点 [读当前]。': '{what}\n'
                                                          '\n'
                                                          '[Read Current] has not succeeded yet; applying '
                                                          'now would blindly write the widget defaults into '
                                                          'the device.\n'
                                                          'Please click [Read Current] first.',
 '臂处于使能态': 'The arm is enabled',
 '状态未知（尚未收到状态帧）—— 状态没到手不等于安全': 'Status unknown (no status frame received yet) — not having status does not '
                               'mean safe',
 '须先失能': 'Disable required first',
 '{what}\n\n{reason}。\n\n改 gravity 会让重力前馈当拍阶跃（正装↔侧装 |Δg|=13.87 m/s²，J2/J3 上几十 Nm），且三条分量下发非原子（中途模长 13.87、方向偏 45°）。\n请先到 [整机] 页失能 —— 本页不会替你失能（那会让你失去保持力矩）。': '{what}\n'
                                                                                                                                                           '\n'
                                                                                                                                                           '{reason}.\n'
                                                                                                                                                           '\n'
                                                                                                                                                           'Changing '
                                                                                                                                                           'gravity '
                                                                                                                                                           'makes '
                                                                                                                                                           'the '
                                                                                                                                                           'gravity '
                                                                                                                                                           'feedforward '
                                                                                                                                                           'step '
                                                                                                                                                           'in '
                                                                                                                                                           'one '
                                                                                                                                                           'sample '
                                                                                                                                                           '(upright↔side-mount '
                                                                                                                                                           '|Δg|=13.87 '
                                                                                                                                                           'm/s², '
                                                                                                                                                           'tens '
                                                                                                                                                           'of '
                                                                                                                                                           'Nm '
                                                                                                                                                           'on '
                                                                                                                                                           'J2/J3), '
                                                                                                                                                           'and '
                                                                                                                                                           'the '
                                                                                                                                                           'three '
                                                                                                                                                           'component '
                                                                                                                                                           'writes '
                                                                                                                                                           'are '
                                                                                                                                                           'not '
                                                                                                                                                           'atomic '
                                                                                                                                                           '(intermediate '
                                                                                                                                                           'magnitude '
                                                                                                                                                           '13.87, '
                                                                                                                                                           'direction '
                                                                                                                                                           'off '
                                                                                                                                                           'by '
                                                                                                                                                           '45°).\n'
                                                                                                                                                           'Please '
                                                                                                                                                           'disable '
                                                                                                                                                           'on '
                                                                                                                                                           'the '
                                                                                                                                                           '[Whole '
                                                                                                                                                           'Arm] '
                                                                                                                                                           'page '
                                                                                                                                                           'first '
                                                                                                                                                           '— '
                                                                                                                                                           'this '
                                                                                                                                                           'page '
                                                                                                                                                           'will '
                                                                                                                                                           'not '
                                                                                                                                                           'disable '
                                                                                                                                                           'the '
                                                                                                                                                           'arm '
                                                                                                                                                           'for '
                                                                                                                                                           'you '
                                                                                                                                                           '(that '
                                                                                                                                                           'would '
                                                                                                                                                           'make '
                                                                                                                                                           'you '
                                                                                                                                                           'lose '
                                                                                                                                                           'holding '
                                                                                                                                                           'torque).',
 '安装方向[{what}]': 'Mounting orientation [{what}]',
 '未执行': 'Not executed',
 '失败：{err}': 'Failed: {err}',
 '读回失败 — 固件不支持 0x2C item6？（需 ≥1.5.x）': "Read-back failed — firmware doesn't support 0x2C item6? (requires "
                                       '≥1.5.x)',
 '已取消 — |g| 偏离未确认': 'Cancelled — |g| deviation not confirmed',
 '下发安装方向': 'Apply Mounting Orientation',
 '下发失败：{detail}': 'Apply failed: {detail}',
 '下发后回读失败 —— 不能确认已生效': 'Read-back after apply failed — cannot confirm it took effect',
 'G(q)：未取到当前姿态，跳过': 'G(q): current pose unavailable, skipped',
 '已固化到 Flash（掉电保持）': 'Persisted to flash (survives power-off)',
 '固化失败：固件拒绝（须失能；0x04=需先 disable）': 'Persist failed: firmware rejected (disable required; 0x04=must disable '
                                   'first)',
 ')，与固件 kin.c 同式。改 rpy 会自动重算向量；直接改向量则 rpy 标为「(自定义)」（反向不唯一，不做反解）。': '), same formula as firmware kin.c. '
                                                                   'Changing rpy automatically recomputes '
                                                                   'the vector; if you edit the vector '
                                                                   'directly, rpy is marked "(Custom)" (the '
                                                                   'inverse is not unique, so no reverse '
                                                                   'solve is done).',
 '离线 — 断开或 500ms 无状态帧；重连后自动恢复': 'Offline — disconnected or no status frame for 500 ms; recovers '
                                'automatically on reconnect',
 '⚠ 臂处于使能态 —— 下发需先到 [整机] 页失能（本页不会替你失能）': '⚠ The arm is enabled — to apply, first disable on the [Whole Arm] '
                                         'page (this page will not disable the arm for you)',
 '|g| 偏离 9.81': '|g| deviates from 9.81',
 '当前 |g| = {mag:.4f} m/s²，偏离 9.81 超过 {pct:.0%}。\n\n常见成因：只改了一个分量（例如正装→侧装时 z 没清零 → ({x:+.2f},{y:+.2f},{z:+.2f}) 模长 13.87 = 1.41×g）。\n确认这是有意为之？': 'Current '
                                                                                                                                               '|g| '
                                                                                                                                               '= '
                                                                                                                                               '{mag:.4f} '
                                                                                                                                               'm/s², '
                                                                                                                                               'deviating '
                                                                                                                                               'from '
                                                                                                                                               '9.81 '
                                                                                                                                               'by '
                                                                                                                                               'more '
                                                                                                                                               'than '
                                                                                                                                               '{pct:.0%}.\n'
                                                                                                                                               '\n'
                                                                                                                                               'Common '
                                                                                                                                               'cause: '
                                                                                                                                               'only '
                                                                                                                                               'one '
                                                                                                                                               'component '
                                                                                                                                               'was '
                                                                                                                                               'changed '
                                                                                                                                               '(e.g. '
                                                                                                                                               'upright→side-mount '
                                                                                                                                               'without '
                                                                                                                                               'zeroing '
                                                                                                                                               'z '
                                                                                                                                               '→ '
                                                                                                                                               '({x:+.2f},{y:+.2f},{z:+.2f}) '
                                                                                                                                               'has '
                                                                                                                                               'magnitude '
                                                                                                                                               '13.87 '
                                                                                                                                               '= '
                                                                                                                                               '1.41×g).\n'
                                                                                                                                               'Confirm '
                                                                                                                                               'this '
                                                                                                                                               'is '
                                                                                                                                               'intentional?',
 '[ERR] 安装方向[{what}] 失败：{err}': '[ERR] Mounting orientation [{what}] failed: {err}',
 '固化到 Flash（0x25）': 'Persist to Flash (0x25)',
 '[ERR] 0x25 PARAM_SAVE 被拒': '[ERR] 0x25 PARAM_SAVE rejected',
 '⚠ 偏离 9.81 超 {pct:.0%}': '⚠ Deviation from 9.81 over {pct:.0%}',
 '[ERR] gravity[{sub}] 被拒：{err}': '[ERR] gravity[{sub}] rejected: {err}',
 '❌ 与写入不一致': '❌ Does not match written value',
 '[ERR] 下发后自检未过：{status}': '[ERR] Post-apply self-check failed: {status}',
 '变了': 'Changed',
 '未变': 'Unchanged',
 '符合预期': 'As expected',
 '⚠ 与预期不符': '⚠ Does not match expectation',
 '分量{sub}({err})': 'Component {sub} ({err})',
 '下发 movej': 'Movej',
 '就绪姿态': 'Ready Pose',
 '把目标填成就绪姿态 [0, 0.5, 0, -1, 0, 0.6, 0]（按轴数裁剪/补 0）\n并立即下发 movej。仍走运动解锁与 Δq 确认。': 'Fill the target with the '
                                                                                'ready pose [0, 0.5, 0, -1, '
                                                                                '0, 0.6, 0] (trimmed/padded '
                                                                                'with 0 per joint count)\n'
                                                                                'and send movej immediately. '
                                                                                'Still goes through motion '
                                                                                'unlock and Δq confirmation.',
 '接管在途运动': 'Take over motion',
 '勾选后直接写一条 movej 旁路帧：固件会作废在途的笛卡尔规划（点动/直线），\n不必等它走完。\n⚠ 若在途的是另一条 movej，SDK 要等原目标超时/到位才返回；\n接管帧本身已经发出，固件会改走新目标。': 'When '
                                                                                                                'checked, '
                                                                                                                'sends '
                                                                                                                'a '
                                                                                                                'movej '
                                                                                                                'bypass '
                                                                                                                'frame '
                                                                                                                'directly: '
                                                                                                                'firmware '
                                                                                                                'discards '
                                                                                                                'the '
                                                                                                                'in-flight '
                                                                                                                'Cartesian '
                                                                                                                'plan '
                                                                                                                '(jog/linear),\n'
                                                                                                                'no '
                                                                                                                'need '
                                                                                                                'to '
                                                                                                                'wait '
                                                                                                                'for '
                                                                                                                'it '
                                                                                                                'to '
                                                                                                                'finish.\n'
                                                                                                                '⚠ '
                                                                                                                'If '
                                                                                                                'the '
                                                                                                                'in-flight '
                                                                                                                'motion '
                                                                                                                'is '
                                                                                                                'another '
                                                                                                                'movej, '
                                                                                                                'the '
                                                                                                                'SDK '
                                                                                                                'still '
                                                                                                                'waits '
                                                                                                                'for '
                                                                                                                'the '
                                                                                                                'original '
                                                                                                                'target '
                                                                                                                'to '
                                                                                                                'time '
                                                                                                                'out '
                                                                                                                'or '
                                                                                                                'be '
                                                                                                                'reached '
                                                                                                                'before '
                                                                                                                'returning;\n'
                                                                                                                'the '
                                                                                                                'takeover '
                                                                                                                'frame '
                                                                                                                'itself '
                                                                                                                'has '
                                                                                                                'already '
                                                                                                                'been '
                                                                                                                'sent, '
                                                                                                                'and '
                                                                                                                'firmware '
                                                                                                                'switches '
                                                                                                                'to '
                                                                                                                'the '
                                                                                                                'new '
                                                                                                                'target.',
 'move_j —— 关节轨迹（绝对角 rad，固件 S 曲线自完成 + 到位静止保持）': 'move_j — joint trajectory (absolute angle rad, firmware '
                                                'S-curve completes on its own + holds at target)',
 '带 tau_ff 前馈': 'With tau_ff feedforward',
 '单发 move_js': 'Send move_js Once',
 'move_js —— 连续伺服透传（单发）': 'move_js — continuous servo passthrough (single shot)',
 '下发 move_mit 单帧': 'Send MIT',
 'move_mit —— 单关节 MIT 透传（单帧，无保活）': 'move_mit — single-joint MIT passthrough (single frame, no keepalive)',
 '下发整臂 MIT 单帧': 'Send all',
 'move_mit_all —— 整臂 MIT 透传（单帧）': 'move_mit_all — whole-arm MIT passthrough (single frame)',
 '⚠ 固件 0.1s 看门狗：连续伺服须以 ≥10Hz 重发，否则 0.1s 后掉 fail-soft 持位。本页只做单发。': '⚠ Firmware 0.1 s watchdog: continuous '
                                                                  'servo must be resent at ≥10 Hz, otherwise '
                                                                  'it drops to fail-soft hold after 0.1 s. '
                                                                  'This page only sends single shots.',
 'kp/kd 对全部关节统一；要逐关节不同请用单关节 move_mit。': 'kp/kd are uniform across all joints; for per-joint values use '
                                        'single-joint move_mit.',
 'kp(统一)': 'kp (all)',
 'kd(统一)': 'kd (all)',
 '时间': 'Time',
 '级别': 'Level',
 '类别': 'Category',
 '内容': 'Content',
 '文本 / 事件名 / 字段…': 'Text / event name / field…',
 '刷新历史': 'Refresh History',
 '导出 JSONL…': 'Export JSONL…',
 '全部': 'All',
 '最低级别': 'Minimum level',
 '显示 {shown} / 共 {total} 条 · 文件 {path}': 'Showing {shown} / {total} entries · file {path}',
 '导出筛选后的日志': 'Export filtered log',
 'JSON Lines (*.jsonl);;全部 (*)': 'JSON Lines (*.jsonl);;All files (*)',
 '导出完成': 'Export complete',
 '已写出 {n} 条 → {path}': 'Wrote {n} entries → {path}',
 '导出日志': 'Export log',
 '当前筛选结果为空。': 'No entries match the current filter.',
 '导出失败': 'Export failed',
 '固件 CMD_HOME 0x2A：各轴低速(固件写死 0.10)回 URDF 零位。\n与 movej(0) 同一条路径，只是速度更低。需先使能。': 'Firmware CMD_HOME 0x2A: every '
                                                                              'axis returns to the URDF zero '
                                                                              'at low speed (firmware '
                                                                              'hard-codes 0.10).\n'
                                                                              'Same path as movej(0), just '
                                                                              'slower. Requires enable '
                                                                              'first.',
 '臂级控制': 'Arm-level control',
 '应用': 'Apply',
 'park（静止保持用全刚度）': 'park (full stiffness for stationary hold)',
 '全局调速器（0..100 整数百分比）': 'Global speed governor (integer percent, 0..100)',
 '读取状态 GET_STATUS': 'Read status GET_STATUS',
 '链路与启动信息': 'Link and boot info',
 '实际速度 = min(单条 movej 的 speed, 本值)。注意这里是百分比：填 1 就是 1% 速度（爬行），不是 0..1 倍率。': 'Actual speed = min(speed of each '
                                                                           'movej, this value). Note this is '
                                                                           'a percentage: 1 means 1% speed '
                                                                           '(crawl), not a 0..1 multiplier.',
 '固件开机签名里的 IWDG 标注 —— 若为 iwdg-rst 说明上电是看门狗复位，排查完再动臂。': 'IWDG marker in the firmware boot signature — if it '
                                                       'shows iwdg-rst, the last power-up was a watchdog '
                                                       'reset; finish troubleshooting before moving the arm.',
 '限速': 'Speed limit',
 '⚠ 急停锁存中 —— 仅 [复位 reset] 可退出 EMERGENCY（固件 1.5.0/M3：失能不再解除锁存）': '⚠ Emergency stop latched — only [reset] can '
                                                                'exit EMERGENCY (firmware 1.5.0/M3: disable '
                                                                'no longer clears the latch)',
 '⚠ 检测到故障位（{detail}）—— 建议先 [清故障 clear_faults]，仍不行则 [复位 reset]。{axes}': '⚠ Fault bit detected ({detail}) — '
                                                                       'try [clear_faults] first; if that '
                                                                       'does not help, [reset].{axes}',
 ' 断轴:{axes}': ' Joint lost:{axes}',
 '曲线放大': 'Enlarge plot',
 '逐关节状态（超温黄底 / 异常码或断轴红底）': 'Per-joint status (overtemp = yellow, fault code or joint lost = red)',
 '显示状态表': 'Show status table',
 '刷新当前': 'Refresh current',
 '下发选中行': 'Send row',
 '下发全部': 'Send all',
 '导入…': 'Import…',
 '从 YAML/JSON 导入整套参数（须先 [刷新当前]）': 'Import a full parameter set from YAML/JSON (run [Refresh current] first)',
 '从 HYY 配置导入…': 'Import HYY…',
 '解析 HYY/SE1 控制器辨识出的 DeviceConfig.yaml, 把参数 + 动力学模型\n写进固件 (无需重新编译固件)。\n映射: 摩擦三元组 / 软限位(与 URDF 硬限位取交集) / tau_max / 重力向量\n      + 模型段 (m/com/I/jm)。\n需先 [刷新当前] 建立基线 (未映射字段从基线取)。': 'Parse '
                                                                                                                                                                                 'the '
                                                                                                                                                                                 'DeviceConfig.yaml '
                                                                                                                                                                                 'identified '
                                                                                                                                                                                 'by '
                                                                                                                                                                                 'the '
                                                                                                                                                                                 'HYY/SE1 '
                                                                                                                                                                                 'controller '
                                                                                                                                                                                 'and '
                                                                                                                                                                                 'write '
                                                                                                                                                                                 'the '
                                                                                                                                                                                 'parameters '
                                                                                                                                                                                 '+ '
                                                                                                                                                                                 'dynamics '
                                                                                                                                                                                 'model\n'
                                                                                                                                                                                 'into '
                                                                                                                                                                                 'the '
                                                                                                                                                                                 'firmware '
                                                                                                                                                                                 '(no '
                                                                                                                                                                                 'firmware '
                                                                                                                                                                                 'rebuild '
                                                                                                                                                                                 'needed).\n'
                                                                                                                                                                                 'Mapped: '
                                                                                                                                                                                 'friction '
                                                                                                                                                                                 'triplets '
                                                                                                                                                                                 '/ '
                                                                                                                                                                                 'soft '
                                                                                                                                                                                 'limits '
                                                                                                                                                                                 '(intersected '
                                                                                                                                                                                 'with '
                                                                                                                                                                                 'URDF '
                                                                                                                                                                                 'hard '
                                                                                                                                                                                 'limits) '
                                                                                                                                                                                 '/ '
                                                                                                                                                                                 'tau_max '
                                                                                                                                                                                 '/ '
                                                                                                                                                                                 'gravity '
                                                                                                                                                                                 'vector\n'
                                                                                                                                                                                 '      '
                                                                                                                                                                                 '+ '
                                                                                                                                                                                 'model '
                                                                                                                                                                                 'section '
                                                                                                                                                                                 '(m/com/I/jm).\n'
                                                                                                                                                                                 'Run '
                                                                                                                                                                                 '[Refresh '
                                                                                                                                                                                 'current] '
                                                                                                                                                                                 'first '
                                                                                                                                                                                 'to '
                                                                                                                                                                                 'establish '
                                                                                                                                                                                 'a '
                                                                                                                                                                                 'baseline '
                                                                                                                                                                                 '(unmapped '
                                                                                                                                                                                 'fields '
                                                                                                                                                                                 'come '
                                                                                                                                                                                 'from '
                                                                                                                                                                                 'the '
                                                                                                                                                                                 'baseline).',
 '回退模型': 'Revert model',
 'CMD_REVERT_MODEL (0x37): 只把动力学模型回退到出厂编译期常量,\n不动其它参数、也不动 flash。\n⚠ 需失能; 且 flash 里的导入模型仍在 (重新上电会复活),\n   此后**不要再点固化** —— 那会永久删除它。': 'CMD_REVERT_MODEL '
                                                                                                                                    '(0x37): '
                                                                                                                                    'reverts '
                                                                                                                                    'only '
                                                                                                                                    'the '
                                                                                                                                    'dynamics '
                                                                                                                                    'model '
                                                                                                                                    'to '
                                                                                                                                    'the '
                                                                                                                                    'factory '
                                                                                                                                    'compile-time '
                                                                                                                                    'constants,\n'
                                                                                                                                    'leaves '
                                                                                                                                    'other '
                                                                                                                                    'parameters '
                                                                                                                                    'and '
                                                                                                                                    'flash '
                                                                                                                                    'untouched.\n'
                                                                                                                                    '⚠ '
                                                                                                                                    'Requires '
                                                                                                                                    'disabled '
                                                                                                                                    'state; '
                                                                                                                                    'the '
                                                                                                                                    'imported '
                                                                                                                                    'model '
                                                                                                                                    'in '
                                                                                                                                    'flash '
                                                                                                                                    'remains '
                                                                                                                                    '(it '
                                                                                                                                    'comes '
                                                                                                                                    'back '
                                                                                                                                    'on '
                                                                                                                                    'power '
                                                                                                                                    'cycle),\n'
                                                                                                                                    '   '
                                                                                                                                    'so '
                                                                                                                                    '**do '
                                                                                                                                    'not '
                                                                                                                                    'press '
                                                                                                                                    'persist '
                                                                                                                                    'again** '
                                                                                                                                    'afterwards '
                                                                                                                                    '— '
                                                                                                                                    'that '
                                                                                                                                    'permanently '
                                                                                                                                    'deletes '
                                                                                                                                    'it.',
 '导出当前': 'Export',
 '固化 Flash…': 'Persist…',
 '恢复出厂…': 'Factory reset…',
 '固件 PARAM_RESET (0x36)：恢复出厂默认 + 失效 flash。\n固件要求失能态（擦写窗口 CPU 停顿），enable 态会回 ERR 0x04。': 'Firmware '
                                                                                        'PARAM_RESET (0x36): '
                                                                                        'restores factory '
                                                                                        'defaults + '
                                                                                        'invalidates flash.\n'
                                                                                        'Firmware requires '
                                                                                        'the disabled state '
                                                                                        '(CPU stalls during '
                                                                                        'the erase window); '
                                                                                        'in enabled state it '
                                                                                        'returns ERR 0x04.',
 '❓ 调参指南': '❓ Guide',
 '打开[调参指南]页并跳到选中行的参数详解 (纯说明, 无需连接)': "Open the [Tuning guide] page at the selected row's parameter details "
                                     '(docs only, no connection needed)',
 '逐关节参数 (双击编辑; 黄=已改未下发; 红=越界/下发失败)': 'Joint parameters (yellow: unsent; red: invalid/failed)',
 '提示: [kp/kd/tau_max] 与 [q_min/q_max] 成组下发 (选中任一组员即整组下发); 标 (v2) 的摩擦参数在 friction_model=1 时生效; 行首悬停见写口/范围。': 'Tip: '
                                                                                                            '[kp/kd/tau_max] '
                                                                                                            'and '
                                                                                                            '[q_min/q_max] '
                                                                                                            'are '
                                                                                                            'sent '
                                                                                                            'as '
                                                                                                            'a '
                                                                                                            'group '
                                                                                                            '(selecting '
                                                                                                            'any '
                                                                                                            'member '
                                                                                                            'sends '
                                                                                                            'the '
                                                                                                            'whole '
                                                                                                            'group); '
                                                                                                            'friction '
                                                                                                            'parameters '
                                                                                                            'marked '
                                                                                                            '(v2) '
                                                                                                            'take '
                                                                                                            'effect '
                                                                                                            'when '
                                                                                                            'friction_model=1; '
                                                                                                            'hover '
                                                                                                            'the '
                                                                                                            'row '
                                                                                                            'header '
                                                                                                            'for '
                                                                                                            'write '
                                                                                                            'command/range.',
 '全局参数 (写 0x28 / 读 0x2C) — 悬停各项看详解': 'Global parameters (write 0x28 / read 0x2C) — hover each item for '
                                     'details',
 '下发全局\n(含 ff_mask)': 'Send global\n(incl. ff_mask)',
 '把上表全局标量 + 右侧 ff_mask 一次性下发 RAM (0x28/0x27, 每写等 ACK)': 'Send the global scalars above plus ff_mask on the '
                                                        'right to RAM in one go (0x28/0x27, waits for ACK on '
                                                        'each write)',
 'ff_mask 前馈使能位 (写 0x27) — 缩写 M/G/I/C/F/Intg/Wall/Q/V, 悬停看含义': 'ff_mask feedforward enable bits (write 0x27) '
                                                               '— abbreviations M/G/I/C/F/Intg/Wall/Q/V, '
                                                               'hover for meaning',
 '模型: — (未读)': 'Model: — (not read)',
 '动力学模型来源。\n  出厂 = 编译期常量 (dyn_model_data.h / dyn_jm_default.h)\n  导入 = 经 0x30/0x32/0x33 写入的辨识参数\n  staged = 已写入暂存区但尚未 commit 的项数\n  未固化 = RAM 与 flash 不一致 (掉电会回退)': 'Dynamics '
                                                                                                                                                                    'model '
                                                                                                                                                                    'source.\n'
                                                                                                                                                                    '  '
                                                                                                                                                                    'factory '
                                                                                                                                                                    '= '
                                                                                                                                                                    'compile-time '
                                                                                                                                                                    'constants '
                                                                                                                                                                    '(dyn_model_data.h '
                                                                                                                                                                    '/ '
                                                                                                                                                                    'dyn_jm_default.h)\n'
                                                                                                                                                                    '  '
                                                                                                                                                                    'imported '
                                                                                                                                                                    '= '
                                                                                                                                                                    'identification '
                                                                                                                                                                    'parameters '
                                                                                                                                                                    'written '
                                                                                                                                                                    'via '
                                                                                                                                                                    '0x30/0x32/0x33\n'
                                                                                                                                                                    '  '
                                                                                                                                                                    'staged '
                                                                                                                                                                    '= '
                                                                                                                                                                    'items '
                                                                                                                                                                    'written '
                                                                                                                                                                    'to '
                                                                                                                                                                    'the '
                                                                                                                                                                    'staging '
                                                                                                                                                                    'area '
                                                                                                                                                                    'but '
                                                                                                                                                                    'not '
                                                                                                                                                                    'yet '
                                                                                                                                                                    'committed\n'
                                                                                                                                                                    '  '
                                                                                                                                                                    'not '
                                                                                                                                                                    'persisted '
                                                                                                                                                                    '= '
                                                                                                                                                                    'RAM '
                                                                                                                                                                    'differs '
                                                                                                                                                                    'from '
                                                                                                                                                                    'flash '
                                                                                                                                                                    '(reverts '
                                                                                                                                                                    'on '
                                                                                                                                                                    'power '
                                                                                                                                                                    'loss)',
 '{label} ({key}) · 写口 {write} · 范围 {range}\n\n{detail}': '{label} ({key}) · write command {write} · range '
                                                          '{range}\n'
                                                          '\n'
                                                          '{detail}',
 '{name}  (bit{bit} · 0x{mask:02X})\n{label}\n\n{detail}\n\n改后需 [下发全局] 才生效 (发送前有确认)': '{name}  (bit{bit} · '
                                                                                      '0x{mask:02X})\n'
                                                                                      '{label}\n'
                                                                                      '\n'
                                                                                      '{detail}\n'
                                                                                      '\n'
                                                                                      'Changes take effect '
                                                                                      'only after [Send '
                                                                                      'global] (confirmation '
                                                                                      'before sending)',
 '0x22 (kp/kd/tau_max 按关节成组)': '0x22 (kp/kd/tau_max grouped by joint)',
 '0x23 (q_min/q_max 成组, 须 q_min<q_max)': '0x23 (q_min/q_max grouped, requires q_min<q_max)',
 '{detail}\n\n范围 {range}': '{detail}\n\nRange {range}',
 '执行中: {what} …': 'Running: {what} …',
 '调参[{what}]': 'Tuning[{what}]',
 '选择 HYY/SE1 辨识配置': 'Select HYY/SE1 identification config',
 'DeviceConfig (*.yaml *.yml);;所有文件 (*)': 'DeviceConfig (*.yaml *.yml);;All files (*)',
 '[INFO] 调参[导入HYY] {name} sha={sha} v{version} — 未映射 {n} 项': '[INFO] Tuning[Import HYY] {name} sha={sha} '
                                                             'v{version} — {n} unmapped items',
 '⚠ 机械臂硬件可能异常': '⚠ Robot arm hardware may be faulty',
 '我已知晓，仍要导入': 'I understand, import anyway',
 '取消 (先去排查)': 'Cancel (troubleshoot first)',
 '[WARN] 调参[导入HYY] 摩擦不对称 {choice}: {items}': '[WARN] Tuning[Import HYY] friction asymmetry {choice}: {items}',
 '[INFO] 调参[导入HYY] 差异 {diffs} 项 + 模型 {models} 项, 固化={save}': '[INFO] Tuning[Import HYY] {diffs} differing '
                                                             'items + {models} model items, persist={save}',
 '读模型状态': 'Read model status',
 '刷新完成 — {n} 关节 × {params} 项 + 全局 (ff_mask={mask} = 0x{mask_hex}); 已允许编辑/下发': 'Refresh complete — {n} joints '
                                                                              '× {params} items + globals '
                                                                              '(ff_mask={mask} = '
                                                                              '0x{mask_hex}); '
                                                                              'editing/sending now enabled',
 '[OK] 调参[刷新] 读回全量完成': '[OK] Tuning[Refresh] full read-back complete',
 '导入/覆盖': 'Import/Overwrite',
 '出厂(编译期常量)': 'Factory (compile-time constants)',
 '拿不到当前关节角，无法校验新限位是否包含当前 q — 等一帧状态再试': 'Current joint angles unavailable; cannot verify the new limits '
                                       'contain the current q — wait for a status frame and retry',
 '下发': 'Send',
 '下发 {n} 行': 'Send {n} rows',
 '下发全局': 'Send global',
 '选择参数文件': 'Select parameter file',
 '参数文件 (*.yaml *.yml *.json);;所有文件 (*)': 'Parameter files (*.yaml *.yml *.json);;All files (*)',
 '[INFO] 调参[导入] {path}: 差异 {n} 项, 固化={save}': '[INFO] Tuning[Import] {path}: {n} differing items, '
                                              'persist={save}',
 'HYY 导入下发': 'HYY import and send',
 '批量下发': 'Batch send',
 '批量下发完成: 关节成功 {ok}/失败 {fail}, 全局失败 {gfail}': 'Batch send complete: joints {ok} succeeded / {fail} failed, '
                                              'globals {gfail} failed',
 '导入下发完成: 摩擦项成功 {ok}/失败 {fail}, 模型 {model}': 'Import send complete: friction items {ok} succeeded / {fail} '
                                             'failed, model {model}',
 '; 已固化到 Flash': '; persisted to flash',
 '导出当前参数': 'Export current parameters',
 '参数文件 (*.yaml)': 'Parameter files (*.yaml)',
 '恢复出厂': 'Restore factory defaults',
 '参数导入 — 差异预览': 'Parameter import — diff preview',
 '下发后固化到 Flash (param_save; 须先失能)': 'Persist to flash after sending (param_save; requires disable first)',
 '取消': 'Cancel',
 '未连接 — 连接后可用（参数读写经 litearm）': 'Not connected — available once connected (parameter reads/writes go through '
                               'litearm)',
 '已连接 — 尚未读取设备参数, 请先 [刷新当前]; 在此之前禁下发/编辑': 'Connected — device parameters not read yet; run [Refresh current] '
                                          'first; sending/editing disabled until then',
 '离线, 忽略操作': 'Offline, operation ignored',
 '忙: 前一条调参操作仍在执行, 已忽略 {what}': 'Busy: previous tuning operation still running, ignored {what}',
 '忙: 运动/控制命令在途 (MainWindow), 已忽略调参操作': 'Busy: motion/control command in flight (MainWindow), tuning '
                                       'operation ignored',
 '[ERR] 调参[{what}] 失败: {err}': '[ERR] Tuning[{what}] failed: {err}',
 '导入 HYY 配置': 'Import HYY config',
 '固件不支持': 'Not supported by firmware',
 '本固件的动力学模型是编译期常量, 没有在线导入能力 (0x34 不可用)。\n\n请先升级固件到含 0x30/0x32/0x33/0x34/0x35 命令的版本。': 'This firmware keeps '
                                                                                      'the dynamics model as '
                                                                                      'compile-time '
                                                                                      'constants and has no '
                                                                                      'online import '
                                                                                      'capability (0x34 '
                                                                                      'unavailable).\n'
                                                                                      '\n'
                                                                                      'Upgrade the firmware '
                                                                                      'to a version that '
                                                                                      'includes the '
                                                                                      '0x30/0x32/0x33/0x34/0x35 '
                                                                                      'commands.',
 '模型参数非法': 'Invalid model parameters',
 '以下项不合法, 已拒绝导入:\n  {items}': 'The following items are invalid; import rejected:\n  {items}',
 '同一关节正、反两向的摩擦力本应大致对称。相差超过一倍, 通常意味着机械上已经出了问题:<br>&nbsp;&nbsp;&nbsp;&nbsp;· 轴承发卡 / 减速器磨损 / 异物<br>&nbsp;&nbsp;&nbsp;&nbsp;· 预紧异常<br>&nbsp;&nbsp;&nbsp;&nbsp;· 或辨识时该关节被外力干扰 —— 那种情况下本次参数本身也不可信<br><br><b>⚠ 导入参数不会修好机械问题。</b><br>建议先人工检查这些关节 (手动转动感受阻力、听异响、测温升), 再决定是否继续。<br><br>继续导入不会造成额外损害; 取消则可先去排查。': 'Friction '
                                                                                                                                                                                                                                                                                                       'in '
                                                                                                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                                                                                                       'forward '
                                                                                                                                                                                                                                                                                                       'and '
                                                                                                                                                                                                                                                                                                       'reverse '
                                                                                                                                                                                                                                                                                                       'directions '
                                                                                                                                                                                                                                                                                                       'of '
                                                                                                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                                                                                                       'same '
                                                                                                                                                                                                                                                                                                       'joint '
                                                                                                                                                                                                                                                                                                       'should '
                                                                                                                                                                                                                                                                                                       'be '
                                                                                                                                                                                                                                                                                                       'roughly '
                                                                                                                                                                                                                                                                                                       'symmetric. '
                                                                                                                                                                                                                                                                                                       'Differing '
                                                                                                                                                                                                                                                                                                       'by '
                                                                                                                                                                                                                                                                                                       'more '
                                                                                                                                                                                                                                                                                                       'than '
                                                                                                                                                                                                                                                                                                       'a '
                                                                                                                                                                                                                                                                                                       'factor '
                                                                                                                                                                                                                                                                                                       'of '
                                                                                                                                                                                                                                                                                                       'two '
                                                                                                                                                                                                                                                                                                       'usually '
                                                                                                                                                                                                                                                                                                       'means '
                                                                                                                                                                                                                                                                                                       'something '
                                                                                                                                                                                                                                                                                                       'is '
                                                                                                                                                                                                                                                                                                       'already '
                                                                                                                                                                                                                                                                                                       'wrong '
                                                                                                                                                                                                                                                                                                       'mechanically:<br>&nbsp;&nbsp;&nbsp;&nbsp;· '
                                                                                                                                                                                                                                                                                                       'Sticking '
                                                                                                                                                                                                                                                                                                       'bearing '
                                                                                                                                                                                                                                                                                                       '/ '
                                                                                                                                                                                                                                                                                                       'reducer '
                                                                                                                                                                                                                                                                                                       'wear '
                                                                                                                                                                                                                                                                                                       '/ '
                                                                                                                                                                                                                                                                                                       'foreign '
                                                                                                                                                                                                                                                                                                       'object<br>&nbsp;&nbsp;&nbsp;&nbsp;· '
                                                                                                                                                                                                                                                                                                       'Abnormal '
                                                                                                                                                                                                                                                                                                       'preload<br>&nbsp;&nbsp;&nbsp;&nbsp;· '
                                                                                                                                                                                                                                                                                                       'Or '
                                                                                                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                                                                                                       'joint '
                                                                                                                                                                                                                                                                                                       'was '
                                                                                                                                                                                                                                                                                                       'disturbed '
                                                                                                                                                                                                                                                                                                       'by '
                                                                                                                                                                                                                                                                                                       'external '
                                                                                                                                                                                                                                                                                                       'force '
                                                                                                                                                                                                                                                                                                       'during '
                                                                                                                                                                                                                                                                                                       'identification '
                                                                                                                                                                                                                                                                                                       '— '
                                                                                                                                                                                                                                                                                                       'in '
                                                                                                                                                                                                                                                                                                       'that '
                                                                                                                                                                                                                                                                                                       'case '
                                                                                                                                                                                                                                                                                                       'these '
                                                                                                                                                                                                                                                                                                       'parameters '
                                                                                                                                                                                                                                                                                                       'are '
                                                                                                                                                                                                                                                                                                       'not '
                                                                                                                                                                                                                                                                                                       'trustworthy '
                                                                                                                                                                                                                                                                                                       'either<br><br><b>⚠ '
                                                                                                                                                                                                                                                                                                       'Importing '
                                                                                                                                                                                                                                                                                                       'parameters '
                                                                                                                                                                                                                                                                                                       'will '
                                                                                                                                                                                                                                                                                                       'not '
                                                                                                                                                                                                                                                                                                       'fix '
                                                                                                                                                                                                                                                                                                       'a '
                                                                                                                                                                                                                                                                                                       'mechanical '
                                                                                                                                                                                                                                                                                                       'problem.</b><br>Inspect '
                                                                                                                                                                                                                                                                                                       'these '
                                                                                                                                                                                                                                                                                                       'joints '
                                                                                                                                                                                                                                                                                                       'by '
                                                                                                                                                                                                                                                                                                       'hand '
                                                                                                                                                                                                                                                                                                       'first '
                                                                                                                                                                                                                                                                                                       '(feel '
                                                                                                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                                                                                                       'resistance '
                                                                                                                                                                                                                                                                                                       'when '
                                                                                                                                                                                                                                                                                                       'turning, '
                                                                                                                                                                                                                                                                                                       'listen '
                                                                                                                                                                                                                                                                                                       'for '
                                                                                                                                                                                                                                                                                                       'abnormal '
                                                                                                                                                                                                                                                                                                       'noise, '
                                                                                                                                                                                                                                                                                                       'check '
                                                                                                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                                                                                                       'temperature '
                                                                                                                                                                                                                                                                                                       'rise), '
                                                                                                                                                                                                                                                                                                       'then '
                                                                                                                                                                                                                                                                                                       'decide '
                                                                                                                                                                                                                                                                                                       'whether '
                                                                                                                                                                                                                                                                                                       'to '
                                                                                                                                                                                                                                                                                                       'continue.<br><br>Continuing '
                                                                                                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                                                                                                       'import '
                                                                                                                                                                                                                                                                                                       'causes '
                                                                                                                                                                                                                                                                                                       'no '
                                                                                                                                                                                                                                                                                                       'extra '
                                                                                                                                                                                                                                                                                                       'damage; '
                                                                                                                                                                                                                                                                                                       'cancel '
                                                                                                                                                                                                                                                                                                       'to '
                                                                                                                                                                                                                                                                                                       'go '
                                                                                                                                                                                                                                                                                                       'troubleshoot '
                                                                                                                                                                                                                                                                                                       'first.',
 '需先失能': 'Disable required',
 '动力学模型 commit 要求失能态 (固件 0x32 门控)。\n\n请先在 [控制] 页失能, 再重跑导入。\n（本次未发出任何 0x30 帧, 暂存区未被污染。）': 'Dynamics model '
                                                                                         'commit requires '
                                                                                         'the disabled state '
                                                                                         '(gated by firmware '
                                                                                         '0x32).\n'
                                                                                         '\n'
                                                                                         'Disable on the '
                                                                                         '[Control] page '
                                                                                         'first, then rerun '
                                                                                         'the import.\n'
                                                                                         '(No 0x30 frames '
                                                                                         'were sent this '
                                                                                         'time; the staging '
                                                                                         'area is '
                                                                                         'untouched.)',
 '导入已取消': 'Import cancelled',
 '确认回退模型': 'Confirm model revert',
 '把动力学模型回退到**出厂编译期常量** (含 jm)。\n\n· 不动其它参数、不动 flash\n· ⚠ flash 里的导入模型仍在 —— **重新上电会复活**\n· ⚠ 此后不要再点 [固化 Flash] —— 那会永久删除 flash 里的导入模型\n· 需失能态': 'Revert '
                                                                                                                                               'the '
                                                                                                                                               'dynamics '
                                                                                                                                               'model '
                                                                                                                                               'to '
                                                                                                                                               'the '
                                                                                                                                               '**factory '
                                                                                                                                               'compile-time '
                                                                                                                                               'constants** '
                                                                                                                                               '(including '
                                                                                                                                               'jm).\n'
                                                                                                                                               '\n'
                                                                                                                                               '· '
                                                                                                                                               'Other '
                                                                                                                                               'parameters '
                                                                                                                                               'and '
                                                                                                                                               'flash '
                                                                                                                                               'are '
                                                                                                                                               'untouched\n'
                                                                                                                                               '· '
                                                                                                                                               '⚠ '
                                                                                                                                               'The '
                                                                                                                                               'imported '
                                                                                                                                               'model '
                                                                                                                                               'in '
                                                                                                                                               'flash '
                                                                                                                                               'remains '
                                                                                                                                               '— '
                                                                                                                                               '**it '
                                                                                                                                               'comes '
                                                                                                                                               'back '
                                                                                                                                               'on '
                                                                                                                                               'power '
                                                                                                                                               'cycle**\n'
                                                                                                                                               '· '
                                                                                                                                               '⚠ '
                                                                                                                                               'Do '
                                                                                                                                               'not '
                                                                                                                                               'press '
                                                                                                                                               '[Persist '
                                                                                                                                               'to '
                                                                                                                                               'Flash] '
                                                                                                                                               'afterwards '
                                                                                                                                               '— '
                                                                                                                                               'that '
                                                                                                                                               'permanently '
                                                                                                                                               'deletes '
                                                                                                                                               'the '
                                                                                                                                               'imported '
                                                                                                                                               'model '
                                                                                                                                               'in '
                                                                                                                                               'flash\n'
                                                                                                                                               '· '
                                                                                                                                               'Requires '
                                                                                                                                               'disabled '
                                                                                                                                               'state',
 '模型已回退到出厂编译期常量 (RAM)。⚠ 不要再点固化 —— 那会永久删除 flash 里的导入模型。': 'Model reverted to the factory compile-time '
                                                         'constants (RAM). ⚠ Do not press persist again — '
                                                         'that permanently deletes the imported model in '
                                                         'flash.',
 '[OK] 调参[回退模型] 完成': '[OK] Tuning[Revert model] complete',
 '回退失败: {err}': 'Revert failed: {err}',
 '[ERR] 调参[回退模型] {err}': '[ERR] Tuning[Revert model] {err}',
 '模型: 固件不支持在线导入 (0x34 不可用) —— 请升级固件': 'Model: firmware does not support online import (0x34 unavailable) — '
                                      'please upgrade firmware',
 '暂存 0x{mask:03X}': 'Staged 0x{mask:03X}',
 '未固化': 'Not persisted',
 '模型: {src}': 'Model: {src}',
 '本机没有这个关节（台架 1J 只有 J1）': 'This joint is not present on this machine (1J bench has only J1)',
 'ff_mask 已改动 — 下发全局时将弹确认框': 'ff_mask changed — a confirmation dialog will appear when sending globals',
 '未读取设备数据 — 请先 [刷新当前], 已拒绝 {what}': 'Device data not read yet — run [Refresh current] first; rejected {what}',
 'J{axis} 当前 q={q:.4f} rad 不在新限位 [{qmin:.4f}, {qmax:.4f}] 内 — 拒绝下发 (防即时 POS_VIOL/FAULT)': 'J{axis} current '
                                                                                          'q={q:.4f} rad is '
                                                                                          'outside the new '
                                                                                          'limits '
                                                                                          '[{qmin:.4f}, '
                                                                                          '{qmax:.4f}] — '
                                                                                          'send rejected '
                                                                                          '(prevents '
                                                                                          'immediate '
                                                                                          'POS_VIOL/FAULT)',
 '未选中行 — 请先点选一行 (或用 [下发全部])': 'No row selected — click a row first (or use [Send all])',
 '逐关节/成组参数下发 (0x22/0x23/0x26)': 'Per-joint/grouped parameter send (0x22/0x23/0x26)',
 '[ERR] 调参[下发] {key} J{axis}: {text}': '[ERR] Tuning[Send] {key} J{axis}: {text}',
 '下发完成: 成功 {ok} 项, 失败 {fail} 项 (格已标红)': 'Send complete: {ok} succeeded, {fail} failed (cells marked red)',
 '下发完成 — {n} 项全部 ACK': 'Send complete — all {n} items ACKed',
 '[OK] 调参[下发] {n} 项全部 ACK': '[OK] Tuning[Send] all {n} items ACKed',
 '全局参数/前馈下发 (0x28 + ff_mask 0x27)': 'Global parameter/feedforward send (0x28 + ff_mask 0x27)',
 '全局下发完成 — 全部 ACK': 'Global send complete — all ACKed',
 '[OK] 调参[全局] 全部 ACK': '[OK] Tuning[Global] all ACKed',
 '全局下发部分失败: {items}': 'Global send partially failed: {items}',
 '[ERR] 调参[全局] 失败项: {items}': '[ERR] Tuning[Global] failed items: {items}',
 '导入': 'Import',
 '确认导入下发': 'Confirm import and send',
 '**只导动力学辨识的产物**, 其余一项不碰:\n  · 摩擦三元组 fv/fc0/fc1 (0x26 item 9/10/11, {joints} 轴各一组)\n  · **动力学模型** body1..7 + jm (0x30/0x33) → commit (0x32, 须失能)\n  · 读回逐项比对 (不一致则**中止, 不固化**)\n{save_line}\n不动: kp/kd/tau_max/软限位/全局标量/ff_mask —— 它们是设备自身口径,\n      yaml 里对应的 smin-smax / torque_max / gravity 是 HYY 控制器配置,\n      不是辨识结果 (见未映射清单)。\n\n模型是力矩前馈的输入 —— 请确认臂已失能且有人看护。': '**Imports '
                                                                                                                                                                                                                                                                                                                                                                      'only '
                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                      'dynamics '
                                                                                                                                                                                                                                                                                                                                                                      'identification '
                                                                                                                                                                                                                                                                                                                                                                      'output**, '
                                                                                                                                                                                                                                                                                                                                                                      'nothing '
                                                                                                                                                                                                                                                                                                                                                                      'else '
                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                      'touched:\n'
                                                                                                                                                                                                                                                                                                                                                                      '  '
                                                                                                                                                                                                                                                                                                                                                                      '· '
                                                                                                                                                                                                                                                                                                                                                                      'friction '
                                                                                                                                                                                                                                                                                                                                                                      'triplets '
                                                                                                                                                                                                                                                                                                                                                                      'fv/fc0/fc1 '
                                                                                                                                                                                                                                                                                                                                                                      '(0x26 '
                                                                                                                                                                                                                                                                                                                                                                      'item '
                                                                                                                                                                                                                                                                                                                                                                      '9/10/11, '
                                                                                                                                                                                                                                                                                                                                                                      'one '
                                                                                                                                                                                                                                                                                                                                                                      'set '
                                                                                                                                                                                                                                                                                                                                                                      'per '
                                                                                                                                                                                                                                                                                                                                                                      'axis '
                                                                                                                                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                                                                                                                                      '{joints} '
                                                                                                                                                                                                                                                                                                                                                                      'axes)\n'
                                                                                                                                                                                                                                                                                                                                                                      '  '
                                                                                                                                                                                                                                                                                                                                                                      '· '
                                                                                                                                                                                                                                                                                                                                                                      '**dynamics '
                                                                                                                                                                                                                                                                                                                                                                      'model** '
                                                                                                                                                                                                                                                                                                                                                                      'body1..7 '
                                                                                                                                                                                                                                                                                                                                                                      '+ '
                                                                                                                                                                                                                                                                                                                                                                      'jm '
                                                                                                                                                                                                                                                                                                                                                                      '(0x30/0x33) '
                                                                                                                                                                                                                                                                                                                                                                      '→ '
                                                                                                                                                                                                                                                                                                                                                                      'commit '
                                                                                                                                                                                                                                                                                                                                                                      '(0x32, '
                                                                                                                                                                                                                                                                                                                                                                      'requires '
                                                                                                                                                                                                                                                                                                                                                                      'disable)\n'
                                                                                                                                                                                                                                                                                                                                                                      '  '
                                                                                                                                                                                                                                                                                                                                                                      '· '
                                                                                                                                                                                                                                                                                                                                                                      'read '
                                                                                                                                                                                                                                                                                                                                                                      'back '
                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                      'compare '
                                                                                                                                                                                                                                                                                                                                                                      'item '
                                                                                                                                                                                                                                                                                                                                                                      'by '
                                                                                                                                                                                                                                                                                                                                                                      'item '
                                                                                                                                                                                                                                                                                                                                                                      '(on '
                                                                                                                                                                                                                                                                                                                                                                      'mismatch '
                                                                                                                                                                                                                                                                                                                                                                      '**abort, '
                                                                                                                                                                                                                                                                                                                                                                      'do '
                                                                                                                                                                                                                                                                                                                                                                      'not '
                                                                                                                                                                                                                                                                                                                                                                      'persist**)\n'
                                                                                                                                                                                                                                                                                                                                                                      '{save_line}\n'
                                                                                                                                                                                                                                                                                                                                                                      'Not '
                                                                                                                                                                                                                                                                                                                                                                      'touched: '
                                                                                                                                                                                                                                                                                                                                                                      'kp/kd/tau_max/soft '
                                                                                                                                                                                                                                                                                                                                                                      'limits/global '
                                                                                                                                                                                                                                                                                                                                                                      'scalars/ff_mask '
                                                                                                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                                                                                                      'they '
                                                                                                                                                                                                                                                                                                                                                                      'follow '
                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                      "device's "
                                                                                                                                                                                                                                                                                                                                                                      'own '
                                                                                                                                                                                                                                                                                                                                                                      'conventions;\n'
                                                                                                                                                                                                                                                                                                                                                                      '      '
                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                      'corresponding '
                                                                                                                                                                                                                                                                                                                                                                      'smin-smax '
                                                                                                                                                                                                                                                                                                                                                                      '/ '
                                                                                                                                                                                                                                                                                                                                                                      'torque_max '
                                                                                                                                                                                                                                                                                                                                                                      '/ '
                                                                                                                                                                                                                                                                                                                                                                      'gravity '
                                                                                                                                                                                                                                                                                                                                                                      'in '
                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                      'yaml '
                                                                                                                                                                                                                                                                                                                                                                      'are '
                                                                                                                                                                                                                                                                                                                                                                      'HYY '
                                                                                                                                                                                                                                                                                                                                                                      'controller '
                                                                                                                                                                                                                                                                                                                                                                      'settings,\n'
                                                                                                                                                                                                                                                                                                                                                                      '      '
                                                                                                                                                                                                                                                                                                                                                                      'not '
                                                                                                                                                                                                                                                                                                                                                                      'identification '
                                                                                                                                                                                                                                                                                                                                                                      'results '
                                                                                                                                                                                                                                                                                                                                                                      '(see '
                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                      'unmapped '
                                                                                                                                                                                                                                                                                                                                                                      'list).\n'
                                                                                                                                                                                                                                                                                                                                                                      '\n'
                                                                                                                                                                                                                                                                                                                                                                      'The '
                                                                                                                                                                                                                                                                                                                                                                      'model '
                                                                                                                                                                                                                                                                                                                                                                      'feeds '
                                                                                                                                                                                                                                                                                                                                                                      'torque '
                                                                                                                                                                                                                                                                                                                                                                      'feedforward '
                                                                                                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                                                                                                      'make '
                                                                                                                                                                                                                                                                                                                                                                      'sure '
                                                                                                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                                                                                                      'arm '
                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                      'disabled '
                                                                                                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                                                                                                      'someone '
                                                                                                                                                                                                                                                                                                                                                                      'is '
                                                                                                                                                                                                                                                                                                                                                                      'watching '
                                                                                                                                                                                                                                                                                                                                                                      'it.',
 '导入下发已取消': 'Import and send cancelled',
 'HYY 导入 (0x26 item9-11 + 0x30/0x33/0x32)': 'HYY import (0x26 item9-11 + 0x30/0x33/0x32)',
 '整套下发': 'Send full set',
 '确认批量下发': 'Confirm batch send',
 '将按固件写口顺序逐条下发整套参数\n  · 关节 {joints} × {params} 项 (0x22/0x23/0x26)\n  · 全局标量 + friction_model + ff_mask (0x28/0x27)\n\n下发生效为即时 RAM 修改 (刚度/限位/前馈), 请确认当前安全。': 'The '
                                                                                                                                                            'full '
                                                                                                                                                            'parameter '
                                                                                                                                                            'set '
                                                                                                                                                            'will '
                                                                                                                                                            'be '
                                                                                                                                                            'sent '
                                                                                                                                                            'one '
                                                                                                                                                            'by '
                                                                                                                                                            'one '
                                                                                                                                                            'in '
                                                                                                                                                            'firmware '
                                                                                                                                                            'write '
                                                                                                                                                            'order\n'
                                                                                                                                                            '  '
                                                                                                                                                            '· '
                                                                                                                                                            'joints '
                                                                                                                                                            '{joints} '
                                                                                                                                                            '× '
                                                                                                                                                            '{params} '
                                                                                                                                                            'items '
                                                                                                                                                            '(0x22/0x23/0x26)\n'
                                                                                                                                                            '  '
                                                                                                                                                            '· '
                                                                                                                                                            'global '
                                                                                                                                                            'scalars '
                                                                                                                                                            '+ '
                                                                                                                                                            'friction_model '
                                                                                                                                                            '+ '
                                                                                                                                                            'ff_mask '
                                                                                                                                                            '(0x28/0x27)\n'
                                                                                                                                                            '\n'
                                                                                                                                                            'Sending '
                                                                                                                                                            'applies '
                                                                                                                                                            'immediately '
                                                                                                                                                            'to '
                                                                                                                                                            'RAM '
                                                                                                                                                            '(stiffness/limits/feedforward) '
                                                                                                                                                            '— '
                                                                                                                                                            'confirm '
                                                                                                                                                            'the '
                                                                                                                                                            'current '
                                                                                                                                                            'state '
                                                                                                                                                            'is '
                                                                                                                                                            'safe.',
 '批量下发已取消': 'Batch send cancelled',
 '限位写被拒绝': 'Limit write rejected',
 '批量整套参数下发 (0x22/0x23/0x26/0x28/0x27)': 'Batch send of the full parameter set (0x22/0x23/0x26/0x28/0x27)',
 '[ERR] 调参[批量] {key} J{axis}: {text}': '[ERR] Tuning[Batch] {key} J{axis}: {text}',
 '[ERR] 调参[模型] commit 被拒: {err}{aborted}': '[ERR] Tuning[Model] commit rejected: {err}{aborted}',
 '[ERR] 调参[模型] 读回不一致 {label}: 期望 {want} 实际 {got}': '[ERR] Tuning[Model] read-back mismatch {label}: expected '
                                                   '{want}, got {got}',
 '; 固化失败 (enable 态会返回 0x04 须先失能)': '; persist failed (enabled state returns 0x04; disable first)',
 '; ⚠ **未固化** —— 本次改动只在 RAM, 掉电即回退。请勾选『下发后固化到 Flash』重跑, 或点 [固化 Flash…]': '; ⚠ **Not persisted** — changes '
                                                                         'are in RAM only and revert on '
                                                                         'power loss. Tick “Persist to flash '
                                                                         'after sending” and rerun, or click '
                                                                         '[Persist to Flash…]',
 '调参[批量] {msg}': 'Tuning[Batch] {msg}',
 '导出': 'Export',
 '固化': 'Persist',
 '固化到 Flash (1/2)': 'Persist to flash (1/2)',
 '将把当前 RAM 参数写入 Flash 持久化 (涉及扇区擦除)。\n\n固件要求关节处于 disable 态 (enable 态返回 ERR 0x04)。': 'The current RAM '
                                                                                   'parameters will be '
                                                                                   'written to flash for '
                                                                                   'persistence (involves '
                                                                                   'sector erase).\n'
                                                                                   '\n'
                                                                                   'Firmware requires the '
                                                                                   'arm to be disabled '
                                                                                   '(enabled state returns '
                                                                                   'ERR 0x04).',
 '再次确认固化 (2/2)': 'Confirm persist again (2/2)',
 'Flash 参数在下电后仍生效, 固件会整体重钳一遍所有参数。\n\n确认现在固化?': 'Flash parameters survive power-down; the firmware re-clamps '
                                               'all parameters on boot.\n'
                                               '\n'
                                               'Persist now?',
 '固化已取消': 'Persist cancelled',
 '固件拒绝: {err}': 'Firmware rejected: {err}',
 '恢复出厂 (1/2)': 'Factory reset (1/2)',
 '将把全部运行时参数改回固件出厂默认，并失效 Flash 里已保存的参数。\n\n当前 RAM 与 Flash 的改动都会丢失。固件要求关节处于 disable 态。': 'This restores all '
                                                                                       'runtime parameters '
                                                                                       'to firmware factory '
                                                                                       'defaults and '
                                                                                       'invalidates the '
                                                                                       'parameters saved in '
                                                                                       'flash.\n'
                                                                                       '\n'
                                                                                       'All current RAM and '
                                                                                       'flash changes will '
                                                                                       'be lost. Firmware '
                                                                                       'requires joints to '
                                                                                       'be in disable state.',
 '再次确认恢复出厂 (2/2)': 'Confirm factory reset again (2/2)',
 '确认现在恢复出厂？': 'Confirm factory reset now?',
 '恢复出厂已取消': 'Factory reset canceled',
 '调参[恢复出厂] {text}': 'Tuning [Factory reset] {text}',
 '调参[固化] {text}': 'Tuning [Persist] {text}',
 '本文件**含动力学模型段** —— 将写入连杆动力学 (m/com/I) 与电机转子惯量 jm。': 'This file **contains a dynamics model section** — link '
                                                     'dynamics (m/com/I) and motor rotor inertia jm will be '
                                                     'written.',
 '本文件**不含动力学模型段** —— 关节与全局参数会下发，**动力学模型不会被改动**。': 'This file **does not contain a dynamics model section** — '
                                                  'joint and global parameters will be sent; **the dynamics '
                                                  'model will not be changed**.',
 '尚无设备基线 (未刷新过) — 下表为待导入全量参数, 请逐项核对。': 'No device baseline yet (never refreshed) — the table below lists the '
                                       'full parameter set to import; verify each item.',
 '关节参数': 'Joint parameters',
 '全局参数': 'Global parameters',
 '旧值 (设备当前)': 'Old value (current on device)',
 '新值 (导入)': 'New value (imported)',
 '说明': 'Note',
 '新增': 'Added',
 '修改': 'Modified',
 '⚠ {kind} — 安全类字段 (控制包络)': '⚠ {kind} — safety-critical field (control envelope)',
 '未映射字段 {n} 项 (yaml 里有、stm32 无处落, 未导入):': 'Unmapped fields: {n} (present in yaml, no destination on stm32, '
                                          'not imported):',
 '离线 — 断开或 500ms 无状态帧; 重连后自动恢复': 'Offline — disconnected or no status frame for 500ms; recovers '
                                 'automatically on reconnect',
 '配置解析失败': 'Config parse failed',
 '[ERR] 调参[导入HYY] {err}': '[ERR] Tuning [Import HYY] {err}',
 '映射失败': 'Mapping failed',
 '导入已取消 —— 摩擦不对称告警': 'Import canceled — friction asymmetry warning',
 '[WARN] 调参[导入HYY] 操作员因摩擦不对称**取消**导入: {joints}': '[WARN] Tuning [Import HYY] Operator **canceled** the '
                                                 'import due to friction asymmetry: {joints}',
 '⚠ 摩擦严重不对称 (操作员已确认继续): {items}': '⚠ Severe friction asymmetry (operator confirmed to continue): {items}',
 '导出失败 — 读回为空 (固件需 27961a1+)': 'Export failed — read-back empty (firmware 27961a1+ required)',
 '刷新失败 — 请检查串口/固件 (读回需固件 27961a1+); 设备参数未确认前禁下发': 'Refresh failed — check serial port/firmware (read-back '
                                                  'requires firmware 27961a1+); writing is blocked until '
                                                  'device parameters are confirmed',
 '已导出到 {path} — 同文件再导入时 diff 应为空': 'Exported to {path} — re-importing the same file should show an empty '
                                   'diff',
 '[OK] 调参[导出] 写 {path}': '[OK] Tuning [Export] wrote {path}',
 '臂已使能 — 写确认': 'Arm enabled — write confirmation',
 '{desc}\n\n机械臂处于 enable 态, 该写入会立即作用于控制律/前馈 (限位墙/积分/摩擦等随写即变)。\n确认继续?': '{desc}\n'
                                                                       '\n'
                                                                       'The robot arm is in enable state; '
                                                                       'this write takes effect immediately '
                                                                       'on the control law/feedforward '
                                                                       '(soft-limit wall, integral, '
                                                                       'friction, etc. change as written).\n'
                                                                       'Continue?',
 '已取消 — enable 态写确认未通过': 'Canceled — enable-state write not confirmed',
 '下发校验未通过': 'Write verification failed',
 '校验未通过: {err}': 'Verification failed: {err}',
 '确认 ff_mask 改动': 'Confirm ff_mask change',
 'ff_mask 将改为 {mask} (0x{mask_hex})\n\n前馈位改动会立即影响控制律输出, 确认下发?': 'ff_mask will change to {mask} '
                                                                '(0x{mask_hex})\n'
                                                                '\n'
                                                                'Feedforward bit changes immediately affect '
                                                                'control law output. Confirm send?',
 '已取消 ff_mask 下发': 'ff_mask write canceled',
 '导入失败': 'Import failed',
 '确认下发后固化 Flash': 'Persist to flash after write',
 '将先下发整套参数到 RAM, 随后调用 param_save 固化到 Flash。\n\n固件要求关节处于 disable 态才会执行擦写 (enable 态返回 ERR 0x04)。\n请确认已先在 [控制] 页 [失能]?': 'The '
                                                                                                                      'full '
                                                                                                                      'parameter '
                                                                                                                      'set '
                                                                                                                      'will '
                                                                                                                      'first '
                                                                                                                      'be '
                                                                                                                      'sent '
                                                                                                                      'to '
                                                                                                                      'RAM, '
                                                                                                                      'then '
                                                                                                                      'param_save '
                                                                                                                      'will '
                                                                                                                      'persist '
                                                                                                                      'it '
                                                                                                                      'to '
                                                                                                                      'flash.\n'
                                                                                                                      '\n'
                                                                                                                      'Firmware '
                                                                                                                      'performs '
                                                                                                                      'the '
                                                                                                                      'erase/write '
                                                                                                                      'only '
                                                                                                                      'with '
                                                                                                                      'joints '
                                                                                                                      'in '
                                                                                                                      'disable '
                                                                                                                      'state '
                                                                                                                      '(enable '
                                                                                                                      'state '
                                                                                                                      'returns '
                                                                                                                      'ERR '
                                                                                                                      '0x04).\n'
                                                                                                                      'Confirm '
                                                                                                                      'you '
                                                                                                                      'have '
                                                                                                                      'already '
                                                                                                                      'pressed '
                                                                                                                      '[Disable] '
                                                                                                                      'on '
                                                                                                                      'the '
                                                                                                                      '[Control] '
                                                                                                                      'page?',
 '已取消固化选项, 仅下发 RAM': 'Persist option canceled — writing to RAM only',
 '固化成功 (已写 Flash)': 'Persist succeeded (written to flash)',
 '已恢复出厂默认 (Flash 参数已失效)': 'Factory defaults restored (flash parameters invalidated)',
 ' —— 设备参数已变更, 请重新 [刷新当前]': ' — device parameters changed; please [Refresh current] again',
 '动力学模型 ({n} 项)': 'Dynamics model ({n} items)',
 'v1 — 误差方向 tanh': 'v1 — error-direction tanh',
 'v2 — SE1 速度方向': 'v2 — SE1 velocity direction',
 'v2-drag — 拖动专用(零速无增益)': 'v2-drag — drag only (no gain at zero speed)',
 '—— 操作员选择**继续**': '— operator chose **continue**',
 '—— 操作员选择取消': '— operator chose cancel',
 '导出写入失败: {err}': 'Export write failed: {err}',
 '[ERR] 调参[导出] {err}': '[ERR] Tuning [Export] {err}',
 '{axis} 分量\n\n{detail}\n\n范围 {range}': '{axis} component\n\n{detail}\n\nRange {range}',
 'J{axis}.{key} 为空 — 请先 [刷新当前]': 'J{axis}.{key} is empty — click [Refresh current] first',
 '成功': 'Succeeded',
 '失败': 'Failed',
 '  · **随后固化到 Flash** (param_save, 须失能, 擦写期间 CPU 停 ~1s)\n': '  · **Then persist to flash** (param_save, '
                                                            'requires disable state, CPU stalls ~1s during '
                                                            'erase/write)\n',
 '  · ⚠ **不会固化到 Flash** —— 本次改动只在 RAM, 掉电即回退\n': '  · ⚠ **Will not persist to flash** — this change stays in '
                                                 'RAM only and reverts on power loss\n',
 '读回失败': 'Read-back failed',
 '❚❚ 冻结': '❚❚ Freeze',
 '清屏': 'Clear',
 '导出 CSV…': 'Export CSV…',
 '导出当前窗口里勾选的关节：时间、q/dq/tau、MOS/线圈温度、驱动错误码。\n冻结状态下导出的是冻结那一刻的窗口。': 'Export the joints checked in the current '
                                                                 'window: time, q/dq/tau, MOS/coil '
                                                                 'temperature, drive error codes.\n'
                                                                 'When frozen, exports the window as of the '
                                                                 'moment of freezing.',
 '关节:': 'Joints:',
 '导出曲线窗口 CSV': 'Export plot window CSV',
 '已写出 {n} 行 → {path}': 'Wrote {n} rows → {path}',
 '▶ 继续': '▶ Resume',
 '导出 CSV': 'Export CSV',
 '当前窗口里没有数据 —— 先连接设备等几帧。': 'No data in the current window — connect the device and wait a few frames first.',
 '请至少勾选一个关节。': 'Select at least one joint.',
 '连接机械臂后显示 3D 模型': '3D model appears after connecting the robot arm',
 '3D 数字孪生': '3D digital twin',
 '等轴': 'Isometric',
 '正视': 'Front',
 '侧视': 'Side',
 '工具': 'Tool',
 '网格': 'Grid',
 '坐标轴': 'Axes',
 '正在加载 3D 模型…': 'Loading 3D model…',
 '只读 · 等待连接': 'Read-only · waiting for connection',
 '已连接 — 等待状态帧': 'Connected — waiting for status frames',
 'FAULT / 急停锁存 — 画面冻结在最后一帧': 'FAULT / emergency stop latched — view frozen on last frame',
 '未连接 — 连接机械臂后显示实时姿态': 'Not connected — connect the robot arm to show live pose',
 '台架 1J — 没有 7 轴 URDF 模型，3D 视图不适用。\n请使用总览/关节页查看 1 轴状态。': 'Bench 1J — no 7-axis URDF model; the 3D view does '
                                                         'not apply.\n'
                                                         'Use the Overview/Joints page to view 1-axis '
                                                         'status.',
 '未找到 3D 模型资产（assets/description）。\n源码运行请确认仓库包含该目录；冻结包请重新打包。': '3D model assets not found '
                                                               '(assets/description).\n'
                                                               'When running from source, make sure the '
                                                               'repository contains that directory; for a '
                                                               'frozen build, repackage.',
 '只读 · {n}J · {k}k 三角形': 'Read-only · {n}J · {k}k triangles',
 '只读 · 在线，准备加载模型': 'Read-only · online, ready to load model',
 '只读 · 离线': 'Read-only · offline',
 '未连接 — 3D 画面冻结在最后一帧': 'Not connected — 3D view frozen on last frame',
 '3D 模型加载失败：{err}': '3D model load failed: {err}',
 '3D 视图初始化失败（OpenGL）：{err}': '3D view initialization failed (OpenGL): {err}',
 '只读 · 台架 1J': 'Read-only · bench 1J',
 '界面语言': 'Interface language',
 '切换后立即生效，并记住这台机器上的选择。\n「跟随系统」= 按桌面语言自动选择；config.yaml 的 language 可改默认。': 'Takes effect immediately after '
                                                                         'switching and is remembered on '
                                                                         'this machine.\n'
                                                                         '"Follow system" = select '
                                                                         'automatically from the desktop '
                                                                         'language; config.yaml language '
                                                                         'sets the default.',
 '语言': 'Language',
 '默认跟随系统：中文桌面显示中文，其余显示英文。除非这里选过，否则以 config.yaml 的 language 为准（auto = 跟随系统）。': 'Follows the system by '
                                                                              'default: a Chinese desktop '
                                                                              'shows Chinese, everything '
                                                                              'else shows English. Unless a '
                                                                              'choice is made here, '
                                                                              'config.yaml language applies '
                                                                              '(auto = follow system).',
 '简体中文': '简体中文',
 '跟随系统': 'Follow system',
 '当前界面语言：{name}（{code}）': 'Current interface language: {name} ({code})',
 '进入零重力拖动': 'Enter zero-G drag',
 '保活周期。固件看门狗超时 0.10s，必须 <0.10 才有余量；\nSDK 默认 0.04s（2.5 倍余量）。': 'Keep-alive period. Firmware watchdog timeout '
                                                              'is 0.10s; it must be <0.10 to leave margin;\n'
                                                              'the SDK default is 0.04s (2.5x margin).',
 '未进入': 'Not engaged',
 '零重力拖动（拖动示教）': 'Zero-G drag (drag teaching)',
 '进入后臂进入重力补偿，可用手自由拖动；松手由虚拟弹簧保持位置。': 'Once engaged, the arm switches to gravity compensation and can be moved '
                                    'freely by hand; on release, a virtual spring holds its position.',
 '⚠ 固件侧靠看门狗保活：SDK 后台线程按上面的周期重发命令，界面卡死/拔线时臂会自动落到 fail-soft 持位，不会失控。': '⚠ Keep-alive relies on the firmware '
                                                                     'watchdog: an SDK background thread '
                                                                     'resends commands at the period above. '
                                                                     'If the UI hangs or the cable is '
                                                                     'pulled, the arm falls back to '
                                                                     'fail-soft hold instead of running '
                                                                     'away.',
 '⚠ 退出前先把关节推回软限位内 —— 零重力会跳过位置越限锁存，但一旦退出该锁存立刻生效，关节停在限外时重启会重新锁死。': '⚠ Push the joints back within soft limits '
                                                                 'before exiting — zero-G skips position '
                                                                 'limit latching, but the latch applies '
                                                                 'immediately on exit; joints left outside '
                                                                 'limits will latch again on restart.',
 '保活期间 SDK 会拒绝其它动作类命令（查询类不受限）；急停/失能永远可达。': 'During keep-alive the SDK rejects other motion commands (queries '
                                           'are unaffected); emergency stop/disable is always available.',
 '保活周期 (s)': 'Keep-alive period (s)',
 '退出零重力拖动': 'Exit zero-G drag',
 '拖动中（保活运行）': 'Dragging (keep-alive running)',
 '⚠ 保活中断: {err}': '⚠ Keep-alive interrupted: {err}',
 '超时保护': 'Timeout protection',
 '断线': 'Disconnected',
 '越限': 'Limit exceeded',
 '超速': 'Overspeed',
 '电机': 'Motor',
 '过温': 'Over-temperature',
 '跟随': 'Following error',
 '非有限': 'Non-finite',
 '模式': 'Mode',
 '臂': 'Arm',
 '丢帧': 'Drops',
 '帧率': 'Frame rate',
 '断轴·{reason}': 'Joint lost · {reason}',
 '已解锁 — 请谨慎操作，急停随时可用': 'Unlocked — operate carefully; emergency stop is always available',
 '已锁定': 'Locked',
 '位置移动 {dpos:.3f} m（阈值 {pos_threshold}）\n姿态变化 {drot:.3f} rad（阈值 {rot_threshold}）': 'Position change '
                                                                                   '{dpos:.3f} m (threshold '
                                                                                   '{pos_threshold})\n'
                                                                                   'Orientation change '
                                                                                   '{drot:.3f} rad '
                                                                                   '(threshold '
                                                                                   '{rot_threshold})',
 'current({a}) 与 targets({b}) 关节数不一致': 'current({a}) and targets({b}) have different joint counts',
 '{joint}: 当前 {cur:.3f} → 目标 {target:.3f}（Δ {delta:.3f} rad）': '{joint}: current {cur:.3f} → target '
                                                               '{target:.3f} (Δ {delta:.3f} rad)',
 '⚠ 拿不到当前末端位姿，无法比较幅度。\n目标：{target}\n（建议先 [读取当前末端位姿] 再下发）': '⚠ Cannot get current end-effector pose; cannot '
                                                           'compare magnitude.\n'
                                                           'Target: {target}\n'
                                                           '(Suggest [Read current end-effector pose] before '
                                                           'sending)',
 '{name} 失败 [{code}]: {title}': '{name} failed [{code}]: {title}',
 '{name} 完成': '{name} complete',
 'litearm.Arm 上找不到 _a._on_status 状态钩子缝隙 —— SDK 内部结构变了。本工具依赖它把运动期间的 100Hz 状态也画到曲线上；请更新 litetool/sdk_worker.py::_attach_state_hook 以适配新版 SDK。': 'Cannot '
                                                                                                                                              'find '
                                                                                                                                              'the '
                                                                                                                                              '_a._on_status '
                                                                                                                                              'state '
                                                                                                                                              'hook '
                                                                                                                                              'seam '
                                                                                                                                              'on '
                                                                                                                                              'litearm.Arm '
                                                                                                                                              '—— '
                                                                                                                                              'the '
                                                                                                                                              'SDK '
                                                                                                                                              'internals '
                                                                                                                                              'have '
                                                                                                                                              'changed. '
                                                                                                                                              'This '
                                                                                                                                              'tool '
                                                                                                                                              'depends '
                                                                                                                                              'on '
                                                                                                                                              'it '
                                                                                                                                              'to '
                                                                                                                                              'plot '
                                                                                                                                              'the '
                                                                                                                                              '100Hz '
                                                                                                                                              'state '
                                                                                                                                              'during '
                                                                                                                                              'motion '
                                                                                                                                              'on '
                                                                                                                                              'the '
                                                                                                                                              'curve; '
                                                                                                                                              'update '
                                                                                                                                              'litetool/sdk_worker.py::_attach_state_hook '
                                                                                                                                              'to '
                                                                                                                                              'adapt '
                                                                                                                                              'to '
                                                                                                                                              'the '
                                                                                                                                              'new '
                                                                                                                                              'SDK.',
 '自动': 'Auto',
 '已连接 {port} · {fw}': 'Connected {port} · {fw}',
 '[OK] 已连接 {port} · 固件 {fw} · N={n}': '[OK] Connected {port} · firmware {fw} · N={n}',
 '急停帧已发出': 'Emergency stop frame sent',
 '接管 movej 帧已发出': 'Takeover movej frame sent',
 '[ERR] 离线: {why}': '[ERR] Offline: {why}',
 '还没有状态帧，无法取当前关节角': 'No state frame yet; cannot read current joint angles',
 '[WARN] 断线：已丢弃 {n} 条排队中的命令': '[WARN] Disconnected: dropped {n} queued commands',
 '[WARN] 关闭时所有者线程仍在执行任务（阻塞调用不可抢占），已直接释放串口': '[WARN] Owner thread was still executing a task on close '
                                            '(blocking calls cannot be preempted); serial port released '
                                            'directly',
 '需要 {n} 个关节角，收到 {got} 个': 'Expected {n} joint angles, got {got}',
 'speed 需 0..1': 'speed must be 0..1',
 '[WARN] 重连时串口枚举失败: {err}': '[WARN] Serial port enumeration failed during reconnect: {err}',
 '正在自动重连（第 {n} 次）…': 'Auto-reconnecting (attempt {n})…',
 '[OK] 已重连 {port} · 固件 {fw} · N={n}': '[OK] Reconnected {port} · firmware {fw} · N={n}',
 '已重连 {port} · {fw}': 'Reconnected {port} · {fw}',
 '[WARN] 关闭链路出错: {err}': '[WARN] Error closing link: {err}',
 '任务已被丢弃（{reason}）': 'Task dropped ({reason})',
 '[WARN] 状态读取被固件拒绝: {err}': '[WARN] Status read rejected by firmware: {err}',
 '链路异常: {err}': 'Link error: {err}',
 '未预期异常: {err}': 'Unexpected exception: {err}',
 '状态流静默 >{timeout:.1f}s': 'State stream silent >{timeout:.1f}s',
 '[WARN] 重连 {port} 失败: {err}': '[WARN] Reconnect to {port} failed: {err}',
 '[WARN] 第 {n} 次重连失败：{count} 个端口均无响应（{port}: {err}）': '[WARN] Reconnect attempt {n} failed: no response on {count} port(s) ({port}: {err})',
 '激活服务返回 HTTP {status}': 'Activation service returned HTTP {status}',
 '{field} 必须是十六进制字符串': '{field} must be a hex string',
 '{field} 需 {want} 位十六进制，给的是 {got} 位': '{field} must be {want} hex digits, got {got}',
 '{field} 必须是整数': '{field} must be an integer',
 '{field} 超出 u32 范围: {value}': '{field} is out of u32 range: {value}',
 '凭据文件的内容不是一个 JSON 对象': 'Credential file does not contain a JSON object',
 '凭据文件缺少 format 字段': 'Credential file is missing the format field',
 '凭据格式为 {fmt}，当前上位机只认 {want}（请升级上位机）': 'Credential format is {fmt}, but this host tool only supports {want} '
                                       '(please upgrade the host tool)',
 '这份凭据是给 {uid} 的，当前这台机器是 {actual}': 'This credential is for {uid}, but this machine is {actual}',
 'flags 只允许 bit0，给的是 0x{flags:X}': 'flags allows only bit0, got 0x{flags:X}',
 '字段 phone 格式不正确：需为 11 位手机号': 'Field phone is invalid: must be an 11-digit mobile number',
 '字段 email 格式不正确：例如 name@example.com': 'Field email is invalid: e.g. name@example.com',
 '字段 name 格式不正确：只允许文字（2-32 字），不能含数字': 'Field name is invalid: letters only (2-32 characters), no digits',
 '设备 UID 需为 24 位十六进制': 'Device UID must be 24 hex digits',
 '未同意《激活注册信息同意书》—— 请先阅读并同意': 'Activation Registration Consent not accepted —— please read and accept it '
                             'first',
 '缺少注册信息': 'Missing registration information',
 '[activation] 内部通道令牌只在 HTTPS 上发送；本次按正式请求发送': '[activation] Internal-channel token is only sent over HTTPS; '
                                              'sending as a regular request this time',
 '未配置激活服务地址 —— 请用 --activation-url 指定': 'Activation service URL not configured —— specify it with '
                                        '--activation-url',
 '{field} 含非十六进制字符': '{field} contains non-hex characters',
 '凭据文件缺少 {field} 字段': 'Credential file is missing the {field} field',
 '字段 {field} 必须是文本': 'Field {field} must be text',
 '缺少字段 {field}': 'Missing field {field}',
 '字段 {field} 过长（上限 {max} 字）': 'Field {field} is too long (max {max} characters)',
 '字段 {field} 至少 {min} 字': 'Field {field} must be at least {min} characters',
 '连不上激活服务: {detail}': 'Cannot reach activation service: {detail}',
 '激活服务返回的不是合法 JSON': 'Activation service returned invalid JSON',
 '激活服务返回的凭据不可用: {detail}': 'Credential returned by activation service is unusable: {detail}',
 '这不是一份凭据文件（不是 JSON）': 'This is not a credential file (not JSON)',
 '{name} 失败: {err}': '{name} failed: {err}',
 'LiteGrip 仅支持 Linux（SocketCAN）': 'LiteGrip supports Linux only (SocketCAN)',
 '[OK] 夹爪已连接 {channel} CAN ID=0x{can_id:02X}': '[OK] Gripper connected {channel} CAN ID=0x{can_id:02X}',
 '停止/释放': 'Stop/Release',
 ' · 已失能并中止在途动作': ' · disabled and aborted in-flight motion',
 ' · 已丢弃 {n} 条排队任务': ' · dropped {n} queued tasks',
 '停止': 'Stop',
 '夹爪使能': 'Gripper enable',
 '夹爪失能': 'Gripper disable',
 '夹爪张开': 'Gripper open',
 '夹爪闭合': 'Gripper close',
 '夹爪抓取 {force}N/{hold}s': 'Gripper grasp {force}N/{hold}s',
 '夹爪写零（不可逆）': 'Gripper zero write (irreversible)',
 '夹爪两端标定': 'Gripper two-end calibration',
 '保存标定': 'Save calibration',
 '加载标定': 'Load calibration',
 '刷新夹爪状态': 'Refresh gripper status',
 '[ERR] 夹爪离线: {why}': '[ERR] Gripper offline: {why}',
 '未安装 litegrip-python: {err}': 'litegrip-python not installed: {err}',
 '夹爪已连接 {channel}（{fw}）': 'Gripper connected {channel} ({fw})',
 '夹爪已连接 {channel}': 'Gripper connected {channel}',
 '夹爪已断开': 'Gripper disconnected',
 '夹爪未连接': 'Gripper not connected',
 '夹爪不可用 — {why}。连接按钮已禁用。': 'Gripper unavailable — {why}. The connect button is disabled.',
 '不可用：{why}': 'Unavailable: {why}',
 '零力矩帧已发出': 'Zero-torque frame sent',
 '[WARN] 夹爪断开出错: {err}': '[WARN] Error disconnecting gripper: {err}',
 '零力矩帧已发出，但失能失败（在途动作可能继续）: {err}': 'Zero-torque frame sent, but disable failed (in-flight motion may '
                                   'continue): {err}',
 '[WARN] 夹爪状态读取失败: {err}': '[WARN] Gripper status read failed: {err}',
 '已按停止/释放中止{detail}': 'Aborted via Stop/Release{detail}',
 '固件无此命令（未实现）': 'Firmware does not support this command (not implemented)',
 '载荷过短（参数校验不通过，未执行）': 'Payload too short (parameter validation failed, not executed)',
 '数值非法（NaN/超限），固件已拒绝': 'Invalid value (NaN/out of range); firmware rejected it',
 '未就绪/未使能（反馈未齐可重试；运动命令需先 enable）': 'Not ready/not enabled (retry once feedback is complete; motion commands '
                                   'need enable first)',
 '需先 disable（先失磁再做此操作）': 'Must disable first (de-energize before this operation)',
 '忙（上一条命令/IK 求解仍在执行）': 'Busy (previous command or IK solve still running)',
 '锁存中，须先 reset 复位（EMERGENCY/单轴故障，重试无效）': 'Latched; reset first (EMERGENCY/single-axis fault, retrying is '
                                         'ineffective)',
 '掩码不符（本会话漏写或写错了 body）': 'Mask mismatch (body missing or wrong in this session)',
 '超时/无应答': 'Timeout/no response',
 'get_ff_vec item 1 读回被拒: {err}': 'get_ff_vec item 1 read-back rejected: {err}',
 '参数读回无应答 (get_ff_vec item 1): {err}': 'No response to parameter read-back (get_ff_vec item 1): {err}',
 'get_ff_scalar item 1 读回被拒: {err}': 'get_ff_scalar item 1 read-back rejected: {err}',
 '参数读回无应答 (get_ff_scalar item 1): {err}': 'No response to parameter read-back (get_ff_scalar item 1): {err}',
 'ff_mask 读回失败 (get_ff_mask): {err}': 'ff_mask read-back failed (get_ff_mask): {err}',
 '固件不支持参数读回 (0x2B) —— 需更新固件': 'Firmware does not support parameter read-back (0x2B) —— update the firmware',
 'get_ff_vec item {item} 读回被拒: {err}': 'get_ff_vec item {item} read-back rejected: {err}',
 'get_ff_vec item {item} 读回失败: {err}': 'get_ff_vec item {item} read-back failed: {err}',
 '固件不支持参数读回 (0x2C) —— 需更新固件': 'Firmware does not support parameter read-back (0x2C) —— update the firmware',
 'get_ff_scalar item {item} 读回被拒: {err}': 'get_ff_scalar item {item} read-back rejected: {err}',
 'get_ff_scalar item {item} 读回失败: {err}': 'get_ff_scalar item {item} read-back failed: {err}',
 'J{axis} 读回失败 (get_joint_param): {err}': 'J{axis} read-back failed (get_joint_param): {err}',
 '{key} 读回失败 (get_ff_scalar): {err}': '{key} read-back failed (get_ff_scalar): {err}',
 '模型 jm 长度 {got} != {want}': 'Model jm length {got} != {want}',
 '模型 body 须为 {n} 个, 实际 {got}': 'Model body must have {n} entries, got {got}',
 'jm 须为 {n} 个, 实际 {got}': 'jm must have {n} entries, got {got}',
 '载荷过短': 'Payload too short',
 '数值非法（NaN/超限/零模型），固件已拒绝': 'Invalid value (NaN/out of range/zero model); firmware rejected it',
 '需先失能（模型 commit/回退要求失能态）': 'Must disable first (model commit/rollback requires disabled state)',
 '忙（flash 正在擦写）': 'Busy (flash is being erased/written)',
 '模型 body{i} 长度 {got} != {want}': 'Model body{i} length {got} != {want}',
 '模型 jm 读回失败: {err}': 'Model jm read-back failed: {err}',
 '模型状态读回失败: {err}': 'Model status read-back failed: {err}',
 ' 参数个数 ': ' parameter count ',
 'body{i} 写入被拒': 'body{i} write rejected',
 'jm 个数 ': 'jm count ',
 'jm 写入被拒': 'jm write rejected',
 'body{i} 须为 {n} 个, 实际 {got}': 'body{i} must have {n} values, got {got}',
 'body{i} 是 ee 固定体 (payload 复合位), 质量必须为 0, 实际 {value}': 'body{i} is the fixed ee body (payload composite), '
                                                        'mass must be 0, got {value}',
 '模型 body{i} 读回失败: {err}': 'Model body{i} read-back failed: {err}',
 'body{i}.{key} = {value} 非有限或超出 ±{limit:g}': 'body{i}.{key} = {value} is not finite or exceeds ±{limit:g}',
 'jm.J{axis} = {value} 非有限或超出 ±{limit:g}': 'jm.J{axis} = {value} is not finite or exceeds ±{limit:g}',
 '无 CDC 写口 (编译期常量)': 'No CDC write port (compile-time constant)',
 '连杆几何, 同型号恒定, 本设计不改': 'Link geometry, constant for a given model, not changed by this design',
 '非运行时参数': 'Not a runtime parameter',
 '轴配置 (方向/编码器/减速比), 编译期常量': 'Axis configuration (direction/encoder/gear ratio), compile-time constant',
 'HYY 控制器配置, 非辨识产物 (本机用自身口径) ': 'HYY controller configuration, not an identification result (this unit uses '
                                'its own values) ',
 '检测到 <b>{n}</b> 个关节的<b>正、反方向库仑摩擦严重不对称</b><br>判据: 比值 &gt; {ratio:g} 且差值 ≥ {delta:g} Nm': 'Detected <b>severe '
                                                                                         'Coulomb friction '
                                                                                         'asymmetry between '
                                                                                         'forward and '
                                                                                         'reverse '
                                                                                         'directions</b> on '
                                                                                         '<b>{n}</b> '
                                                                                         'joints<br>Criterion: '
                                                                                         'ratio &gt; '
                                                                                         '{ratio:g} and '
                                                                                         'difference ≥ '
                                                                                         '{delta:g} Nm',
 '顶层': 'Top level',
 '{where} 缺字段 `{key}`': '{where} is missing field `{key}`',
 '{where}.{key} 须为数值, 实际 {value}': '{where}.{key} must be numeric, got {value}',
 '{where}.{key} 非有限 ({value})': '{where}.{key} is not finite ({value})',
 'yaml 顶层须为对象': 'yaml top level must be an object',
 'robot_group.robot 须为非空数组': 'robot_group.robot must be a non-empty array',
 'robot[0].joint 须为长度 {n} 的数组 (J1..J7, 顺序即关节号), 实际 {got}': 'robot[0].joint must be an array of length {n} '
                                                           '(J1..J7, order is joint number), got {got}',
 'robot[0].gravity 模长 {mag:.3f} < 1.0 m/s² —— 非法': 'robot[0].gravity magnitude {mag:.3f} < 1.0 m/s² — '
                                                   'invalid',
 '{where}.{key} 不在参数目录中 (既非关节项也非全局项)': '{where}.{key} is not in the parameter catalog (neither a joint entry '
                                       'nor a global entry)',
 '尚无设备基线 —— 请先点 [刷新当前] 再导入 (导入需要基线补齐未映射字段)': 'No device baseline yet — click [Refresh Current] before '
                                             'importing (import uses the baseline to fill unmapped fields)',
 '&nbsp;&nbsp;J{joint}:&nbsp; |fc0| = <b>{a:.3f}</b> Nm , |fc1| = <b>{b:.3f}</b> Nm<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;比值 <b>{ratio}</b> , 差值 {delta:.3f} Nm': '&nbsp;&nbsp;J{joint}:&nbsp; '
                                                                                                                                                                               '|fc0| '
                                                                                                                                                                               '= '
                                                                                                                                                                               '<b>{a:.3f}</b> '
                                                                                                                                                                               'Nm, '
                                                                                                                                                                               '|fc1| '
                                                                                                                                                                               '= '
                                                                                                                                                                               '<b>{b:.3f}</b> '
                                                                                                                                                                               'Nm<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ratio '
                                                                                                                                                                               '<b>{ratio}</b>, '
                                                                                                                                                                               'difference '
                                                                                                                                                                               '{delta:.3f} '
                                                                                                                                                                               'Nm',
 '读取/解析 yaml 失败: {err}': 'Failed to read/parse yaml: {err}',
 '{where} 须为对象': '{where} must be an object',
 '{where}: axis.id={jid} 与数组下标 {i} 不一致 —— 顺序即关节号, 拒绝导入': '{where}: axis.id={jid} does not match array index '
                                                         '{i} — order is the joint number; import refused',
 '{where}.axis: smin({lo}) 须 < smax({hi})': '{where}.axis: smin({lo}) must be < smax({hi})',
 '{where}.{key} 在设备基线上为空 —— 台架上 J2..J7 无读回值。导入需要整臂基线': '{where}.{key} is empty in the device baseline — '
                                                       'J2..J7 have no read-back values on this bench. '
                                                       'Import requires a full-arm baseline',
 '未登记 —— 需裁决': 'Not registered — decision needed',
 '{name} · {size} B · 版本 {version} · sha256 {sha}': '{name} · {size} B · version {version} · sha256 {sha}',
 '镜像版本 {expected}, 但设备复位后报 {version} —— 烧录本身已通过读回校验, 请核对这份镜像是否选错': 'Image version {expected}, but the device '
                                                                   'reports {version} after reset — the '
                                                                   'flash itself passed read-back '
                                                                   'verification; check whether the wrong '
                                                                   'image was selected',
 '完成 · 设备报版本 {version}': 'Done · device reports version {version}',
 '升级完成并通过读回校验': 'Upgrade complete; read-back verification passed',
 '已取消（尚未开始）': 'Cancelled (not started)',
 '开始烧录': 'Starting flash',
 '等待串口重新枚举并重建会话': 'Waiting for the serial port to re-enumerate and the session to rebuild',
 '失败后复位回应用 ...': 'Resetting back to application after failure ...',
 '失能全部关节': 'Disabling all joints',
 '发送 CMD_ENTER_DFU (0x15)': 'Sending CMD_ENTER_DFU (0x15)',
 '打开 DFU 设备 (0483:DF11)': 'Opening DFU device (0483:DF11)',
 '等待 DFU 设备 (0483:DF11) 枚举': 'Waiting for DFU device (0483:DF11) to enumerate',
 '复位回应用（烧录已完成, 取消不再生效）': 'Resetting back to application (flash complete; cancel no longer applies)',
 '复位回应用也失败 ({detail}) —— 板子可能停在 bootloader, 断电重上电即可': 'Reset back to application also failed ({detail}) — '
                                                      'the board may be stuck in the bootloader; power-cycle '
                                                      'it',
 '机械臂在 {timeout:.0f}s 内没有失能 —— 不冒险进入 DFU (跳转会停 TIM3, 电机 100ms 松开, 有重力负载会下垂)': 'Robot arm did not disable '
                                                                              'within {timeout:.0f}s — not '
                                                                              'risking DFU entry (the jump '
                                                                              'stops TIM3, motors release in '
                                                                              '100ms, and joints will sag '
                                                                              'under gravity)',
 '等 {timeout:.0f}s 没等到 DFU 设备 (0483:DF11) —— 检查 USB 线; Windows 上还需要 ST 的 WinUSB 驱动': 'No DFU device '
                                                                                     '(0483:DF11) appeared '
                                                                                     'within {timeout:.0f}s '
                                                                                     '— check the USB cable; '
                                                                                     'on Windows you also '
                                                                                     "need ST's WinUSB "
                                                                                     'driver',
 '固件已写入并通过读回校验, 但 {window:.0f}s 内没能重新连上 ({attempts} 次): {last} —— 断电重上电即可': 'Firmware written and passed '
                                                                            'read-back verification, but '
                                                                            'could not reconnect within '
                                                                            '{window:.0f}s ({attempts} '
                                                                            'attempts): {last} — power-cycle '
                                                                            'the board',
 '机械臂未连接 —— 请先连接设备': 'Robot arm not connected — connect the device first',
 '进入 DFU': 'Enter DFU',
 'DFU 设备在, 但当前用户打不开它 (打开时报 Access denied)。Linux 上需要一条 udev 规则：SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="df11", MODE="0666"': 'DFU '
                                                                                                                                               'device '
                                                                                                                                               'is '
                                                                                                                                               'present, '
                                                                                                                                               'but '
                                                                                                                                               'the '
                                                                                                                                               'current '
                                                                                                                                               'user '
                                                                                                                                               'cannot '
                                                                                                                                               'open '
                                                                                                                                               'it '
                                                                                                                                               '(Access '
                                                                                                                                               'denied '
                                                                                                                                               'on '
                                                                                                                                               'open). '
                                                                                                                                               'On '
                                                                                                                                               'Linux '
                                                                                                                                               'a '
                                                                                                                                               'udev '
                                                                                                                                               'rule '
                                                                                                                                               'is '
                                                                                                                                               'required: '
                                                                                                                                               'SUBSYSTEM=="usb", '
                                                                                                                                               'ATTR{idVendor}=="0483", '
                                                                                                                                               'ATTR{idProduct}=="df11", '
                                                                                                                                               'MODE="0666"',
 '没有可用的 DFU 设备': 'No usable DFU device',
 '{name} 超时': '{name} timed out',
 '{name} 没有结果': '{name} returned no result',
 '没有检测到处于 DFU (0483:DF11) 的板子 —— 它可能刚被拔掉, 或已经复位回应用态': 'No board detected in DFU mode (0483:DF11) — it may '
                                                      'have just been unplugged, or already reset back to '
                                                      'the application',
 '失能失败: {err}': 'Disable failed: {err}',
 '已取消': 'Cancelled',
 '已取消 (镜像已写入)': 'Cancelled (image already written)',
 '[WARN] 关闭串口失败: {err}': '[WARN] Failed to close serial port: {err}',
 '无法枚举 USB 设备: {detail}': 'Cannot enumerate USB devices: {detail}',
 '没有解析到任何数据记录': 'No data records found',
 'BIN 文件为空': 'BIN file is empty',
 '镜像里有 {n} 个不同版本串: {hits}': 'Image contains {n} different version strings: {hits}',
 '烧录基址 0x': 'Flash base address 0x',
 ' 未对齐到 ': ' is not aligned to ',
 'BIN 长度 ': 'BIN length ',
 ' B 超出 Flash 上界 0x': ' B exceeds flash upper bound 0x',
 ' (从 0x': ' (space available from 0x',
 ' 起可用 ': ', ',
 '镜像里未找到 Litearm* 版本串 (固件过旧? 版本宏被改过?)': 'No Litearm* version string found in the image (firmware too old? '
                                        'version macro changed?)',
 '镜像起始地址 0x': 'Image start address 0x',
 ' 不是应用基址 0x': ' is not the application base address 0x',
 ' —— 应用只能烧到 0x': ' — the application can only be flashed to 0x',
 '镜像结束地址 0x': 'Image end address 0x',
 ' 超出 Flash 上界 0x': ' exceeds flash upper bound 0x',
 ' (共 ': ' (total ',
 '镜像覆盖受保护扇区 0x': 'Image covers protected sector 0x',
 ' —— 扇区 6 是许可证 (magic LTC1), 扇区 7 是出厂标定 (magic LTP1), 两者只存在于设备上, 擦掉不可恢复。这份镜像不能用。': ' — sector 6 is the '
                                                                                    'license (magic LTC1), '
                                                                                    'sector 7 is the factory '
                                                                                    'calibration (magic '
                                                                                    'LTP1); both exist only '
                                                                                    'on the device and '
                                                                                    'cannot be recovered '
                                                                                    'once erased. This image '
                                                                                    'cannot be used.',
 '第 ': 'Line ',
 " 行不以 ':' 开头": " does not start with ':'",
 ' 行过短': ' is too short',
 ' 行校验和错误': ' has a checksum error',
 ' 行长度字段与实际不符': ' has a length field that does not match the data',
 ' 行含非十六进制字符: ': ' contains non-hex characters: ',
 '不是 Intel HEX 文本（也不是 .bin）: ': 'Not Intel HEX text (and not .bin): ',
 '（这份文件既不是合法 HEX，也不是 .bin）': ' (this file is neither valid HEX nor .bin)',
 ' 行: 地址 0x': ': address 0x',
 ' 重复定义': ' is defined more than once',
 ' 行: 未知记录类型 0x': ': unknown record type 0x',
 '假件 (--fake / 测试)': 'Fake (--fake / test)',
 '假件: 读回校验失败 (首个不一致处 0x08000100)': 'Fake: read-back verification failed (first mismatch at 0x08000100)',
 '✓ 读回校验通过 (': '✓ Read-back verification passed (',
 ' B 逐字节一致, 假件)': ' B matched byte-for-byte, fake)',
 '写入 ': 'Writing ',
 ' B (假件)': ' B (fake)',
 '✔ LiteArm STM32（板载 CDC）— {desc}': '✔ LiteArm STM32 (onboard CDC) — {desc}',
 '{dev}（系统串口，非 USB）': '{dev} (system serial port, not USB)',
 'USB 串口': 'USB serial port',
 '{name} 有 {rows} 行，时间轴有 {n} 行 —— 拒绝导出错位数据': '{name} has {rows} rows but the timeline has {n} rows — '
                                             'refusing to export misaligned data',
 '曲线窗口里没有数据 —— 连接后等几帧再导出': 'No data in the plot window — connect, wait a few frames, then export',
 'joint_fault 有 {rows} 行，时间轴有 {n} 行': 'joint_fault has {rows} rows, timeline has {n} rows',
 '还没有读回采集数据 —— 先 [读回并预览] 再导出': 'No captured data read back yet — use [Read Back & Preview] before exporting',
 '控制频率必须为正: {hz}': 'Control frequency must be positive: {hz}',
 '{name} 第 {row} 行有 {got} 列，期望 {want} —— 拒绝导出错位数据': '{name} row {row} has {got} columns, expected {want} — '
                                                    'refusing to export misaligned data',
 '关节索引 {j} 超出 0..{last}': 'Joint index {j} out of range 0..{last}',
 '第 {i} 拍各字段轴数不一致 —— 拒绝导出错位数据': 'Frame {i} has inconsistent axis counts across fields — refusing to export '
                                'misaligned data',
 '[activation] --activation-url 缺少值；使用默认地址': '[activation] --activation-url is missing a value; using the '
                                             'default address',
 '[lang] 不认识的 --lang=': '[lang] unrecognized --lang=',
 '；支持 zh / en': '; supported: zh / en',
 'LiteArm Tool 已在运行，已切换到已有窗口。': 'LiteArm Tool is already running; switched to the existing window.',
 '已有实例在运行，已为你切换到该窗口。\n同一时间只允许一个上位机占用串口。': 'An instance is already running; switched you to that window.\n'
                                          'Only one host tool may hold the serial port at a time.',
 '[WARN] 单实例锁不可用: {why}': '[WARN] Single-instance lock unavailable: {why}',
 '锁文件不可用': 'Lock file unavailable',
 '未知错误': 'Unknown error',
 '设备已使能 —— 请先失能，再提交激活': 'Device is enabled — disable it before submitting activation',
 '[lang] --lang 缺少值；使用配置/系统语言': '[lang] --lang has no value; using the configured/system language',
 '未解析': 'unresolved',
 'pyusb 自带 libusb': 'pyusb bundled libusb',
 '设置地址指针 (擦除前) ...': 'setting address pointer (before erase) ...',
 '设置地址指针 (写数据前) ...': 'setting address pointer (before writing) ...',
 '擦除扇区 {k} (@0x{addr:08X}) ...': 'erasing sector {k} (@0x{addr:08X}) ...',
 '写入 {off}/{total} B (块 {block}) ...': 'writing {off}/{total} B (block {block}) ...',
 '结束 (manifest) ...': 'finishing (manifest) ...',
 '读回校验 ...': 'read-back verification ...',
 '擦除扇区 0x{addr:08X} 耗时 {busy:.2f} s ✓ (忙时长下界通过; 本机无 UPLOAD, 无法再读回复核)': 'erased sector 0x{addr:08X} in '
                                                                       '{busy:.2f} s ✓ (busy-time lower '
                                                                       'bound passed; no UPLOAD on this '
                                                                       'device, cannot read back to '
                                                                       're-check)',
 '擦除扇区 0x{addr:08X} 耗时 {busy:.2f} s, 读回复核全 0xFF ✓': 'erased sector 0x{addr:08X} in {busy:.2f} s; read-back '
                                                    'is all 0xFF ✓',
 '未安装 pyusb (pip install pyusb)': 'pyusb is not installed (pip install pyusb)',
 '找不到 libusb 后端 (pip install libusb-package)': 'no libusb backend found (pip install libusb-package)',
 '✓ 读回校验通过 ({n} B 逐字节一致, 假件)': '✓ read-back verified ({n} B byte-for-byte, fake device)',
 '写入 {n} B (假件)': 'wrote {n} B (fake device)',
 '{label}  (x, y, z)': '{label}  (x, y, z)',
 '值': 'value',
 '② 安装姿态与向量（{unit}）': '② Mounting orientation and vector ({unit})',
 '[lang] 不认识的 --lang={value}；支持 zh / en': '[lang] unknown --lang={value}; supported values are zh / en',
 '写入 {done}/{total} B (假件)': 'wrote {done}/{total} B (fake device)',
 'body{i} 参数个数 {got} != {want}': 'body{i} parameter count {got} != {want}',
 'jm 个数 {got} != {want}': 'jm count {got} != {want}',
 '已失能': 'Disabled',
 '已连接 — 参数已读取，可编辑/下发': 'Connected — parameters loaded; editing/sending enabled',
 '已读回 {n} 拍': 'Read back {n} ticks',
 '录制中…': 'Recording…'}

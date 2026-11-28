"""English metadata for parameter catalog (generated translation).

Source: litetool/param_catalog.py. Keys match parameter `key` fields.
"""

LABELS = {'kp': 'kp stiffness',
 'kd': 'kd damping',
 'tau_max': 'tau_max torque clamp',
 'q_min': 'q_min soft-limit lower bound',
 'q_max': 'q_max soft-limit upper bound',
 'friction': 'friction Coulomb friction (v1)',
 'ki': 'ki integral gain',
 'i_max': 'i_max integral clamp',
 'wall_stiff': 'wall_stiff limit-wall stiffness',
 'wall_damp': 'wall_damp limit-wall damping',
 'wall_tau_max': 'wall_tau_max wall-force clamp',
 'gravity_scale': 'gs gravity scale',
 'inertia_scale': 'is inertia scale',
 'friction_v': 'friction_v viscous (v2)',
 'friction_fc0': 'friction_fc0 positive Coulomb (v2)',
 'friction_fc1': 'friction_fc1 negative Coulomb (v2)',
 'kd_extra': 'kd_extra τ-domain software damping',
 'drag_gain': 'drag_gain drag-compensation ratio',
 'fric_db': 'Friction deadband fric_db',
 'wall_margin': 'Limit wall lead angle',
 'friction_slew': 'Friction slew limit',
 'payload_mass': 'Payload mass',
 'payload_com': 'Payload center of mass com',
 'gravity': 'Gravity vector g',
 'friction_model': 'Friction model',
 'fric_v2_eps': 'v2 tanh smoothing bandwidth',
 'drag_db': 'Drag Coulomb deadband bandwidth',
 'wall_fw_kd': 'Firmware kd added in wall zone',
 'hold_kp_gain': 'On-target stiffness multiplier'}

META = {'kp': ('MIT position stiffness (the P term of PD)',
        'Responsiveness/anti-sag knob: larger -> tighter and less sag; too large -> prone to '
        'vibration/whine. Upper limit 500; raise in small per-axis steps before the oscillation '
        "point (see symptom table 'sags at target / holds soft').",
        'Meaning: the MIT-control position stiffness kp, with PD_j=kp·(q_d−q)+kd·(q̇_d−q̇) '
        'executed inside the motor. Unit Nm/rad, range [0,500]. Typical values by motor: 6248 axis '
        '360~420, 4340 axis 220, 4310 forearm 50. Larger -> tighter tracking and less '
        'sag/residual; too large -> that axis jitters/whines/oscillates (stop before the '
        'oscillation point). Common misuse: changing all axes at once (start with the load-bearing '
        'large axes and try small steps), or mistaking saturation for insufficient stiffness.'),
 'kd': ('MIT damping (the D term of PD)',
        'Suppresses oscillation/recoil: jitter, whine, recoil at target -> raise kd (≤5). Too '
        'large -> stiff and amplifies high-frequency noise.',
        'Meaning: the MIT-control damping kd, which damps the velocity error (q̇_d−q̇). Unit '
        'Nm·s/rad, range [0,5]. Typical values 2.5 (forearm)~5 (upper arm). Jitter/whine/recoil at '
        'target -> add kd first (≤5), together with lowering kp. Too large -> the axis feels '
        'stiff, lags behind, and amplifies measurement noise. Common misuse: using kd to force '
        'down vibration caused by kp (lower kp at the same time).'),
 'tau_max': ('Per-axis torque clamp (safety ceiling)',
             "Absolute ± limit on this axis's commanded torque. Constantly pinned at ±tau_max "
             'means saturation: lower the velocity envelope / reduce load, do not add kp (see '
             "symptom table 'tau constantly at ±tau_max').",
             "Meaning: the absolute clamp on this axis's commanded torque; the final formula is "
             'τ=clamp(τ,±tau_max). Unit Nm, range [0.1,120]; motor models have hardware limits '
             '(6248->120, 4340->28, 4310->10). If τ constantly sits at ±tau_max the axis is '
             'saturated: lower the velocity envelope or reduce the load first; adding kp only '
             "makes it more aggressive. Common misuse: raising tau_max above the motor's hardware "
             'torque in order to suppress saturation.'),
 'q_min': ('Soft-limit lower bound (rad)',
           'Lower angle bound; exceeding it triggers POS_VIOL/FAULT. Before changing it, make sure '
           'the current q is still inside the new limit.',
           'Meaning: the minimum allowed angle of this joint (soft limit, rad). Range [-15,15]; '
           'q_min<q_max is required. Motion past it triggers POS_VIOL/FAULT. The factory value is '
           'the URDF hard limit inset by about 1°. Before applying, the GUI checks whether the '
           'current q is inside the new limit; making it too large may leave the arm unable to '
           'reach its original working point.'),
 'q_max': ('Soft-limit upper bound (rad)',
           'Upper angle bound; exceeding it triggers POS_VIOL/FAULT. Before changing it, make sure '
           'the current q is still inside the new limit.',
           'Meaning: the maximum allowed angle of this joint (soft limit, rad). Range [-15,15]; '
           "q_min<q_max is required. Motion past it triggers POS_VIOL/FAULT. Note that J4's upper "
           'bound is near 0 (asymmetric limit). Common misuse: widening the limit to get around '
           'over-limit alarms — what should really be checked is the motion target/velocity '
           'envelope.'),
 'friction': ('Coulomb friction feedforward v1 (error direction)',
              'Only effective with friction_model=0: friction·tanh(e/fric_db). Keep at 0 while v2 '
              '(factory default) is enabled.',
              'Meaning: v1 friction feedforward magnitude, output along the position-error '
              'direction as friction·tanh(e/fric_db) (when friction_model=0). Unit Nm, range '
              '[0,50]. Factory value 0 (v2 friction has taken over). If switching back to v1 '
              'manually, the value roughly equals the torque needed to start this axis plus '
              'margin. Common misuse: editing the friction column while v2 is enabled by default '
              '(it has no effect).'),
 'ki': ('Integral gain (removes steady-state residual)',
        'Steady-state residual/sag at target -> raise ki; too large -> oscillation/overshoot. The '
        'output is clamped by i_max; the firmware auto-clears the integral at motion start.',
        'Meaning: the gain of the position-error integral term τ_int=ki·∫(q_d−q)dt. Unit '
        'Nm/(rad·s), range [0,1000]. Used to remove steady-state residual/offset (what remains '
        'after gravity is compensated by gs). The firmware auto-clears the integral at motion '
        'start to avoid windup shocks; the output is clamped by i_max. Typical values 10~40 '
        '(forearm 10, upper arm 40). Too large -> oscillation/overshoot.'),
 'i_max': ('Integral clamp (anti-windup)',
           'Upper limit on the integral output: larger -> stronger anti-sag but harsher '
           'start/stop. The brake against windup.',
           'Meaning: output clamp ±i_max of the integral term (anti-windup). Unit Nm, range '
           '[0,100]. Typical values 3~20 (forearm 3~4, upper arm 20). The larger the value, the '
           'stronger the anti-sag but the more pronounced the start/stop kick. Common misuse: '
           "maxing out both ki and i_max to try to make the arm 'never move', which very easily "
           'starts oscillation.'),
 'wall_stiff': ('Limit virtual-wall stiffness (FF_WALL off by default)',
                'Spring-damper push-back as the limit is approached. On this firmware, legal movej '
                'targets normally do not trigger it.',
                'Meaning: the spring stiffness of the virtual wall at the soft limit (wall force = '
                'k·δ + wall damping term). Unit Nm/rad, range [0,2000]. The FF_WALL bit is off by '
                'default; once enabled it only produces force when q approaches the limit. This '
                'firmware has no manual compliance mode, and legal movej targets are already '
                'blocked by the soft limits, so the wall is mainly a backstop.'),
 'wall_damp': ('Limit-wall damping',
               'Wall-zone damping (only resists motion in the outward direction past the wall).',
               'Meaning: the velocity damping of the virtual wall; it only resists motion in the '
               'outward direction past the wall (the force that would pull the joint out of the '
               'wall is clamped to 0), preventing bounce-back after hitting the limit. Unit '
               'Nm·s/rad, range [0,50].'),
 'wall_tau_max': ('Limit-wall force clamp',
                  "Upper limit on the virtual wall's output torque (±tau_max).",
                  'Meaning: the torque clamp of the wall force (sign·clamp before output). Unit '
                  'Nm, range [0,50]. Too small makes the wall useless; if set too large, values '
                  'approaching tau_max are still backstopped by tau_max.'),
 'gravity_scale': ('Per-joint gravity compensation scale gs',
                   'Gravity-term output knob: sag at target / holds soft -> raise gs on that axis '
                   '(gravity compensation too small). Factory baseline [1, 1, 1, 1, 1, 1, 1].',
                   'Meaning: per-joint scale on the gravity feedforward gs_j·G_j(q) (an output-end '
                   'multiplier knob). Dimensionless [0,20]. Factory baseline [1, 1, 1, 1, 1, 1, 1] '
                   '(re-set on 2026-09-12 when the model source changed: under the identified '
                   'inertia model it must return to 1.0; the old CAD-based compensation values are '
                   'deprecated). Sag at target/holds soft -> raise gs on the affected axis; lifts '
                   'past the target/pushes upward -> lower gs. Common misuse: changing the global '
                   'gravity vector instead of per-joint gs (use the gs knob first), or only '
                   'raising gs on the upper arm and ignoring the forearm.'),
 'inertia_scale': ('Per-joint inertia scale is',
                   'Inertia/Coriolis-term knob: high-inertia axes that track poorly dynamically -> '
                   'raise is. Too large -> prone to vibration.',
                   'Meaning: per-joint scale on the inertia/Coriolis feedforward '
                   'is_j·[M·q̈+C·q̇]_j. Dimensionless [0,20], factory all 1. Slow to start/stop or '
                   'reverse, square corners pulled off -> raise is on the high-inertia axes. Too '
                   'large -> feedforward overshoot and oscillation. Common misuse: treating is as '
                   "'more force' to suppress saturation that only appears with large kp (check "
                   'first whether tau_max is pinned at its ceiling).'),
 'friction_v': ('v2 viscous friction fv (velocity direction)',
                'τ= fv·q̇_d. Low-speed jerking (stick-slip) -> raise fv; too large -> jolt at zero '
                'crossing.',
                'Meaning: the viscous term of v2 friction, fv·q̇_d (q̇_d = desired velocity, not '
                'measured). Unit Nm·s/rad, range [0,20]. Factory values are the SE1 identified '
                'values (J1~J7 ≈ 0.75/0.64/0.20/0.26/0.03/0.08/0.04). Low-speed stick-slip/jerking '
                '-> raise fv; too large -> reverse jolt when crossing zero.'),
 'friction_fc0': ('v2 positive Coulomb fc0 (≥0)',
                  'Positive half-branch along the velocity direction; low-speed creep/static '
                  'friction compensation.',
                  'Meaning: the magnitude of the v2 Coulomb positive half-branch (velocity > 0 '
                  'side), must be ≥0. Unit Nm, range [0,50]. Factory SE1 values approx '
                  'J1~J7=1.24/2.28/0.39/0.59/0.09/0.12/0.08. Insufficient low-speed creep '
                  'compensation -> raise fc0; too large -> jolt when stopping/starting.'),
 'friction_fc1': ('v2 negative Coulomb fc1 (≤0, stored negative)',
                  'Negative half-branch along the velocity direction; together with fc0 it forms '
                  'asymmetric static friction (sign contract ≤0).',
                  'Meaning: the magnitude of the v2 Coulomb negative half-branch (velocity < 0 '
                  'side), stored as a negative value (≤0, sign contract). Unit Nm, range [-50,0]. '
                  'Together with fc0 it forms asymmetric static friction (SE1 identification is '
                  'usually slightly larger in the negative direction). Common misuse: entering a '
                  'positive number makes the firmware reject the whole group / clamp it back to '
                  '0.'),
 'kd_extra': ('τ-domain software derivative damping (fixes movej startup ringing)',
              'Motion mode only: τ += kd_extra·(q̇_d−q̇). Factory [6,6,6,6,0,0,0] — must be 0 for '
              'wrist joints.',
              'Meaning: extra derivative damping added on the [torque] field, used to fix movej '
              'startup ringing. Unit Nm·s/rad, range [0,50], factory [6,6,6,6,0,0,0]. Why put it '
              "on τ rather than kd: MIT's kd goes through the 12-bit q̇ channel and has a hard cap "
              'of 5, whereas τ, though also 12-bit, has torque as its full scale, so its '
              'resolution is much higher. ⚠ **Wrist joints (J5/J6/J7) must stay at 0**: J7 has '
              'extremely low inertia (≈0.0002 kg·m²), so kd_extra/J is far faster than the control '
              'period, and the delayed damping reverse-excites the axis (in upstream testing, '
              'adding 3 on all axes drove J7 to −3.33 rad/s and it was aborted by the velocity '
              'envelope).'),
 'drag_gain': ('Drag friction compensation ratio (per joint)',
               'Zero-gravity/drag only: how much friction each joint compensates. Factory all 0.6 '
               '(same value as the vendor coeff); larger = compensates harder, smaller = stickier. '
               'Only affects the drag path.',
               'Meaning: per-joint ratio of the drag friction compensation τ_drag = '
               'drag_gain_j·(fv_j·q̇ + Coulomb_j). Unitless, range [0,5], factory all 0.6 (same '
               'value as coeff[ROBOT_MAX_DOF] in the vendor MITDragDemo). Division of labor with '
               'friction_v/fc0/fc1: those are the identified physical friction parameters, while '
               'this item is only the compensation ratio. ⚠ This firmware (1.12.0) fixes the '
               'zero-gravity law at kd=0.1 and drag_db=0=hard sign, with no kd lower '
               'bound/quadratic stabilization term any more; setting gain clearly above 1 '
               'over-compensates and may cause one-directional drift. Only effective on the [zero '
               'gravity] and friction_model=2 paths; regular motion control does not use this '
               'item.'),
 'fric_db': ('v1 friction tanh deadband bandwidth',
             'v1: smoothing bandwidth of friction·tanh(e/fric_db); smaller means sharper friction '
             'switching. v2 (factory default) does not use it but keeps the default.',
             'Meaning: v1 friction tanh deadband bandwidth ε (error direction). Unit rad, range '
             '[1e-4,0.5], factory 0.02. The smaller it is, the steeper the friction near zero '
             'error (closer to hard Coulomb); the larger, the smoother. Participates only when '
             'friction_model=0. Common misuse: adjusting it with v2 on has no effect; under v1, '
             'too large a value makes the torque soft near zero on target.'),
 'wall_margin': ('Limit wall lead angle',
                 'How far from the soft limit the virtual-wall zone begins.',
                 "Meaning: the virtual wall's lead angle (how far from the soft limit it starts "
                 'applying force). Unit rad, range [0,0.5], factory 0.0524. Not involved when '
                 'FF_WALL is off.'),
 'friction_slew': ('Friction/wall output slew limit Nm/s',
                   'Slew ceiling for friction and wall torque, eliminating start/stop step noise; '
                   '0 = output frozen at its history.',
                   'Meaning: rate-of-change ceiling for friction and virtual-wall output '
                   '(first-order slew). Unit Nm/s, range [0,500], factory 60. Used to eliminate '
                   'step noise in friction torque at start/stop. 0 = output frozen at its '
                   'historical value. Common misuse: too small feels like friction compensation '
                   'cannot keep up (slow); too large loses the smoothing effect.'),
 'payload_mass': ('End-effector payload mass (kg)',
                  'Sagging or poor tracking with a grasped/hung heavy object → enter the payload '
                  "mass, don't just crank up kp. Works together with payload_com.",
                  'Meaning: mass mounted at the end effector, merged into the dynamics gravity '
                  'term (changing the mass is equivalent to recomputing the dynamics). Unit kg, '
                  'range [0,20]. After grasping/hanging a heavy object, sagging or poor tracking → '
                  'enter the real payload (gripper included) first, instead of only raising kp. '
                  'Accurate only when given together with payload_com; a wrong direction can '
                  'instead make compensation excessive.'),
 'payload_com': ('Payload center-of-mass offset (ee frame, m)',
                 'Offset of the payload center of mass relative to the end effector, so the '
                 'gravity term converts correctly.',
                 'Meaning: offset of the payload center of mass in the end-effector frame (x,y,z). '
                 'Unit m, range [-1,1]×3, factory 0. If the load hangs off-center → compensation '
                 'is computed wrong, causing sag/push-up in some poses. Measure the offset and '
                 'enter it. Typical misuse: mass with no offset (compensation is still inaccurate '
                 'when a heavy load is cantilevered).'),
 'gravity': ('Gravity vector in base frame (m/s²)',
             'Default (0,0,-9.81). For side-mounted/upside-down/tilted-table mounting, change it '
             'here (or start with the per-joint gs knobs).',
             'Meaning: gravity vector in the base frame, direction + magnitude. Unit m/s², each '
             'component [-50,50], factory (0,0,-9.81). Side-mounted/upside-down/tilted base → '
             "change it here so the model's gravity direction matches reality. For small "
             'deviations, prefer fine-tuning with the per-joint gs knobs. Common misuse: treating '
             'it as gs (it is global geometry; gs is the per-axis residual knob).'),
 'friction_model': ('Friction model switch 0=v1 / 1=v2',
                    'Factory = 1 (v2 velocity direction, SE1 triplet); 0 reverts to v1 '
                    '(error-direction tanh, uses friction/fric_db).',
                    'Meaning: selects the friction feedforward implementation. 1 = v2 velocity '
                    'direction (fv/fc0/fc1 triplet, factory default), 0 = v1 error direction '
                    '(friction + fric_db). v1/v2 share the FF_FRICTION bit. Before switching to 0, '
                    "tune friction/fric_db close to that axis's breakaway torque and try; "
                    'switching back to 1 restores the triplet.'),
 'fric_v2_eps': ('v2 tanh smoothing bandwidth (rad/s)',
                 'v2: the ε in tanh(q̇_d/ε). Smaller means sharper (harder) slip switching; too '
                 'large flattens the friction.',
                 'Meaning: v2 friction tanh smoothing bandwidth ε (tanh(q̇_d/ε)). Unit rad/s, '
                 'range [1e-3,0.5], factory 0.02. The smaller ε is, the steeper the '
                 'velocity-direction switching (closer to ideal Coulomb, but harsher through '
                 'zero); the larger, the more the friction is flattened (undercompensated). '
                 'Normally keep the factory value; reduce it in small steps only when you need it '
                 '"harder".'),
 'drag_db': ('Drag Coulomb deadband bandwidth',
             'Deadband bandwidth of the Coulomb term used specifically for zero gravity. Factory '
             "0.0 = hard sign (same as the vendor's MITDragDemo); if the real robot chatters, fall "
             'back to 0.02/0.05 to use tanh.',
             'Meaning: deadband bandwidth of u=(q̇/drag_db)² in drag friction. Unit rad/s, range '
             '[0,0.5], factory 0.0. 0.0 = hard sign Coulomb: full-amplitude Coulomb thrust '
             'whenever q̇≠0, with no deadband at zero speed — if zero-speed chatter appears on the '
             'real robot, change to 0.02/0.05 to use tanh (zero first derivative at zero speed). '
             'Different from fric_v2_eps: this one is used only in [drag] mode.'),
 'wall_fw_kd': ('Firmware velocity damping added in the wall zone',
                'Extra amount added to the motor kd when entering the limit wall zone (capped at '
                '5). Treats hand-tool-wall coupled oscillation.',
                'Meaning: amount added to MIT kd when a joint enters the limit wall zone (capped '
                'at 5 after addition). Unit Nm·s/rad, range [0,5], factory 0.8. Rationale: '
                "firmware kd executes in the motor's kHz current loop with no control-loop delay, "
                'making it a clean dissipation path for hand-tool-wall coupled oscillation '
                '(host-side damping does not provide enough phase lag). ⚠ Effective only in the '
                'wall zone of [zero-gravity mode] — the wall on the movej path is off by default.'),
 'hold_kp_gain': ('On-target stiffness multiplier',
                  'Within 0.2s after movej reaches target, ramps kp to kp×this value (capped at '
                  '500), while τ ramps to G(q_hold). Factory 2.0.',
                  'Meaning: amplification factor for holding stiffness after motion reaches '
                  'target. Unitless, range [0,5], factory 2.0. After arrival the firmware uses '
                  'smoothstep to ramp kp to mit_kp×this value within 0.2s (capped at 500), while '
                  'setting τ=G(q_hold) and freezing q_ref — i.e. "on-target stiffening", with '
                  'holding stiffness carried by kp rather than the integral. ⚠ Naming: this item '
                  'is semantically completely different from another similarly named firmware '
                  'parameter (hold_kp_scale=0.6, the derating factor for watchdog fail-soft), '
                  'hence it is named gain here. Larger → stiffer after arrival; smaller → softer '
                  'after arrival / may sag.')}

FF_LABELS = ['Master switch (total dynamics feedforward)',
 'Gravity',
 'Inertia',
 'Coriolis',
 'Friction (v1/v2 share this bit, selected by friction_model)',
 'Integral',
 'Limit virtual wall',
 'MIT quantization compensation',
 'Velocity reference']

FF_DETAILS = ['Master switch: the master switch for dynamics feedforward. Takes effect only when the G/inertia '
 'sub-bits are set. To turn off all feedforward as a group (leaving only PD motor-internal '
 'feedback), clear this bit; with the other bits untouched, clearing it is the fastest way back to '
 'pure PD.',
 'Gravity compensation: enables the gs_j·G_j(q) gravity feedforward. If the arm sags at target or '
 'holds softly, first confirm this bit is on and whether gs is sufficient. Off = no gravity '
 'compensation at all (holding will be soft).',
 'Inertia compensation: enables the is_j·(M·q̈(+ Coriolis)) inertia feedforward, for start/stop on '
 'high-inertia axes or poor dynamic tracking. When there is dynamic jitter, lower kp first, then '
 'look at this bit.',
 'Coriolis/centrifugal: only within the inertia group, decides whether the C(q,q̇)·q̇ Coriolis '
 'term is included. Can be enabled when tracking drifts on high-speed large-arm segments; at low '
 'speed it is almost imperceptible. Works together with the INERTIA bit.',
 "Friction feedforward: enables the friction term (v1/v2 share this bit's switch; the model is "
 'selected by friction_model). For low-speed judder/stick-slip, first confirm this bit is on, then '
 'tune fv/fc0/fc1.',
 'Integral term: enables ki·∫e to eliminate steady-state residual. If there is a static error at '
 'target but this bit is off, raising ki has no effect.',
 'Limit virtual wall: off by default. When enabled, adds a virtual wall near the soft limits (this '
 'firmware has no manual compliance; legal movej targets are already blocked by the soft limits).',
 "MIT quantization compensation: feedforward compensation for the motor's MIT 16-bit position / "
 '12-bit torque quantization error. Enable when low-speed fine motion / point-contact accuracy '
 'matters.',
 'Velocity-reference torque: in MIT mode, adds kd·dq_d as a velocity-reference feedforward. On by '
 'default; turning it off changes the low-speed tracking feel.']

MODEL_BODY_LABELS = ('Mass (identification basis)',
 'CoM x (identification basis)',
 'CoM y (identification basis)',
 'CoM z (identification basis)',
 'Inertia ixx',
 'Inertia ixy',
 'Inertia ixz',
 'Inertia iyy',
 'Inertia iyz',
 'Inertia izz')

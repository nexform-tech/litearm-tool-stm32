"""pyqtgraph.opengl 场景控件 —— 只读数字孪生。

只被 `ScenePage` 在第一次显示时 import，避免没打开 3D 的用户为 PyOpenGL
付启动时间。控件本身不读状态、不发命令：页面把平滑后的 q 喂给 `set_pose()`。

⚠ Linux 上 PyOpenGL 默认选 EGL 时找不到 Qt 的 GLX context（实测报
`Attempt to retrieve context when no valid context`）。`litetool.app` 会在
Qt 之前设 `PYOPENGL_PLATFORM=glx`；单独跑本模块时也要设。
"""
from __future__ import annotations

import time
from typing import Dict, Optional

import numpy as np
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QMatrix4x4, QVector3D
from PyQt5.QtWidgets import QSizePolicy

import pyqtgraph.opengl as gl
from pyqtgraph.opengl.shaders import FragmentShader, ShaderProgram, VertexShader

from litetool.scene.urdf_model import UrdfModel

#: 与 tool 深色界面一致的克制配色；末位是 ee/工具强调色。
PALETTE = (
    # 工业材质：深石墨底座 + 亮铝/中灰钛交替的连杆 + 蓝色阳极氧化末端。
    (0.50, 0.51, 0.54, 1.0),   # base — graphite
    (0.84, 0.86, 0.89, 1.0),   # J1 — aluminium
    (0.70, 0.72, 0.76, 1.0),   # J2 — titanium
    (0.84, 0.86, 0.89, 1.0),   # J3 — aluminium
    (0.70, 0.72, 0.76, 1.0),   # J4 — titanium
    (0.84, 0.86, 0.89, 1.0),   # J5 — aluminium
    (0.70, 0.72, 0.76, 1.0),   # J6 — titanium
    (0.84, 0.86, 0.89, 1.0),   # J7 — aluminium
    (0.25, 0.41, 0.58, 1.0),   # ee_link — anodised blue
)

#: 比 pyqtgraph 自带的 `shaded` 多一盏补光 + Blinn-Phong 高光 + 轻微菲涅尔；
#: 自带 shader 在深色界面里几乎只有暗面，看起来像塑料/剪影。
METAL_SHADER = ShaderProgram('litearm-metal', [
    VertexShader("""
        uniform mat4 u_mvp;
        uniform mat3 u_normal;
        attribute vec4 a_position;
        attribute vec3 a_normal;
        attribute vec4 a_color;
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            v_normal = normalize(u_normal * a_normal);
            v_color = a_color;
            gl_Position = u_mvp * a_position;
        }
    """),
    FragmentShader("""
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            vec3 N = normalize(v_normal);
            vec3 V = vec3(0.0, 0.0, 1.0);
            vec3 key  = normalize(vec3( 0.40, -0.60,  0.80));
            vec3 fill = normalize(vec3(-0.70,  0.25,  0.55));
            vec3 rim  = normalize(vec3( 0.00,  0.75,  0.35));
            float d1 = max(dot(N, key),  0.0);
            float d2 = max(dot(N, fill), 0.0);
            float d3 = max(dot(N, rim),  0.0);
            float s1 = pow(max(dot(N, normalize(key  + V)), 0.0), 64.0);
            float s2 = pow(max(dot(N, normalize(fill + V)), 0.0), 24.0);
            float front = max(dot(N, V), 0.0);
            float fres = pow(1.0 - front, 3.0);
            vec3 base = v_color.rgb;
            vec3 rgb = base * (0.34 + 0.46 * d1 + 0.26 * d2 + 0.10 * d3 + 0.22 * front)
                     + mix(vec3(1.0), base, 0.30) * (0.26 * s1 + 0.09 * s2)
                     + base * 0.12 * fres;
            gl_FragColor = vec4(rgb, v_color.a);
        }
    """),
])
BG = (240, 242, 245, 255)
GRID = (150, 158, 170, 140)


def qmatrix(m: np.ndarray) -> QMatrix4x4:
    return QMatrix4x4(*[float(v) for v in m.reshape(-1)])


class SceneWidget(gl.GLViewWidget):
    """URDF 网格 + 基座/工具坐标轴 + TCP 标记；`set_pose(q)` 只改变换。"""

    def __init__(self, model: UrdfModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._items: Dict[str, gl.GLMeshItem] = {}
        self._fit_center = np.zeros(3)
        self._fit_distance = 1.5
        self._cam_timer: Optional[QTimer] = None
        self._interacting = False
        self._cam_started = 0.0
        self._cam_start: Dict[str, object] = {}
        self._cam_target: Dict[str, object] = {}
        self._cam_ms = 260

        self.setBackgroundColor(BG)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._grid = gl.GLGridItem()
        self._grid.setSize(2.0, 2.0, 1.0)
        self._grid.setSpacing(0.1, 0.1, 1.0)
        self._grid.setColor(GRID)
        self.addItem(self._grid)

        self._base_axes = gl.GLAxisItem()
        self._base_axes.setSize(0.20, 0.20, 0.20)
        self.addItem(self._base_axes)

        self._tool_axes = gl.GLAxisItem()
        self._tool_axes.setSize(0.09, 0.09, 0.09)
        self.addItem(self._tool_axes)

        self._tcp = gl.GLScatterPlotItem(
            pos=np.array([[0.0, 0.0, 0.0]], dtype=np.float32),
            color=(0.05, 0.45, 0.72, 1.0), size=9.0, pxMode=True)
        self.addItem(self._tcp)

        self._build()
        self.set_pose(np.zeros(model.n_joints))
        self.frame_model(self._q)

    # ------------------------------------------------------------------ 构建
    def _build(self):
        for i, (name, link) in enumerate(self.model.links.items()):
            verts, faces = self.model.mesh(name)
            md = gl.MeshData(vertexes=verts, faces=faces)
            item = gl.GLMeshItem(
                meshdata=md, smooth=True, drawEdges=False,
                shader=METAL_SHADER, color=PALETTE[i % len(PALETTE)],
                glOptions="opaque")
            self._items[name] = item
            self.addItem(item)

    @property
    def triangle_count(self) -> int:
        return sum(len(self.model.mesh(name)[1]) for name in self.model.links)

    # ------------------------------------------------------------------ 姿态
    def frame_model(self, q=None) -> None:
        lo, hi = self.model.bounds(q)
        center = (lo + hi) / 2.0
        span = float(np.max(hi - lo))
        self._fit_center = center
        self._fit_distance = max(0.5, span * 1.85)
        self.setCameraPosition(pos=QVector3D(*center),
                               distance=self._fit_distance,
                               elevation=24, azimuth=36)

    # ------------------------------------------------------------------ 交互
    def mousePressEvent(self, ev):  # noqa: N802 - Qt 命名
        # 相机拖动期间暂停“状态→姿态”刷新：鼠标事件优先，避免 60Hz 定时器
        # 和拖动抢事件循环（软件渲染下尤其明显）。
        self._interacting = True
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):  # noqa: N802 - Qt 命名
        super().mouseReleaseEvent(ev)
        self._interacting = False
        self.update()

    # ------------------------------------------------------------------ 相机
    def camera_preset(self, name: str) -> None:
        center = QVector3D(*self._fit_center)
        distance = self._fit_distance
        elevation, azimuth = 24, 36
        if name == "front":
            elevation, azimuth = 4, 0
        elif name == "side":
            elevation, azimuth = 4, 90
        elif name == "top":
            elevation, azimuth = 88, 0
        elif name == "tool":
            # 工具视角：把当前工具位置放到画面中心，距离收近。
            tool = self.model.fk(self._last_q())[self.model.tool_link]
            center = QVector3D(*tool[:3, 3])
            distance = max(0.35, self._fit_distance * 0.35)
            elevation, azimuth = 20, 35
        self.animate_camera(center=center, distance=distance,
                            elevation=elevation, azimuth=azimuth)

    def animate_camera(self, *, center: Optional[QVector3D] = None,
                       distance: Optional[float] = None,
                       elevation: Optional[float] = None,
                       azimuth: Optional[float] = None,
                       ms: int = 260) -> None:
        cur_center = self.opts.get("center") or QVector3D(0, 0, 0)
        self._cam_start = {
            "center": QVector3D(cur_center),
            "distance": float(self.opts.get("distance", 1.0)),
            "elevation": float(self.opts.get("elevation", 0.0)),
            "azimuth": float(self.opts.get("azimuth", 0.0)),
        }
        self._cam_target = {
            "center": QVector3D(center) if center is not None else self._cam_start["center"],
            "distance": float(distance) if distance is not None else self._cam_start["distance"],
            "elevation": float(elevation) if elevation is not None else self._cam_start["elevation"],
            "azimuth": float(azimuth) if azimuth is not None else self._cam_start["azimuth"],
        }
        self._cam_ms = max(1, int(ms))
        self._cam_started = time.monotonic()
        if self._cam_timer is None:
            self._cam_timer = QTimer(self)
            self._cam_timer.timeout.connect(self._cam_step)
        self._cam_timer.start(16)
        self._cam_step()

    def _cam_step(self) -> None:
        t = min(1.0, (time.monotonic() - self._cam_started) * 1000.0 / self._cam_ms)
        e = t * t * (3.0 - 2.0 * t)                 # smoothstep
        a, b = self._cam_start, self._cam_target
        c0, c1 = a["center"], b["center"]
        center = QVector3D(
            c0.x() + (c1.x() - c0.x()) * e,
            c0.y() + (c1.y() - c0.y()) * e,
            c0.z() + (c1.z() - c0.z()) * e,
        )
        self.setCameraPosition(
            pos=center,
            distance=a["distance"] + (b["distance"] - a["distance"]) * e,
            elevation=a["elevation"] + (b["elevation"] - a["elevation"]) * e,
            azimuth=a["azimuth"] + (b["azimuth"] - a["azimuth"]) * e,
        )
        if t >= 1.0 and self._cam_timer is not None:
            self._cam_timer.stop()

    def _last_q(self):
        # tool 预设需要“当前工具位姿”；页面每帧都会 set_pose，这里用最后一次。
        return getattr(self, "_q", np.zeros(self.model.n_joints))

    def set_pose(self, q) -> None:
        self._q = np.asarray(q, dtype=float).reshape(-1)
        world = self.model.fk(self._q)
        for name, item in self._items.items():
            m = world.get(name)
            if m is not None:
                item.setTransform(qmatrix(m))
        tool = world.get(self.model.tool_link, np.eye(4))
        self._tool_axes.setTransform(qmatrix(tool))
        self._tcp.setTransform(qmatrix(tool))
        self.update()

    # ------------------------------------------------------------------ 显隐
    def set_grid_visible(self, on: bool) -> None:
        self._grid.setVisible(bool(on))

    def set_axes_visible(self, on: bool) -> None:
        self._base_axes.setVisible(bool(on))
        self._tool_axes.setVisible(bool(on))
        self._tcp.setVisible(bool(on))

    def shutdown(self) -> None:
        if self._cam_timer is not None:
            self._cam_timer.stop()

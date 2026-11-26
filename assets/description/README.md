# 3D description assets

本目录是 LiteArm 7 轴臂的 URDF + 网格，供 `litetool.scene` 只读渲染使用。

- **来源**：`nexform-tech/litearm-description`，包路径 `SE/litearm_description`，
  studio 锁定的 `v2.0.0`（见 `litearm-studio/description.lock.json`）。
- **版本**：decimated preview（studio 的 `build-description.mjs` 产物），
  9 个 binary STL，约 6.2 MB / 129k 三角形；不是 60 MB 的原始上游网格。
- **`meshes_lod/`**：`tools/gen_lod.py` 用二次误差简化生成的 LOD（约 45k 三角形，
  2.2 MB），3D 页默认用它（`config.yaml` 的 `scene_lod`）。视口是顶点瓶颈：
  实测 llvmpipe 1200×800 下 129k = 11.3 ms/帧，45k = 6.5 ms/帧。
  重新生成需要开发期依赖 `fast-simplification`（运行时不依赖）。
- **为什么不构建期下载**：tool 的安装包必须离线可用，且不引入 Node/pnpm。
  资产随包进入 PyInstaller 的 `_internal/assets/description`；源码运行从本目录读。
- **许可证**：模型属于上游仓库；分发前请按上游仓库的许可证确认。若上游模型更新，
  用 studio 的 locked fetch + decimation 流程重出 `meshes/`，再跑 `tools/gen_lod.py`，
  不要手工改 STL。

运行时可用 `LITEARM_TOOL_DESCRIPTION=/path/to/description` 指向另一份模型。

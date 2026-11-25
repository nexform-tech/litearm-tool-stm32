# 3D description assets

本目录是 LiteArm 7 轴臂的 URDF + 网格，供 `litetool.scene` 只读渲染使用。

- **来源**：`nexform-tech/litearm-description`，包路径 `SE/litearm_description`，
  studio 锁定的 `v2.0.0`（见 `litearm-studio/description.lock.json`）。
- **版本**：decimated preview（studio 的 `build-description.mjs` 产物），
  9 个 binary STL，约 6.2 MB / 129k 三角形；不是 60 MB 的原始上游网格。
- **为什么不构建期下载**：tool 的安装包必须离线可用，且不引入 Node/pnpm。
  资产随包进入 PyInstaller 的 `_internal/assets/description`；源码运行从本目录读。
- **许可证**：模型属于上游仓库；分发前请按上游仓库的许可证确认。若上游模型更新，
  用 studio 的 locked fetch + decimation 流程重出本目录，不要手工改 STL。

运行时可用 `LITEARM_TOOL_DESCRIPTION=/path/to/description` 指向另一份模型。

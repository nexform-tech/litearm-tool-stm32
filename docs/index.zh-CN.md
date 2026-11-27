[English](index.md) | 简体中文

本目录面向操作员和开发者，说明 LiteArm Tool STM32 的安装、运行与扩展方式。

# 文档索引

## 从这里开始

- [安装与验证](setup.zh-CN.md)：安装依赖、运行离线测试并连接机械臂。
- [架构](architecture.zh-CN.md)：组件、数据流、边界与设计决策。
- [项目 README](../README.zh-CN.md)：功能、安全模型、参数调参与固件兼容性。

## 任务

- [调参链路](architecture.zh-CN.md#数据流)：参数写入与读回经过的路径。
- [真机验收清单](../README.zh-CN.md#真机验收清单需-stm32--电机can-在线)：固件或工具变更后按顺序执行的检查。

## 参考

- [Studio → 工具能力对照](capability-matrix.zh-CN.md)：已落地、评审中、未开始与明确不迁。
- [参数调参页](../README.zh-CN.md#参数调参页参数页签)：读写命令表与取值范围。
- [固件兼容性](../README.zh-CN.md#固件版本兼容性14x--150)：状态帧布局与各版本行为。
- 设计记录：[工具设计 2026-09-07](superpowers/specs/2026-09-07-litearm-tool-stm32-design.md) 与 [限位标定与零位偏置 2026-09-08](superpowers/specs/2026-09-08-limits-calib-zero-offset-design.md)。

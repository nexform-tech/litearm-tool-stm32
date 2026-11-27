English | [简体中文](index.zh-CN.md)

This directory documents how to install, run, and extend LiteArm Tool STM32 for operators and developers.

# Documentation

## Start here

- [Setup](setup.md): install dependencies, run the offline tests, and connect to an arm.
- [Architecture](architecture.md): components, data flow, boundaries, and design decisions.
- [Project README](../README.md): features, safety model, parameter tuning, and firmware compatibility.

## Tasks

- [Tuning guide](architecture.md#data-flow): where parameter writes and readbacks travel.
- [On-hardware acceptance checklist](../README.md#on-hardware-acceptance-checklist): the ordered check performed after firmware or tool changes.

## Reference

- [Studio → tool capability matrix](capability-matrix.md): delivered, in review, not started, and deliberately not migrated.
- [Parameter tuning page](../README.md#parameter-tuning-page): write/read command table and ranges.
- [Firmware compatibility](../README.md#firmware-compatibility-14x--150): status-frame layouts and version behavior.
- Design records: [tool design, 2026-09-07](superpowers/specs/2026-09-07-litearm-tool-stm32-design.md) and [limits calibration and zero offset, 2026-09-08](superpowers/specs/2026-09-08-limits-calib-zero-offset-design.md).

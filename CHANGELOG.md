# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的记录方式。

## [1.0.0] - 2026-11-04

### Added

- Windows 平台基于 `SendInput` 的逐字键入，绕过网页粘贴限制
- 中文、English、数字、Emoji 和多行文本支持
- 2 / 3 / 5 / 8 秒切换等待，慢 / 标准 / 快三档输入速度
- 回车 / Shift+回车两种换行方式
- 全局热键 `Ctrl+Alt+K`
- 倒计时与输入进度浮层，`Esc` 随时中止
- 目标窗口权限检测：目标以管理员运行时给出明确提示
- 单实例运行，避免热键冲突
- 本地设置持久化，支持 `%APPDATA%` 不可写时回退到程序目录
- 禁用粘贴测试页 `demo/paste-guard-demo.html`
- PyInstaller 打包脚本、管理员启动脚本、Windows 构建 CI

### Fixed

- 修复输入完成后立即抢回焦点导致末尾字符丢失的问题
- 修复目标窗口权限更高时误报“完成”的问题
- 修复带 UTF-8 BOM 的设置文件无法读取的问题

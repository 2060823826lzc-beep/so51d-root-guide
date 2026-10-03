# Xperia 实验工具箱

面向个人机主的 Windows 开源实验工具：检测手机、尝试一次临时 Root、检查 KernelSU、隐藏或恢复底部手势条。

**当前最新修正版：1.3.2 · 常亮可选版。** 临时 Root 功能仍属实验性质。本项目独立维护，与 Sony、Google 或上游项目不存在官方合作、认证或背书关系。

## 下载与使用

[下载最新修正版完整便携包](https://github.com/2060823826lzc-beep/so51d-root-guide/releases/tag/v1.3.2) · [使用说明](docs/usage.md) · [支持范围](docs/compatibility.md)

1. 解压整个 ZIP，运行 `SO51D-Root-Tool.exe`，无需另装 Python 或 ADB。
2. 手机开启 USB 调试，连接电脑、允许授权，点击“刷新检测”。
3. 查看匹配情况后自行选择操作。等待解锁时可取消并恢复原常亮设置。

Root 执行后核验当前状态并结束，不强制等待 300 秒。已有 Root 时跳过激活，同一次开机最多尝试一次，不自动重试。

自动常亮是可选辅助，读取或开启失败、返回 `null`、存在旧恢复记录时均不会因此阻止 Root。程序跳过自动常亮并提示手动保持亮屏；读不到可靠原值时不修改设置。

## 技术来源

| 技术 | 在本项目中的用途 |
|---|---|
| [GhostLock](https://github.com/YuKongA/ghostlock-app) | 临时提权原生程序；本项目保留诊断修改源码 |
| [KernelSU](https://github.com/tiann/KernelSU) | 管理 Root 授权；随包提供指定管理器和辅助程序 |
| [ADB](https://developer.android.com/tools/adb) | 通过已授权 USB 调试执行手机命令 |
| [Android 资源覆盖](https://source.android.com/docs/core/runtime/rros) | 隐藏、恢复手势小白条 |
| [Python / Tkinter](https://docs.python.org/3/library/tkinter.html) | 后端脚本和 Windows 界面 |
| [PyInstaller](https://pyinstaller.org/) | 打包 Windows EXE |

具体版本、许可证、来源与源码获取方式见 [第三方清单](THIRD_PARTY_NOTICES.md)。Root 技术来自上游，本项目主要提供 Windows 操作界面、检测、配置选择、诊断记录与可逆操作管理。

## 使用边界

仅用于本人拥有或获得明确授权的设备。**允许点击尝试不代表手机已适配，也不保证成功或稳定。** 操作可能失败、卡死、重启或造成数据损失；请先备份。完整重启后临时 Root 会消失。

临时 Root 消失不等于恢复全部修改；应用、模块文件和设置可能保留。等待解锁阶段可取消激活，激活开始后停止电脑端等待不代表手机端操作已撤销。只向可信应用授予必要的 Root 权限。

本版 69 项离线测试和 EXE 自检通过，未新增整套实机 Root 验收。[查看验证记录](docs/validation.md)

日志在本机保存，不自动上传；主动分享前需脱敏。[隐私说明](PRIVACY.md) · [使用与责任声明](docs/disclaimer.md)

本项目自行编写的代码采用 [Apache-2.0](LICENSE)；第三方组件保留各自许可证，声明不会改变这些权利和义务。

[构建说明](docs/build.md) · [修改与来源记录](native/MODIFICATIONS.md) · [问题反馈](https://github.com/2060823826lzc-beep/so51d-root-guide/issues) · [安全反馈](SECURITY.md)

如果这个工具对你有帮助，欢迎给 [GitHub 仓库](https://github.com/2060823826lzc-beep/so51d-root-guide) 点个 **Star ⭐**，也欢迎在酷安分享帖点赞、收藏。反馈实测机型、固件、完整内核和使用结果，也能帮助完善适配记录。感谢支持本项目，以及提供核心技术的上游开源作者。

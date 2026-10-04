# Xperia 实验工具箱

面向个人机主的 Windows 开源实验工具：检测手机、尝试一次临时 Root、检查 KernelSU、隐藏或恢复底部手势条。

**当前版本：1.3.3 · 状态与界面修正版。** 临时 Root 功能仍属实验性质。本项目独立维护，与 Sony、Google 或上游项目不存在官方合作、认证或背书关系。

## 下载与使用

[查看发布与下载](https://github.com/2060823826lzc-beep/so51d-root-guide/releases) · [使用说明](docs/usage.md) · [支持范围](docs/compatibility.md)

1. 解压整个 ZIP，运行 `SO51D-Root-Tool.exe`，无需另装 Python 或 ADB。
2. 手机开启 USB 调试，连接电脑、允许授权，点击“刷新检测”。
3. 首页查看状态并选择操作，设备详情、历史记录、日志在独立分页查看。等待解锁时可取消本次操作。

Root 执行后核验当前状态并结束，不强制等待 300 秒。已有 Root 时跳过激活，同一次开机最多尝试一次，不自动重试。

Root 默认不修改充电常亮。需要时勾选“操作期间保持 USB 充电常亮”，结束或取消后恢复，读取或开启失败不阻止 Root。首页可独立开启 USB 常亮、关闭充电常亮、恢复首次手动修改前的设置，两套恢复记录独立保存。

当前常亮状态以手机回读为准；空闲时每 15 秒自动刷新，显示最近核验时间。断线或读取失败时显示未知，不把旧状态作为当前状态。该设置只控制充电常亮，不会点亮或解锁手机。

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

本版 90 项离线测试和 EXE 自检通过，未新增整套实机 Root 验收。[查看验证记录](docs/validation.md)

日志在本机保存，不自动上传；主动分享前需脱敏。[隐私说明](PRIVACY.md) · [使用与责任声明](docs/disclaimer.md)

本项目自行编写的代码采用 [Apache-2.0](LICENSE)；第三方组件保留各自许可证，声明不会改变这些权利和义务。

[构建说明](docs/build.md) · [修改与来源记录](native/MODIFICATIONS.md) · [问题反馈](https://github.com/2060823826lzc-beep/so51d-root-guide/issues) · [安全反馈](SECURITY.md)

如果这个工具对你有帮助，欢迎给 [GitHub 仓库](https://github.com/2060823826lzc-beep/so51d-root-guide) 点个 **Star ⭐**，也欢迎在酷安分享帖点赞、收藏。反馈实测机型、固件、完整内核和使用结果，也能帮助完善适配记录。感谢支持本项目，以及提供核心技术的上游开源作者。

# Xperia 实验工具箱 1.3.1

面向个人机主的 Windows 开源实验工具。本版修复 Root 后强制等待 300 秒，以及等待解锁时无法取消的问题。

下载 **SO51D-Root-Tool-1.3.1.zip**，完整解压后运行 SO51D-Root-Tool.exe，无需另装 Python 或 ADB。

- Root 执行后即时核验并结束，不强制等待五分钟。
- 等待解锁时可取消并恢复原常亮设置；断线保留恢复记录。
- 本包补齐第三方说明、许可证、隐私说明与使用声明。
- 2026-10-01 文档补充：参考上游官方说明，完善取消与恢复范围、Root 授权、日志隐私及责任边界；重新提供便携包与源码包及对应哈希，程序二进制不变。
- KernelSU-v3.3.0-source.zip 提供随包官方 KernelSU 版本的上游源码快照；Toolbox-1.3.1-source.zip 提供本项目与修改后的 GhostLock 源码。BusyBox-source-and-build.zip 补充内嵌 BusyBox 的源码与构建材料。源码与二进制均可在本页获取，SHA256SUMS.txt 用于校验。

63 项离线测试和编译后 EXE 自检通过。本次未新增整套实机 Root 验收。允许尝试不代表已适配，可能失败、卡死、重启或造成数据损失。仅用于本人或获得授权的设备；请先备份。

[技术来源与许可证](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/THIRD_PARTY_NOTICES.md) · [使用与责任声明](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/docs/disclaimer.md)

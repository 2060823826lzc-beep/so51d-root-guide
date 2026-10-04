# Xperia 实验工具箱 1.3.3 · 状态与界面修正版

本版优化整体界面，并明确显示手机的充电常亮设置。Root 默认不修改常亮设置；读取失败也不影响 Root 流程。

下载 **SO51D-Root-Tool-1.3.3.zip**，完整解压后运行 `SO51D-Root-Tool.exe`，无需另装 Python 或 ADB。

- 浅色首页集中展示状态与操作，设备详情、历史记录、执行日志单独分页，小窗口支持滚动。
- 空闲时自动刷新实际设置，显示最近核验时间；读取失败或断线时显示“状态未知”，不会推断为已开启或已关闭。
- “开启 USB 常亮”设置为仅 USB 供电时保持唤醒；“关闭充电常亮”关闭所有充电方式的常亮。两者都不会点亮屏幕或自动解锁。
- “恢复原设置”恢复本工具首次手动修改前的设置，按手机分别保存记录；恢复后可能仍然开启常亮，取决于原值。
- Root 的“操作期间保持 USB 充电常亮”默认不勾选。主动启用时保留其他供电方式，并在结束或取消后尝试恢复；与手动记录独立。
- 设置写入和恢复后回读核验，区分没有记录、成功、待恢复及失败；外部修改冲突时保留记录。
- 保留取消强制 300 秒等待、等待解锁时可取消的修复。

90 项离线测试及编译后的 EXE 自检通过。此次验证未执行真实手机命令，未新增整套实机 Root 验收。临时 Root 仍属实验功能，允许尝试不代表已适配或保证成功。

便携包包含许可证、第三方来源和源码材料。`Toolbox-1.3.3-source.zip` 提供本项目及修改后的 GhostLock 源码；发布附件同时提供 KernelSU、BusyBox 源码材料和原生诊断组件。使用 `SHA256SUMS.txt` 校验附件。

[使用说明](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/docs/usage.md) · [技术来源与许可证](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/THIRD_PARTY_NOTICES.md) · [验证记录](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/docs/validation.md)

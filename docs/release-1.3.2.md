# Xperia 实验工具箱 1.3.2 · 最新修正版

本版修复“无法确认原亮屏设置，未启动”导致无法尝试 Root 的问题。自动常亮现在是可选辅助功能，不再作为 Root 启动条件。

下载 **SO51D-Root-Tool-1.3.2.zip**，完整解压后运行 `SO51D-Root-Tool.exe`，窗口标题为“1.3.2 常亮可选版”，无需另装 Python 或 ADB。

- 常亮原值读取失败、返回 `null` 或异常值、开启失败：跳过自动常亮，提示手动保持亮屏，继续 Root 流程。
- 有旧待恢复记录或损坏记录：保留原记录，跳过本次自动常亮，不再因此阻止 Root。
- 读不到可靠原值时不修改设置；已经发出过修改命令时，仍尝试恢复并在失败时保留恢复记录。
- 保留 Root 后不强制等待 300 秒、等待解锁时可取消的修复。
- 跳过自动常亮后取消操作，不再误报“已恢复”。

69 项离线测试及编译后的 EXE 自检通过；自检不执行手机命令。本次未新增整套实机 Root 验收。临时 Root 仍属实验功能，允许尝试不代表已适配或保证成功。

便携包保留许可证、第三方来源和源码材料。`Toolbox-1.3.2-source.zip` 提供本项目及修改后的 GhostLock 源码；KernelSU 和 BusyBox 源码材料也随发布提供。`SHA256SUMS.txt` 用于校验附件。

[使用说明](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/docs/usage.md) · [技术来源与许可证](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/THIRD_PARTY_NOTICES.md) · [验证记录](https://github.com/2060823826lzc-beep/so51d-root-guide/blob/main/docs/validation.md)

# 第三方技术、许可与来源

根目录 `LICENSE` 仅说明本项目自行编写部分的 Apache-2.0 许可。第三方部分保留各自许可；下载包不是统一采用同一个许可证。

| 组件 | 固定版本 / 来源 | 用途与分发 | 许可与材料 |
|---|---|---|---|
| GhostLock | [YuKongA/ghostlock-app](https://github.com/YuKongA/ghostlock-app/tree/b28529cb31ef6cfe597bb8994eec411ef87513ea)，提交 `b28529cb31ef6cfe597bb8994eec411ef87513ea` | 修改后的临时提权诊断程序 | Apache-2.0；`native/LICENSE`、`native/src/`、`native/MODIFICATIONS.md` |
| 内核配置参考 | [NickJi2019/ghostlock-app，tag 113](https://github.com/NickJi2019/ghostlock-app/blob/113/app/src/main/assets/kernel_profiles/5.15.189-android13-8-00016-g51bba4309aac-ab14546557.conf) | 14546557 配置参考，经离线核验编码 | 上游 GhostLock 许可；来源见 `profiles/catalog.json` 和 `evidence/14546557-offline-profile.json` |
| KernelSU | [v3.3.0 / 32601](https://github.com/tiann/KernelSU/tree/v3.3.0)，提交 `932014ab5b2c9b74a3d11e2ec4d17dd10fc9442e` | 官方管理器 APK，以及从同一 APK 原样提取的 ksud | 根许可 GPLv3；内核目录 GPLv2；保留上游各目录声明，见 `licenses/KernelSU-*` |
| BusyBox（KernelSU 内嵌） | 1.36.1.1；[上游构建材料](https://github.com/topjohnwu/ndk-box-kitchen/tree/14d189ea3070a8167b3576bf83fe070d4a3441af) | 随官方 ksud 内嵌分发，未另行修改 | GPLv2；`licenses/BusyBox-LICENSE.txt`，源码与构建材料见 `sources/BusyBox-source-and-build.zip` |
| Android Platform Tools | [37.0.1](https://developer.android.com/tools/releases/platform-tools) | 原样复制 ADB 与配套接口 DLL，未打包整个 SDK | 各开源组件许可，保留完整 `platform-tools/NOTICE.txt`；不以本项目许可证替代 Google SDK 条款 |
| CPython | [后端 3.14.0b1](https://github.com/python/cpython/tree/v3.14.0b1)；GUI 使用 3.12.14 | 后端独立运行时、EXE 内的 Python 运行时 | Python/PSF 及随附第三方条款；`runtime/LICENSE.txt`、`licenses/CPython-3.12-LICENSE.txt` |
| Tcl/Tk | GUI 构建所用 CPython 发行版中的 8.6 系列 | Tkinter 图形界面 | 随包保留 Tcl、Tk 各自 `license.terms` |
| PyInstaller | [6.22.0](https://github.com/pyinstaller/pyinstaller/tree/v6.22.0) | 构建工具与 EXE bootloader | GPLv2 等适用条款及 bootloader 例外，见 `licenses/PyInstaller-COPYING.txt` |
| Android 资源覆盖 / 本地 Java 辅助程序 | Android RRO 接口；`src/GesturePillOverlay.java` | 修改本工具创建的 SystemUI 手势条颜色覆盖 | 本地辅助源码 Apache-2.0；Android SDK 是构建依赖，不随包分发 |

## 对应源码与构建资料

KernelSU 官方二进制未经本项目修改。对应 v3.3.0 的完整上游版本源码快照（含构建脚本和依赖版本文件）随便携包放在 `sources/KernelSU-v3.3.0-source.zip`，并在同一 Release 提供独立下载；上游链接和固定提交同时保留。各第三方依赖继续按其原许可提供。官方 APK 的签名属于上游，自行构建不承诺产生相同签名或逐字节相同 APK。

KernelSU 内嵌的 BusyBox 也保留 GPLv2 许可，补充上游 1.36.1 源码和 Android NDK 构建补丁、配置与说明，位于 `sources/BusyBox-source-and-build.zip`，同一 Release 提供独立下载。其 ARM64 二进制已与上游 1.36.1.1 发布包逐字节核对。来源快照与构建资料不代表已复现全部上游二进制。

本项目的完整源码快照也在同一 Release 提供。GhostLock 的实际诊断修改源码在 `native/`，原生构建脚本为 `scripts/build_native.py`；配置文件与来源在 `profiles/`。工具链与构建步骤见 `docs/build.md`。ONDK、Android SDK 和第三方构建工具不包含在便携包中。

程序与原生材料哈希见 `bundle-sha256.json`、`tools-manifest.json` 和 Release 的 `SHA256SUMS.txt`。许可证文本、版权声明和各组件条款保留在对应目录；使用、修改或再次分发时应按各组件条款处理。

## 修改与归属

本项目自行编写的部分包括 Windows GUI、ADB 操作编排、状态判断、配置选择、历史记录、恢复流程和手势条辅助程序。Root 原理与原生基础来自 GhostLock；Root 管理来自 KernelSU。本项目没有将上游技术宣称为原创。

修改后的上游原生文件有日期与修改说明。详见 `native/MODIFICATIONS.md`。项目名称和商标仅用于合理说明来源与设备，未获得或宣称上游官方背书。

这份清单记录实际分发材料和履约措施，不是对所有地区、所有使用方式均合法的保证。许可证的完整文本优先于本清单的简要概述。

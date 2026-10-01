# 构建当前工具箱

Windows，建议 Python 3.12。安装 `pip install pyinstaller==6.22.0`，运行：

```powershell
python -m unittest discover -s tests -v
python scripts/build_release.py --materials C:\path\to\extracted-tool
```

materials 是已解压的完整发布包或维护者现有工具目录，用于提供经过哈希核验的 runtime、platform-tools、downloads。构建脚本用当前仓库的 GUI、后端、配置覆盖素材中的同名文件，重新编译 EXE，清除运行记录并生成 SHA-256 清单。不会连接手机。不要以任意来源的素材替换依赖。

当前后端携带 Python 3.14.0b1 独立运行时；GUI 使用 Python 3.12 和 PyInstaller 6.22.0 构建。首次发布沿用已验证的运行时，不声称 EXE 可以逐字节复现。

原生诊断程序基于 YuKongA/ghostlock-app 的 b28529cb31ef6cfe597bb8994eec411ef87513ea，修改源码完整保留在 native/src。使用 ONDK r30.1 的 Windows 工具链：

```powershell
python scripts/build_native.py --toolchain C:\ondk-r30.1\toolchains\llvm\prebuilt\windows-x86_64\bin --output build/native
```

ONDK 来源：https://github.com/topjohnwu/ondk/releases/tag/r30.1 。Windows 压缩包 SHA-256：5743de90f45704728a0d726d46671be23b377e7867f6acb106e1aee77463276a。


## 公开分发材料

构建会复制当前使用、隐私和责任文档，以及对应许可证。
KernelSU 固定版本的源码快照放进 sources/，也可作为独立 Release 附件提供。
生成完整便携包后，同一 Release 同时提供当前项目源码快照和 SHA256SUMS.txt。
来源和构建步骤见 THIRD_PARTY_NOTICES.md、third_party/README.md。

没有分发整个 Android SDK，也未分发本工具不依赖的 libwinpthread DLL。
构建会执行 EXE 自检；不会执行真实手机 Root。

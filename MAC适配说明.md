# macOS 适配与本机构建（v0.5.1）

已在 Apple Silicon、macOS 26.5.2、Python 3.13.4 上验证本地构建。源码保留原项目的动画、互动、拖动、吸边、自移动、大小调节和 Codex 集成。本说明不代表 Intel Mac 或其他 macOS 版本已经通过验收，也不代表已有正式签名、公证的公开安装包。

## 构建

在 Mac 上、仓库根目录中执行。先安装 Apple Command Line Tools，供本地签名和 PyInstaller 使用。

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-macos.txt
```

从[原作者 v0.5.1 发布页](https://github.com/jingh12312-rgb/bailong-desktop-pet/releases/tag/v0.5.1)下载 `bailong-desktop-pet-v0.5.1-windows-x64-webm.zip`。35 段动画未纳入 Git；仅从该压缩包提取 `BailongPet/outputs` 并放到仓库根目录，与 `app` 并列。不要复制 Windows 的 `_internal` 或 `tools/ffmpeg.exe`。

也可以用 Python 标准库解压，保留中文文件名：

```sh
python -m zipfile -e ~/Downloads/bailong-desktop-pet-v0.5.1-windows-x64-webm.zip work/upstream-release
cp -R work/upstream-release/BailongPet/outputs .
python app/pet.py --self-test
python work/build_macos.py
```

生成 `dist-macos/BailongPet.app`，可以移到“应用程序”后双击打开。首次启动会预加载动画，请等待准备完成。运行该 `.app` 无需另装 Python 或 FFmpeg。

构建脚本从 `imageio-ffmpeg` 取得本机架构解码器，检查 `libvpx-vp9` 支持，并将解码器、播放资源、音效和图标一起打包。动画显式使用 `libvpx-vp9` 解码，避免默认 VP9 解码器丢失透明通道。脚本只构建当前机器架构，不生成通用二进制。

临时签名只用于本地构建。向其他用户分发前仍需处理 Apple 开发者签名、公证及所包含组件的许可，不要关闭或绕过系统安全检查。原项目的源码与美术素材许可声明保持不变，见 README 和 ASSETS.md；本次改动不重新分发动画或安装包。

## 使用与自动启动

单击互动，拖动移动，右键打开菜单；隐藏后从菜单栏图标恢复。双击查询 Codex 额度需要本人已登录的 Codex 和网络。对话会使用本人的 Codex 额度。

将 `.app` 放到固定位置后，可开启或关闭随 Codex 启动：

```sh
/Applications/BailongPet.app/Contents/MacOS/BailongPet --enable-autostart
/Applications/BailongPet.app/Contents/MacOS/BailongPet --disable-autostart
```

开启后，用户级 LaunchAgent 在登录时运行监测器，检测 Codex 或 ChatGPT 桌面进程从未运行变为运行时启动桌宠；它不会在关闭 Codex 时自动退出桌宠。移动或卸载前先关闭自动启动，移好后重新开启。监测器配置位于 `~/Library/LaunchAgents/com.bailongpet.autostart.plist`。

配置、诊断及本地对话记录写入 `~/Library/Application Support/BailongPet`，自检也写到该用户目录，避免修改已签名的 `.app`。原有 Codex 任务同步仅查询本机数据库，仍依赖数据库格式；同步的公开进度会保存到桌宠自己的本地历史。仓库不包含个人登录信息或运行记录。

## 验证范围

- 本机原生 `.app` 启动、菜单栏入口、点击/拖动及右键菜单窗口。
- 35 段动画解码、透明通道像素检查、离线交互自检。
- 修复 Qt 工具窗口在应用失去焦点后自动消失；已观察到 Codex 位于前台时桌宠仍在屏幕上。
- 修复 Qt 的 MoveToActiveSpace 与 CanJoinAllSpaces 行为冲突导致的启动异常。
- 成品在不含开发环境 PATH 的环境中通过离线自检，解压后的签名完整性检查通过。
- 用户级 LaunchAgent 从安装路径自动拉起桌宠；只读额度查询成功，任务同步观察到本机活动任务。

Intel Mac、多个显示器、手动切换 Space、真实全屏隐藏/恢复、声音播放、重新登录系统后的自动启动及真实对话任务尚未逐项实测。自动启动检测到了现有桌面进程，但未为验收强行退出并重启用户的 Codex。

原生窗口回归测试需在可用的 macOS 桌面会话中单独运行：

```sh
python -m unittest discover -s app -p test_macos_window.py -v
python -m unittest discover -s app -p test_platform_support.py -v
python -m unittest discover -s app -p test_video_frames.py -v
```

`test_macos_window.py` 在非 Cocoa 平台跳过；offscreen 模拟检查不能代替原生焦点切换和显示验收。

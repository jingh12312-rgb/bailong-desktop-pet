# GPT白龙娘动态桌宠 v0.5.1

Windows轻量版：自移动、吸边探头、大小调节、Codex公开任务进展提醒，35段透明WebM动画。

普通使用者请到[发布页](https://github.com/jingh12312-rgb/bailong-desktop-pet/releases/tag/v0.5.1)下载 `bailong-desktop-pet-v0.5.1-windows-x64-webm.zip`，全部解压后双击 `BailongPet.exe`。

macOS 用户请阅读 [Mac 适配与本机构建说明](MAC适配说明.md)。目前已在 Apple Silicon Mac 上验证本地 `.app` 构建、35 段动画和基础交互，并修复切换到其他应用时桌宠消失的问题；暂不提供正式签名、公证的 Mac 安装包。

## 开发者运行

此仓库提供v0.5.1轻量版源码；动画素材和Windows解码器随上述完整发布包提供，没有纳入Git历史。

1. 安装64位Python（当前构建使用Python 3.13）。
2. 在源码目录执行 `python -m pip install -r requirements.txt`。
3. 从完整Windows发布包复制整个 `outputs` 和 `tools` 文件夹到源码根目录，与 `app` 并列。保留全部35段WebM及素材清单。
4. 执行 `python app/pet.py`；自检执行 `python app/pet.py --self-test`。

程序通过FFmpeg的libvpx-vp9解码透明通道，保留动作预加载；请不要用丢弃透明通道的默认VP9解码方式替换。

## 构建Windows包

在Windows上安装PyInstaller 6.22.3至 `.build-tools`：`python -m pip install --target .build-tools pyinstaller==6.22.3`。

运行 `python work/build_windows.py` 生成EXE。重新整理完整ZIP使用 `python work/build_release.py`，需要先将FFmpeg放在 `work/video-deps/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe`（可从完整包的tools/ffmpeg.exe复制），并保留outputs素材。脚本会生成带运行库、解码器及素材的发布包。

## 说明

没有Codex也能使用普通桌宠功能。额度、对话与任务同步需要使用者自己的Codex安装和登录。仓库不包含账号、密钥、个人聊天记录。

macOS构建脚本包含本机架构的FFmpeg、动画资源和图标，并执行本地临时签名及签名完整性检查。Apple Silicon上的本地验证范围与尚未验证的功能见Mac适配说明；Intel Mac、其他macOS版本和正式发布流程尚未验收。

源码尚未指定开源许可证；公开源码不代表授予任意使用或再分发许可。美术素材说明见ASSETS.md，运行库遵循各自许可证。本项目非OpenAI官方产品。

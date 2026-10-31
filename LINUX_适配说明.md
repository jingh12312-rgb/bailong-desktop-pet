# 白龙桌宠 v0.5.1 Linux 使用与构建

本适配以 Ubuntu 24.04、x86_64、GNOME Wayland 下的 XWayland 为主要目标。具体已通过项目以随附验收报告为准。其他发行版、真实 X11 登录、原生 Wayland、多屏和登录自启动不因代码存在而视为已验收。

## 启动便携包

完整解压后进入 `BailongPet` 目录，运行 `./BailongPet`。保留全部子目录。该包携带 Python、Qt、Linux FFmpeg 和 `libxcb-cursor`，仍使用系统的图形驱动及基础 X11/音频运行库，不依赖系统 Python。不要运行 Windows 的 `ffmpeg.exe`。

单击互动，双击查询额度，按住左键拖动。拖到左右边缘可吸边；贴边时单击展开。右键桌宠或托盘图标打开动画、对话、历史、大小、音效和隐藏设置。通过“退出桌宠”关闭程序。重复启动会唤回已有实例；预加载期间不会创建第二只。

动画和互动可以离线运行。对话及额度查询使用你自己的 Codex 安装和登录。程序不会捆绑账号。Linux 登录环境缺少终端 PATH 时，会查找常见安装位置，包括 fnm、nvm。若未找到，可在启动进程中传入 `BAILONG_CODEX=/绝对路径/codex`；不需要修改系统环境变量。

## Wayland 能力边界

有 XWayland 时默认使用 Qt xcb。当前 Wayland 会话不支持可靠的跨应用全屏检测，因此相应菜单项会禁用并说明原因。可以手动隐藏并通过托盘恢复。

`BAILONG_QPA_MODE=wayland` 仅供开发者验证原生 Wayland。原生 Wayland 的任意定位、置顶、吸边和自动全屏隐藏未承诺可用。真实 X11 会话可使用 EWMH 全屏检测，需要 `xprop`；本机 XWayland 测试不等于真实 X11 登录验收。

## 用户文件

Linux 的对话记录放在 `$XDG_DATA_HOME/BailongPet`，运行状态放在 `$XDG_STATE_HOME/BailongPet`，帧缓存放在 `$XDG_CACHE_HOME/BailongPet/frame_cache`。变量未设置或为相对路径时，分别使用 `~/.local/share`、`~/.local/state` 和 `~/.cache`。偏好由 Qt 写入用户配置目录。

开发验收可设置 `BAILONG_DATA_DIR` 和独立 `XDG_CONFIG_HOME`，避免影响真实历史和设置。不要将真实账户目录或聊天记录放进发行包。

## 源码运行

固定上游提交 `b102e734f20bb50889af12df5778f1499109f41b`。远端 `v0.5.1` 标签目前指向旧提交，请勿以标签代替此基线。

在独立虚拟环境安装 `requirements-linux.txt`。从官方 v0.5.1 完整发布包复制 `outputs/白龙桌宠素材`。发布包 SHA-256 为 `4b636bf1e92a82a798b01be09cbd658cbfc46c548dd1a38acee31368b9c78580`，包含 35 段 WebM 及素材清单。旧版 25 段素材不能替代。

运行 `python work/check_linux.py` 检查条件，再用 `bash work/run_linux.sh` 启动。源代码运行若缺少 xcb 系统库，可安装发行版依赖，或在项目 `tools/lib` 提供匹配运行库。安装系统依赖属于单独操作。

## 自检与界面验收

离线自检：`./BailongPet --self-test --self-test-output /绝对路径/报告目录`。默认报告放在用户状态目录，不写入安装目录。

真实界面验收要求隔离的 `BAILONG_DATA_DIR`、`XDG_CONFIG_HOME`、可用桌面及 `xdotool`，运行 `./BailongPet --gui-test --self-test-output /绝对路径/报告目录`。脚本会操作自己的窗口并暂时移动鼠标，结束时恢复鼠标位置。它使用真实 XCB 窗口和 Qt 输入事件，并额外通过 XTest 验证原生点击、拖动；所有动画的画面选择属于程序化测试。

仅在明确需要真实连接时增加 `--test-model gpt-6-luna`。脚本显式选择该模型的最低可用推理档位，发送一条固定短句。模型不可用时失败退出，不自动换模型。成功回复以 `completed` 状态为准。

额度单独验收：`./BailongPet --self-test --quota-only --self-test-output /绝对路径/报告目录`。此命令只读查询，不发送对话请求。

## 可选自启动

默认不安装自启动。源码入口为 `python app/linux_autostart.py --enable --backend xdg --trigger codex`。`--trigger session` 表示登录后直接启动。`--backend systemd` 为可选用户服务路径，依赖桌面会话集成。状态查询使用 `--status`，关闭使用 `--disable`。

启用或关闭会修改用户配置，并可能启动或停止对应监视器。请在明确选择后操作。改变安装位置后应重新生成入口。本轮测试仅使用隔离目录和当前会话，不证明真实登录自启动成功。

## 构建和来源

构建环境另装 `pyinstaller==6.22.3`，运行 `python work/build_linux.py --output /绝对路径/新构建目录`。脚本拒绝覆盖已有同名发行目录。构建包包含版本信息与第三方许可；详细版本锁定文件随交付提供。

FFmpeg 来自 `imageio-ffmpeg==0.7.0` 的 Linux wheel，实际解码器为 FFmpeg 7.0.2-static（johnvansickle.com），构建时核查 `libvpx-vp9`。FFmpeg 许可独立于 Python 包的 BSD 许可，以 `licenses/FFmpeg-LICENSE.txt` 为准。随附 xcb 库来自 Ubuntu `libxcb-cursor0 0.1.4-1build1`。

上游源码和美术素材尚未指定开放再分发许可。此包用于本地适配和验收；公开再分发前需处理上游授权及各运行库的许可条件。源码差异和测试报告可供后续 PR 审查，本轮不会提交、推送或创建 PR。

## 本轮界面问题修复

中文气泡按实际宽度计算换行后的高度，并在新内容进入布局后再测量。覆盖短句切长句、50%—150% 缩放、额度/任务结果/互动消息切换，以及进度标题更新，避免窗口仍使用单行高度而裁切文字。

默认待机 `idle.webm` 的原始透明帧中含有块状底部残影。本轮只对该文件的解码帧启用局部清理：保留 RGB、顶部区域、实体轮廓和少量羽化边缘，仅清除底部轮廓以外的透明残留。原始 WebM 不变，其他动画不应用此处理。开发对照可在启动进程中设置 `BAILONG_CLEAN_IDLE_SHADOW=0` 查看原始残影。预解码缓存带处理版本标记，旧缓存不会绕过修复。

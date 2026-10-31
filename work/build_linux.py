"""在 Linux 构建独立目录包；不安装系统依赖，不覆盖已有发行目录。"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not sys.platform.startswith('linux'):raise SystemExit('请在 Linux 构建。')
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'app'))
    from linux_support import diagnostics
    report=diagnostics(root)
    if report['missing_assets'] or report['assets_present']!=35 or not report['ffmpeg_libvpx_vp9_decoder']:
        raise SystemExit('素材或透明解码器检查失败：'+json.dumps(report,ensure_ascii=False))
    output=(args.output or root/'dist-linux').absolute()
    destination=output/'BailongPet'
    if destination.exists():raise SystemExit('为保留已有构建，不覆盖：'+str(destination))
    import PyInstaller.__main__
    options=['--onedir','--windowed','--contents-directory','.',
             '--name','BailongPet','--distpath',str(output),
             '--workpath',str(root/'.build-linux/work'),
             '--specpath',str(root/'.build-linux'),
             '--exclude-module','imageio_ffmpeg',
             '--exclude-module','tkinter']
    library=root/'tools/lib/libxcb-cursor.so.0'
    if library.is_file():options+=['--add-binary',str(library)+':.']
    for module in ('autostart','linux_autostart','linux_support','linux_runtime','linux_acceptance',
                   'selftest','desktop_task_sync','desktop_visibility','chat_backend',
                   'chat_ui','quota','video_frames','PySide6.QtMultimedia','PySide6.QtTest'):
        options+=['--hidden-import',module]
    PyInstaller.__main__.run([*options,str(root/'app/pet.py')])
    shutil.copytree(root/'outputs/白龙桌宠素材',destination/'outputs/白龙桌宠素材')
    shutil.copytree(root/'app/sounds',destination/'app/sounds')
    (destination/'tools').mkdir()
    shutil.copy2(report['ffmpeg'],destination/'tools/ffmpeg')
    licenses=destination/'licenses';licenses.mkdir()
    if (root/'tools/licenses').is_dir():
        shutil.copytree(root/'tools/licenses',licenses/'runtime-texts')
    for name in ('PySide6','shiboken6','pillow','psutil','pyinstaller','imageio-ffmpeg'):
        distribution=importlib.metadata.distribution(name)
        for item in distribution.files or ():
            parts=Path(str(item)).parts
            if any(p.lower().startswith(('license','copying','notice')) for p in parts):
                original=distribution.locate_file(item)
                if original.is_file():
                    target=licenses/name/Path(*parts)
                    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target)
    copyright=root.parent/'downloads/xcb-cursor/usr/share/doc/libxcb-cursor0/copyright'
    if copyright.is_file():shutil.copy2(copyright,licenses/'libxcb-cursor-copyright.txt')
    license_text=subprocess.run([str(destination/'tools/ffmpeg'),'-L'],capture_output=True,text=True,check=True)
    (licenses/'FFmpeg-LICENSE.txt').write_text(license_text.stdout+license_text.stderr)
    info={'upstream':'b102e734f20bb50889af12df5778f1499109f41b',
          'linux_port_revision':'20261031-ui-fixes-r2',
          'platform':platform.platform(),'python':platform.python_version(),
          'dependencies':{name:importlib.metadata.version(name) for name in ('PySide6','Pillow','psutil','imageio-ffmpeg','pyinstaller')},
          'ffmpeg_sha256':hashlib.file_digest((destination/'tools/ffmpeg').open('rb'),'sha256').hexdigest(),
          'scope':'Ubuntu 24.04 x86_64；本地验收候选包；其他平台见验收报告'}
    info['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'app').glob('*.py')) if not p.name.startswith('test_')}
    (destination/'LINUX_BUILD_INFO.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
    shutil.copy2(root/'LINUX_适配说明.md',destination/'Linux使用说明.md')
    print('构建完成：'+str(destination))
    return 0

if __name__=='__main__':sys.exit(main())

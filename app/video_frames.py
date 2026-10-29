"""Decode VP9 alpha explicitly; the default VP9 decoder may discard alpha."""
import os,subprocess,sys,shutil
from pathlib import Path
from platform_support import resource_root

def ffmpeg_path():
    root=resource_root()
    for candidate in (root/'tools/ffmpeg.exe',root/'tools/ffmpeg',root/'work/video-deps/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'):
        if candidate.is_file():return str(candidate)
    found=shutil.which('ffmpeg')
    if found:return found
    raise RuntimeError('缺少透明动画播放器，请重新完整解压桌宠安装包。')

def rgba_frames(path,size):
    args=[ffmpeg_path(),'-hide_banner','-loglevel','error','-threads','2','-c:v','libvpx-vp9','-i',str(path),'-an','-vf',f'scale={size}:{size}:flags=lanczos','-pix_fmt','rgba','-f','rawvideo','pipe:1']
    kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
    with subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs) as proc:
        try:
            stride=size*size*4
            while True:
                raw=proc.stdout.read(stride)
                if not raw:break
                if len(raw)!=stride:raise RuntimeError('动画帧不完整：'+str(path))
                yield raw
            error=proc.stderr.read().decode('utf-8',errors='replace')
            if proc.wait()!=0:raise RuntimeError('透明动画读取失败：'+error[-1000:])
        finally:
            if proc.poll() is None:proc.kill();proc.wait()

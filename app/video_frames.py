"""Decode VP9 alpha explicitly; the default VP9 decoder may discard alpha."""
import os,subprocess,sys,shutil
from pathlib import Path
from platform_support import resource_root


def alpha_cleanup_tag(path):
    """Only the inspected official idle clip has a confirmed floor-matte defect."""
    if (sys.platform.startswith('linux') and Path(path).name=='idle.webm'
            and os.environ.get('BAILONG_CLEAN_IDLE_SHADOW','1')!='0'):
        return 'idle-footer-contour-v1'
    return None


def clean_idle_footer(raw,size):
    """Remove the idle clip's footer matte outside its solid silhouette.

    Preserve RGB, all alpha>=224 pixels, the top 80%, and a one-display-pixel
    feather below each solid column. This is not a whole-image alpha threshold.
    """
    if len(raw)!=size*size*4:raise ValueError('无效的 RGBA 帧尺寸')
    result=bytearray(raw);start=size*4//5;feather=max(1,round(size/256))
    for x in range(size):
        last=next((y for y in range(size-1,start-1,-1) if result[(y*size+x)*4+3]>=224),start-1)
        for y in range(max(start,last+feather+1),size):result[(y*size+x)*4+3]=0
    return bytes(result)

def ffmpeg_path():
    root=resource_root()
    if sys.platform.startswith('linux'):
        override=os.environ.get('BAILONG_FFMPEG')
        if override:
            path=Path(override).expanduser()
            if not path.is_file() or not os.access(path,os.X_OK):
                raise RuntimeError('BAILONG_FFMPEG 不是可执行文件：'+str(path))
            return str(path)
        candidates=(root/'tools/ffmpeg',shutil.which('ffmpeg'))
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and os.access(candidate,os.X_OK):return str(candidate)
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError,RuntimeError):pass
    else:
        candidates=(root/'tools/ffmpeg.exe',root/'tools/ffmpeg',
                    root/'work/video-deps/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe',
                    shutil.which('ffmpeg'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate,os.X_OK):
            return str(candidate)
    raise RuntimeError('没有找到可执行的 FFmpeg。请安装 requirements-linux.txt 或设置 BAILONG_FFMPEG。')

def rgba_frames(path,size):
    args=[ffmpeg_path(),'-hide_banner','-loglevel','error','-threads','2','-c:v','libvpx-vp9','-i',str(path),'-an','-vf',f'scale={size}:{size}:flags=lanczos','-pix_fmt','rgba','-f','rawvideo','pipe:1']
    from linux_runtime import child_options,stop_child
    kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else child_options(args[0])
    with subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs) as proc:
        try:
            stride=size*size*4
            while True:
                raw=proc.stdout.read(stride)
                if not raw:break
                if len(raw)!=stride:raise RuntimeError('动画帧不完整：'+str(path))
                if alpha_cleanup_tag(path):raw=clean_idle_footer(raw,size)
                yield raw
            error=proc.stderr.read().decode('utf-8',errors='replace')
            if proc.wait()!=0:raise RuntimeError('透明动画读取失败：'+error[-1000:])
        finally:
            stop_child(proc)

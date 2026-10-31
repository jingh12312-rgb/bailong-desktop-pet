"""Local process ownership and Linux singleton helpers; no desktop configuration."""
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys


def child_environment(executable=None):
    env=os.environ.copy()
    if sys.platform.startswith('linux'):
        # PyInstaller's private libraries must not be inherited by Node/FFmpeg.
        if getattr(sys,'frozen',False):
            original=env.pop('LD_LIBRARY_PATH_ORIG',None)
            if original:env['LD_LIBRARY_PATH']=original
            else:env.pop('LD_LIBRARY_PATH',None)
        if executable:
            parent=str(Path(executable).absolute().parent)
            env['PATH']=parent+os.pathsep+env.get('PATH',os.defpath)
    return env


def child_options(executable=None):
    return {'start_new_session':True,'env':child_environment(executable)} if sys.platform.startswith('linux') else {}


def stop_child(process):
    """Reap this child and the Linux session group created by child_options()."""
    grouped=sys.platform.startswith('linux')
    if grouped:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    elif process.poll() is None:process.terminate()
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if grouped:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:process.kill()
        process.wait(timeout=2)
    if grouped:
        # A wrapper can exit before its descendants. Its owned PGID remains ours.
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass


def instance_directory():
    from platform_support import state_root,xdg_path
    if os.environ.get('BAILONG_DATA_DIR'):
        return state_root()/'runtime'
    return xdg_path('XDG_RUNTIME_DIR','.cache')/'bailong-pet'


def instance_name():
    key=str(instance_directory().absolute()).encode()
    return 'bailong-pet-'+hashlib.sha256(key).hexdigest()[:20]


def acquire_instance():
    import fcntl
    directory=instance_directory();directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    handle=(directory/'pet.lock').open('a+b')
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:handle.close();return None
    return handle

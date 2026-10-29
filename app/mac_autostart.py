"""User LaunchAgent; never modifies system launch daemons."""
import os,sys,subprocess,plistlib
from pathlib import Path

LABEL='com.bailongpet.autostart'
def entry():return Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
def command():
    return [sys.executable,'--autostart'] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).with_name('pet.py')),'--autostart']
def disable():
    p=entry()
    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}',str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    p.unlink(missing_ok=True)
def enable():
    disable();p=entry();p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(plistlib.dumps({'Label':LABEL,'ProgramArguments':command(),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10}))
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(p)],check=True)
def monitor():
    import time
    from autostart import gpt_is_open,launch_pet
    previous=False
    while True:
        current=gpt_is_open()
        if current and not previous:launch_pet()
        previous=current;time.sleep(2)

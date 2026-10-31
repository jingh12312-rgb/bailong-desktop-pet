"""通过当前用户的真实托盘协议操作指定 PID；不操作其他应用。"""
import re
import subprocess
import time


def call(destination,path,method,*args):
    result=subprocess.run(['gdbus','call','--session','--dest',destination,'--object-path',path,'--method',method,'--',*map(str,args)],capture_output=True,text=True,timeout=5)
    if result.returncode:raise RuntimeError(result.stderr.strip())
    return result.stdout


def tray_endpoint(pid):
    items=call('org.kde.StatusNotifierWatcher','/StatusNotifierWatcher','org.freedesktop.DBus.Properties.Get','org.kde.StatusNotifierWatcher','RegisteredStatusNotifierItems')
    for item in re.findall(r"'([^']+)'",items):
        destination,path=item.split('@',1) if '@' in item else (item,'/StatusNotifierItem')
        try:
            owner=call('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus.GetConnectionUnixProcessID',destination)
        except RuntimeError:continue
        if int(re.search(r'\b(\d+)\b',owner).group(1))==pid:
            menu=call(destination,path,'org.freedesktop.DBus.Properties.Get','org.kde.StatusNotifierItem','Menu')
            return destination,re.search(r"'([^']+)'",menu).group(1)
    raise RuntimeError('没有找到指定 PID 的托盘端点：'+str(pid))


def tray_action(pid,label):
    destination,path=tray_endpoint(pid)
    call(destination,path,'com.canonical.dbusmenu.AboutToShow',0)
    layout=call(destination,path,'com.canonical.dbusmenu.GetLayout',0,-1,"['label','enabled','visible']")
    entries=re.findall(r"\((\d+), \{[^}]*'label': <'([^']+)'>",layout)
    item=next((identifier for identifier,text in entries if text==label),None)
    if item is None:raise RuntimeError('托盘菜单没有指定项目：'+label)
    call(destination,path,'com.canonical.dbusmenu.Event',item,'clicked','<0>',0)
    return {'pid':pid,'destination':destination,'menu':path,'action':label}

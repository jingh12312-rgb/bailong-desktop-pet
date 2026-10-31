"""Platform paths and optional macOS desktop integration."""
import os
import sys
from pathlib import Path

def xdg_path(variable, fallback):
    value=os.environ.get(variable,'')
    return Path(value) if value and Path(value).is_absolute() else Path.home()/fallback

def resource_root():
    if not getattr(sys,'frozen',False):return Path(__file__).resolve().parents[1]
    executable=Path(sys.executable).resolve()
    return executable.parents[1]/'Resources' if sys.platform=='darwin' else executable.parent

def user_data():
    if os.environ.get('BAILONG_DATA_DIR'):return Path(os.environ['BAILONG_DATA_DIR'])
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/BailongPet'
    if sys.platform.startswith('linux'):
        return xdg_path('XDG_DATA_HOME','.local/share')/'BailongPet'
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')/'BailongPet'

def state_root():
    if sys.platform.startswith('linux'):
        if os.environ.get('BAILONG_DATA_DIR'):return user_data()
        return xdg_path('XDG_STATE_HOME','.local/state')/'BailongPet'
    return user_data() if sys.platform=='darwin' else resource_root()

def cache_root():
    if sys.platform.startswith('linux'):
        return xdg_path('XDG_CACHE_HOME','.cache')/'BailongPet/frame_cache'
    return resource_root()/'app/cache'

def configure_mac_window(widget):
    if sys.platform!='darwin':return
    try:
        import objc
        from AppKit import NSWindowCollectionBehaviorCanJoinAllSpaces,NSWindowCollectionBehaviorFullScreenAuxiliary
        view=objc.objc_object(c_void_p=int(widget.winId()))
        window=view.window()
        window.setCollectionBehavior_(window.collectionBehavior()|NSWindowCollectionBehaviorCanJoinAllSpaces|NSWindowCollectionBehaviorFullScreenAuxiliary)
    except (ImportError,AttributeError,ValueError):pass

def mac_fullscreen():
    try:
        import Quartz as q
        from AppKit import NSWorkspace
        front=NSWorkspace.sharedWorkspace().frontmostApplication()
        pid=front.processIdentifier()
        if pid==os.getpid():return False
        from desktop_visibility import covers_monitor
        displays=q.CGGetActiveDisplayList(32,None,None)[1]
        monitors=[]
        for display in displays:
            r=q.CGDisplayBounds(display);monitors.append((r.origin.x,r.origin.y,r.origin.x+r.size.width,r.origin.y+r.size.height))
        for w in q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly|q.kCGWindowListExcludeDesktopElements,q.kCGNullWindowID) or []:
            if w.get(q.kCGWindowOwnerPID)!=pid or w.get(q.kCGWindowLayer)!=0:continue
            b=w[q.kCGWindowBounds];r=(b['X'],b['Y'],b['X']+b['Width'],b['Y']+b['Height'])
            return any(covers_monitor(r,m) for m in monitors)
    except (ImportError,AttributeError,KeyError,TypeError):pass
    return False

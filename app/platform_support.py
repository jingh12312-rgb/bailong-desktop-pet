"""Platform paths and optional macOS desktop integration."""
import os
import sys
from pathlib import Path

def resource_root():
    if not getattr(sys,'frozen',False):return Path(__file__).resolve().parents[1]
    executable=Path(sys.executable).resolve()
    return executable.parents[1]/'Resources' if sys.platform=='darwin' else executable.parent

def user_data():
    if os.environ.get('BAILONG_DATA_DIR'):return Path(os.environ['BAILONG_DATA_DIR'])
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/BailongPet'
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')/'BailongPet'

def state_root():
    return user_data() if sys.platform=='darwin' else resource_root()

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

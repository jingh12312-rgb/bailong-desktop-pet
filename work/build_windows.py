from pathlib import Path
import sys,subprocess,shutil,json
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'.build-tools'));sys.path.insert(0,str(root/'app'))
from version import VERSION
import PyInstaller.__main__
PyInstaller.__main__.run(['--noconfirm','--clean','--onedir','--windowed','--name','BailongPet','--distpath',str(root/'发布包'/f'build-v{VERSION}'),'--workpath',str(root/'.build'/f'work-v{VERSION}'),'--specpath',str(root/'.build'),'--exclude-module','numpy','--exclude-module','scipy','--exclude-module','matplotlib','--exclude-module','tkinter','--exclude-module','PyQt5','--exclude-module','PyQt6','--hidden-import','autostart','--hidden-import','selftest','--hidden-import','version',str(root/'app/pet.py')])

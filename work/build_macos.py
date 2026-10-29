from pathlib import Path
import sys,subprocess,shutil,json
root=Path(__file__).resolve().parents[1]
if sys.platform!='darwin':raise SystemExit('必须在Mac上运行；本脚本不生成Windows包。')
# Install requirements-macos.txt in a clean virtual environment first.
import PyInstaller.__main__
PyInstaller.__main__.run(['--noconfirm','--clean','--windowed','--name','BailongPet','--osx-bundle-identifier','com.bailongpet.desktop','--distpath',str(root/'dist-macos'),'--workpath',str(root/'.build-macos'),'--specpath',str(root/'.build-macos'),'--hidden-import','autostart','--hidden-import','mac_autostart','--hidden-import','selftest','--hidden-import','AppKit','--hidden-import','Quartz','--hidden-import','PySide6.QtMultimedia',str(root/'app/pet.py')])
resources=root/'dist-macos/BailongPet.app/Contents/Resources'
assets=root/'outputs/白龙桌宠素材';dest=resources/'outputs/白龙桌宠素材';dest.mkdir(parents=True,exist_ok=True)
m=json.loads((assets/'素材清单.json').read_text(encoding='utf-8'))
items=[m['idle']]+m.get('additionalIdleAnimations',[])+m['variants']+[v for v in m.get('workAnimations',[]) if v]+m.get('movementAnimations',[])+[m[k] for k in ('dragAnimation','landingAnimation','quotaAnimation') if m.get(k)]
for v in items:
 rel=v.get('playbackFile') or v['file'].replace('.webm','.webp');target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(assets/rel,target)
 if v.get('returnTransition'):
  rel=v['returnTransition']['file'];target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(assets/rel,target)
for v in items:v.pop('source',None)
(resources/'app').mkdir(exist_ok=True);shutil.copytree(root/'app/sounds',resources/'app/sounds',dirs_exist_ok=True)
(dest/'素材清单.json').write_text(json.dumps(m,ensure_ascii=False),encoding='utf-8')
import plistlib
p=root/'dist-macos/BailongPet.app/Contents/Info.plist';data=plistlib.loads(p.read_bytes());data['LSUIElement']=True;p.write_bytes(plistlib.dumps(data))
# Re-sign after resources/plist changes. Ad-hoc signing is for local testing only.
subprocess.run(['codesign','--force','--deep','--sign','-',str(root/'dist-macos/BailongPet.app')],check=True)
print('生成了本机构架的未公证测试.app。公开发布前必须进行Mac实机验收、正式签名和公证。')

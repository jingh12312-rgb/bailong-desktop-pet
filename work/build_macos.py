"""Build a self-contained macOS app on the current Mac architecture."""
from pathlib import Path
import json
import os
import platform
import shutil
import subprocess
import sys
import plistlib

if sys.platform != 'darwin':
    raise SystemExit('Build this application on macOS.')

import imageio_ffmpeg
import PyInstaller.__main__
from PIL import Image

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'app'))
from video_frames import rgba_frames

assets = root / 'outputs/白龙桌宠素材'
manifest = json.loads((assets / '素材清单.json').read_text(encoding='utf-8'))
ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
decoders = subprocess.check_output([str(ffmpeg), '-hide_banner', '-decoders'], text=True)
if 'libvpx-vp9' not in decoders:
    raise SystemExit('FFmpeg must include the libvpx-vp9 alpha decoder.')

build = root / '.build-macos'
build.mkdir(exist_ok=True)
staged_assets = build / 'assets'
if staged_assets.exists():
    shutil.rmtree(staged_assets)
staged_assets.mkdir()
items = ([manifest['idle']] + manifest.get('additionalIdleAnimations', [])
         + manifest['variants'] + [v for v in manifest.get('workAnimations', []) if v]
         + manifest.get('movementAnimations', [])
         + [manifest[k] for k in ('dragAnimation', 'landingAnimation', 'quotaAnimation')
            if manifest.get(k)])
for item in items:
    files = [item.get('playbackFile') or item['file'].replace('.webm', '.webp')]
    if item.get('returnTransition'):
        files.append(item['returnTransition']['file'])
    for relative in files:
        target = staged_assets / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assets / relative, target)
    item.pop('source', None)
(staged_assets / '素材清单.json').write_text(
    json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
idle = manifest['idle']
frames = rgba_frames(assets / (idle.get('playbackFile') or idle['file']), 512)
try:
    icon = Image.frombytes('RGBA', (512, 512), next(frames))
finally:
    frames.close()
icon_path = build / 'BailongPet.icns'
icon.save(icon_path)

# A stable name lets the runtime locate its bundled decoder without PATH.
tools = build / 'tools'
tools.mkdir(exist_ok=True)
decoder = tools / 'ffmpeg'
shutil.copy2(ffmpeg, decoder)
decoder.chmod(0o755)
destination = Path(os.environ.get('BAILONG_DIST_DIR', str(root / 'dist-macos')))
PyInstaller.__main__.run([
    '--noconfirm', '--clean', '--windowed', '--name', 'BailongPet',
    '--osx-bundle-identifier', 'com.bailongpet.desktop',
    '--target-architecture', platform.machine(), '--icon', str(icon_path),
    '--distpath', str(destination), '--workpath', str(build / 'work'),
    '--specpath', str(build), '--log-level', 'WARN',
    '--exclude-module', 'imageio_ffmpeg',
    '--hidden-import', 'autostart', '--hidden-import', 'mac_autostart',
    '--hidden-import', 'selftest', '--hidden-import', 'AppKit',
    '--hidden-import', 'Quartz', '--hidden-import', 'PySide6.QtMultimedia',
    '--add-binary', f'{decoder}:tools',
    '--add-data', f'{staged_assets}:outputs/白龙桌宠素材',
    '--add-data', f'{root / "app/sounds"}:app/sounds',
    str(root / 'app/pet.py'),
])

bundle = destination / 'BailongPet.app'
plist = bundle / 'Contents/Info.plist'
info = plistlib.loads(plist.read_bytes())
info.update(LSUIElement=True, CFBundleDisplayName='白龙桌宠',
            CFBundleShortVersionString='0.5.1', CFBundleVersion='0.5.1.1')
plist.write_bytes(plistlib.dumps(info))
subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(bundle)], check=True)
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
print(f'Built local {platform.machine()} app: {bundle}')

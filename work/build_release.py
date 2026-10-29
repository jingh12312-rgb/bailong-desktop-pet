"""Create an audited source ZIP and a self-contained Windows onedir ZIP."""
from pathlib import Path
from importlib.metadata import distribution
import ast,html,json,shutil,zipfile,hashlib,sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from version import VERSION
OUT=ROOT/'发布包'
webm=json.loads((ROOT/'outputs/白龙桌宠素材/素材清单.json').read_text(encoding='utf-8'))['idle'].get('playbackFile','').endswith('.webm')
edition='-webm' if webm else ''
stage=OUT/f'release-v{VERSION}{edition}'
source=stage/'repository/bailong-desktop-pet';portable=stage/'windows/BailongPet'
source.mkdir(parents=True,exist_ok=True);(source/'app').mkdir(exist_ok=True)
modules=['platform_support.py','mac_autostart.py','test_platform_support.py','test_preferences.py','desktop_task_sync.py','test_desktop_task_sync.py','pet.py','movement.py','test_movement.py','quota.py','autostart.py','prepare_assets.py','test_pet.py','selftest.py','version.py','test_quota.py','chat_backend.py','chat_ui.py','test_chat.py','desktop_visibility.py','test_visibility.py','test_session_reuse.py','test_task_notifications.py']
modules.append('video_frames.py')
for name in modules:shutil.copy2(ROOT/'app'/name,source/'app'/name)
shutil.copytree(ROOT/'app/sounds',source/'app/sounds',dirs_exist_ok=True)
guide=(ROOT/'work/release_readme.txt').read_text(encoding='utf-8')
if webm:guide=guide.replace('windows-x64.zip','windows-x64-webm.zip')+'\n透明WebM轻量版：动画保留原分辨率与帧率；tools文件夹包含必需的透明视频解码器，请一起保留。\n'
readme='# GPT白龙娘动态桌宠 '+VERSION+'\n\n普通使用者请下载Releases里的 **bailong-desktop-pet-v'+VERSION+'-windows-x64.zip**。解压后双击BailongPet.exe；无需Python。\n\n'+guide
(source/'README.md').write_text(readme,encoding='utf-8')
(source/'先看我-安装说明.txt').write_text(guide,encoding='utf-8-sig')
(source/'requirements.txt').write_text('PySide6==6.9.2\nPillow==12.0.0\npsutil==7.0.0\n',encoding='utf-8')
(source/'.gitignore').write_text('.venv/\n__pycache__/\n*.pyc\napp/cache/\napp/*状态.json\napp/*.jsonl\noutputs/\n发布包/\n.build*/\n*.zip\n检查报告.json\n检查预览.png\n',encoding='utf-8')
(source/'DEVELOPMENT.md').write_text(r'''# 开发者说明

普通用户请用windows-x64.zip。此仓库压缩包不含动画、Python及Qt运行环境。
开发者需安装64位Python，并将完整包的outputs文件夹复制到此目录。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app\prepare_assets.py
.venv\Scripts\python.exe app\pet.py
.venv\Scripts\python.exe app\test_pet.py
```

复刻EXE可安装PyInstaller 6.22.3，使用onedir/windowed模式，以app/pet.py作为入口，显式包含autostart、selftest、version模块。Windows包必须在Windows构建。
程序支持--autostart、--enable-autostart、--disable-autostart、--self-test。
所有播放路径相对发行目录。renderScale和renderOffset控制固定显示校准。
源码未指定开源许可证，美术许可见ASSETS.md。
''',encoding='utf-8')
(source/'ASSETS.md').write_text('素材随Releases发布，不纳入Git历史。35段动画来自项目作者提供的角色素材及透明处理版本。未额外授予美术素材商用或再分发许可。\n',encoding='utf-8')
(source/'RELEASE_NOTES.md').write_text(f'''白龙桌宠 v{VERSION}

普通用户下载windows-x64.zip，全部解压后双击BailongPet.exe。
已包含Python、Qt、图像和进程处理依赖、35段动画、点击音效及中文入门说明。
新增系统托盘、隐藏/显示桌宠、可开关的全屏自动隐藏，保留查询、拖拽、落地和屏幕边界限制。
任务输入框、开启新对话、本机历史、公开思考摘要/执行进度实时显示、可滚动完整结果与详情。
任务成功时播放一次点击音效和庆祝动画。工作01仅任务开场一次并显示收到提示；其余工作与待机按35:65分组选播，组内等概率并避免连续重复。
15项互动与5项工作均可单击互动，手动工作动作显示台词，自动工作无动作台词。所有动作启动预加载。
基础两套待机平时4:1播放；新增待机03—06与六个移动动作按15秒规则交替，工作动作5项已接入，剩余1槽。
对话功能需要使用者自己的Codex安装、登录与网络；对话历史不随包分发。
额度查询需要使用者自己安装Codex并登录；离线动作无需账号。
此发布包仅Windows x64。macOS适配代码待实机验收，不含Mac安装包。Linux/32位Windows不支持；Windows ARM未验证。
''',encoding='utf-8')

build=OUT/f'build-v{VERSION}/BailongPet'
assert (build/'BailongPet.exe').is_file(),'先生成EXE'
shutil.copytree(build,portable,dirs_exist_ok=True)
if webm:
    (portable/'tools').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'work/video-deps/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe',portable/'tools/ffmpeg.exe')
(portable/'app').mkdir(exist_ok=True)
shutil.copytree(ROOT/'app/sounds',portable/'app/sounds',dirs_exist_ok=True)
assets=ROOT/'outputs/白龙桌宠素材';dest=portable/'outputs/白龙桌宠素材';dest.mkdir(parents=True,exist_ok=True)
m=json.loads((assets/'素材清单.json').read_text(encoding='utf-8'))
lean={k:m[k] for k in ('version','character','idle','additionalIdleAnimations','variants','dragAnimation','landingAnimation','quotaAnimation')}
lean['workAnimations']=m.get('workAnimations',[])[:6]
lean['movementAnimations']=m.get('movementAnimations',[])
items=[lean['idle']]+lean['additionalIdleAnimations']+lean['variants']+[lean[k] for k in ('dragAnimation','landingAnimation','quotaAnimation')]+[v for v in lean['workAnimations'] if v]+lean['movementAnimations']
for item in items:
    relative=item.get('playbackFile') or item['file'].replace('.webm','.webp')
    target=dest/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(assets/relative,target)
    item['file']=relative;item['playbackFile']=relative;item.pop('source',None)
    for key in ('previousFile','pendingReturnTransition','revision'):item.pop(key,None)
    if item.get('returnTransition'):
        bridge=item['returnTransition']['file'];bridge_dest=dest/bridge
        bridge_dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(assets/bridge,bridge_dest)
(dest/'素材清单.json').write_text(json.dumps(lean,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['README.md','ASSETS.md','RELEASE_NOTES.md','先看我-安装说明.txt']:shutil.copy2(source/name,portable/name)
page='<!doctype html><meta charset="utf-8"><title>白龙桌宠安装说明</title><style>body{max-width:850px;margin:40px auto;padding:0 24px;font:17px/1.8 "Microsoft YaHei",sans-serif;color:#453950;background:#fbf8fe}pre{white-space:pre-wrap;font:inherit}</style><pre>'+html.escape(guide)+'</pre>'
(portable/'先看我-安装说明.html').write_text(page,encoding='utf-8')
for name,flag in [('开启随GPT自动启动.cmd','--enable-autostart'),('关闭随GPT自动启动.cmd','--disable-autostart')]:
    (portable/name).write_text('@echo off\ncd /d "%~dp0"\nstart "" "%~dp0BailongPet.exe" '+flag+'\n',encoding='ascii')
(portable/'检查桌宠.cmd').write_text('@echo off\ncd /d "%~dp0"\nstart "" /wait "%~dp0BailongPet.exe" --self-test\necho See the generated report: 检查报告.json\npause\n'.replace('检查报告.json','report JSON in this folder'),encoding='ascii')

# Preserve installed dependency licenses, including native libraries that were
# actually collected by PyInstaller, rather than unrelated environment files.
licenses=portable/'licenses';licenses.mkdir(exist_ok=True)
if webm:
    import subprocess
    license_text=subprocess.check_output([str(portable/'tools/ffmpeg.exe'),'-L'],stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW).decode('utf-8',errors='replace')
    (licenses/'FFmpeg.txt').write_text(license_text+'\nBinary source: https://github.com/imageio/imageio-ffmpeg ; https://github.com/BtbN/FFmpeg-Builds\n',encoding='utf-8')
python_license=Path(sys.prefix)/'LICENSE_PYTHON.txt'
if python_license.exists():shutil.copy2(python_license,licenses/'Python.txt')
for name in ['Pillow','psutil','PySide6','shiboken6']:
    dist=distribution(name)
    for file in dist.files or []:
        if 'license' in str(file).lower() or 'copying' in str(file).lower():
            p=dist.locate_file(file)
            if p.is_file():target=licenses/name/p.name;target.parent.mkdir(exist_ok=True);shutil.copy2(p,target)
toc=ast.literal_eval((ROOT/'.build'/f'work-v{VERSION}/BailongPet/Analysis-00.toc').read_text(encoding='utf-8'))
paths=set()
def walk(value):
    if isinstance(value,str) and value.lower().startswith(str(Path(sys.prefix)).lower()):paths.add(str(Path(value)).lower())
    elif isinstance(value,(tuple,list)): 
        for v in value:walk(v)
walk(toc)
collected=[]
for meta in (Path(sys.prefix)/'conda-meta').glob('*.json'):
    data=json.loads(meta.read_text(encoding='utf-8'))
    if any(str(Path(sys.prefix)/file).lower() in paths for file in data.get('files',[])):
        name=f"{data['name']}-{data['version']}-{data['build']}";folder=Path(sys.prefix)/'pkgs'/name/'info/licenses'
        if folder.is_dir():shutil.copytree(folder,licenses/name,dirs_exist_ok=True)
        collected.append({'name':data['name'],'version':data['version'],'license':data.get('license'),'licenseFilesIncluded':folder.is_dir()})
(licenses/'components.json').write_text(json.dumps(collected,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(ROOT/'app/sounds/Kenney-License.txt',licenses/'Kenney-License.txt')
pyi_license=ROOT/'.build-tools/pyinstaller-6.22.3.dist-info/licenses/COPYING.txt'
if pyi_license.exists():shutil.copy2(pyi_license,licenses/'PyInstaller-COPYING.txt')
(licenses/'说明.txt').write_text('本文件夹保留随包运行库的许可文本。源码项目和美术素材的许可另见ASSETS.md。Qt/PySide来源：https://download.qt.io/official_releases/QtForPython/ 和 https://download.qt.io/official_releases/qt/6.9/ 。\n',encoding='utf-8')

info={'version':VERSION,'architecture':'Windows x64','animationCount':len(items),'sourceSHA256':{name:hashlib.sha256((ROOT/'app'/name).read_bytes()).hexdigest() for name in modules}}
for folder in [source,portable]:
    (folder/'VERSION.txt').write_text(VERSION+'\n',encoding='ascii')
    (folder/'BUILD_INFO.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')

archives=[]
for folder,suffix in [(portable,'windows-x64'+edition)]:
    zip_path=OUT/f'bailong-desktop-pet-v{VERSION}-{suffix}.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zip:
        for p in sorted(folder.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.name not in ('运行状态.json','自启动状态.json','检查报告.json','检查预览.png','额度查询日志.jsonl','conversations.json','conversations.tmp'):
                zip.write(p,p.relative_to(folder.parent))
    with zipfile.ZipFile(zip_path) as zip:assert zip.testzip() is None
    archives.append(zip_path);print(zip_path.name,round(zip_path.stat().st_size/1048576,2),'MiB',flush=True)
(OUT/f'SHA256SUMS-v{VERSION}{edition}.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in archives),encoding='ascii')

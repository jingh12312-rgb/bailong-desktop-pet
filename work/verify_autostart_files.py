"""验证隔离的 .desktop/systemd 配置；不安装入口或调用 systemctl。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import linux_autostart


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.output.absolute();root.mkdir(parents=True,exist_ok=True)
    with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(args.executable.absolute())):
        desktop=root/'bailong-pet-monitor.desktop';desktop.write_text(linux_autostart._desktop_text())
        service=root/'bailong-pet-monitor.service';service.write_text(linux_autostart._service_text())
    report={'passed':True,'checks':[],'scope':'只生成隔离文件并验证语法；未安装自启动、未启动用户服务'}
    for command in (['desktop-file-validate',str(desktop)],['systemd-analyze','--user','verify',str(service)]):
        result=subprocess.run(command,capture_output=True,text=True,timeout=20)
        report['checks'].append({'tool':command[0],'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        report['passed']=report['passed'] and result.returncode==0
    (root/'config-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':sys.exit(main())

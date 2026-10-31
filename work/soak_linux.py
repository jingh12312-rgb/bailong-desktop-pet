"""对全新解压包进行有时间戳的持续运行检查，默认30分钟。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime,timezone
import psutil
from tray_test_client import tray_action


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seconds',type=int,default=1800)
    args=parser.parse_args();output=args.output.absolute();output.mkdir(parents=True,exist_ok=True)
    # Refuse an unrelated pet; never stop another installation.
    active=[]
    for p in psutil.process_iter(['pid','name','cmdline']):
        cmd=p.info.get('cmdline') or []
        if p.info.get('name')=='BailongPet' or len(cmd)>1 and cmd[1].endswith('/app/pet.py'):active.append(p.info['pid'])
    if active:raise RuntimeError('已有同类实例：'+str(active))
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    env.update(BAILONG_DATA_DIR=str(output/'runtime/data'),XDG_CONFIG_HOME=str(output/'runtime/config'),XDG_CACHE_HOME=str(output/'runtime/cache'))
    config=Path(env['XDG_CONFIG_HOME'])/'BailongPet/DesktopPet.conf';config.parent.mkdir(parents=True,exist_ok=True)
    config.write_text('[General]\nsyncCodexTasks=false\nsoundDisabled=true\n')
    state=Path(env['BAILONG_DATA_DIR'])/'app';log=(output/'application.log').open('wb')
    process=subprocess.Popen([str(args.executable.absolute())],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    log.close();owner=psutil.Process(process.pid);report={'passed':False,'pid':process.pid,'requested_seconds':args.seconds,'started_utc':datetime.now(timezone.utc).isoformat(),'samples':[]}
    pointer=None
    def snapshot():
        for _ in range(20):
            try:return json.loads((state/'显示诊断.json').read_text())
            except (OSError,ValueError):time.sleep(.05)
        raise RuntimeError('无法读取界面诊断')
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('启动提前退出')
            try:
                data=json.loads((state/'显示诊断.json').read_text())
                if data.get('pid')==process.pid:break
            except (OSError,ValueError):pass
            time.sleep(.2)
        else:raise TimeoutError('启动诊断超时')
        started=time.monotonic();owner.cpu_percent(None)
        while True:
            elapsed=time.monotonic()-started
            if process.poll() is not None:raise RuntimeError('持续运行期间程序提前退出')
            data=snapshot()
            if data.get('pid')!=process.pid or time.time()-(state/'显示诊断.json').stat().st_mtime>10:raise RuntimeError('界面诊断心跳已停止')
            children=[{'pid':p.pid,'name':p.name(),'pgid':os.getpgid(p.pid)} for p in owner.children(recursive=True)]
            sample={'elapsed_seconds':round(elapsed,2),'cpu_percent':owner.cpu_percent(None),'rss_mib':round(owner.memory_info().rss/1024**2,2),'position':data['position'],'visible':data['visible'],'children':children}
            report['samples'].append(sample)
            (output/'soak-progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps(sample,ensure_ascii=False),flush=True)
            if elapsed>=args.seconds:break
            time.sleep(min(30,args.seconds-elapsed))
        report['actual_seconds']=round(time.monotonic()-started,2)
        tray_action(process.pid,'退出桌宠')
        report['normal_exit']=process.wait(timeout=10)==0
        report['passed']=report['normal_exit'] and report['actual_seconds']>=args.seconds
    except BaseException:
        import traceback;report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        report['ended_utc']=datetime.now(timezone.utc).isoformat();report['remaining_pid']=psutil.pid_exists(process.pid)
        if report['remaining_pid']:report['passed']=False
        if pointer:subprocess.run(['xdotool','mousemove',pointer['X'],pointer['Y']],check=False,timeout=5)
        (output/'soak-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

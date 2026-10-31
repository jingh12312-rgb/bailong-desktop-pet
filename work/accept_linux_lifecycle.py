"""验收本轮包的并发启动、崩溃恢复和监视器；不操作用户真实配置。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
from tray_test_client import tray_action


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();exe=args.executable.absolute();output=args.output.absolute();output.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    env.update(BAILONG_DATA_DIR=str(output/'runtime/data'),XDG_CONFIG_HOME=str(output/'runtime/config'),XDG_CACHE_HOME=str(output/'runtime/cache'))
    state=Path(env['BAILONG_DATA_DIR'])/'app';owned=[];pet_children=[];report={'passed':False,'checks':[]}
    def check(name,value=True,**extra):
        if not value:raise AssertionError(name)
        report['checks'].append({'name':name,**extra});print(name,flush=True)
    def launch(*extra):
        file=(output/f'process-{len(owned)+1}.log').open('wb')
        process=subprocess.Popen([str(exe),*extra],env=env,stdout=file,stderr=subprocess.STDOUT,start_new_session=True)
        file.close();owned.append(process);return process
    def wait_json(path,predicate,timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                data=json.loads(path.read_text())
                if predicate(data):return data
            except (OSError,ValueError):pass
            time.sleep(.15)
        raise TimeoutError(str(path))
    def ready(process):return wait_json(state/'运行状态.json',lambda d:d.get('pid')==process.pid and process.poll() is None)
    def menu_exit(pid):
        wait_json(state/'显示诊断.json',lambda d:d.get('pid')==pid)
        tray_action(pid,'退出桌宠')
        handle=next((p for p in owned if p.pid==pid),None)
        if handle:
            if handle.wait(timeout=8)!=0:raise RuntimeError('菜单退出返回异常状态')
        else:
            try:psutil.Process(pid).wait(timeout=8)
            except psutil.NoSuchProcess:pass
    try:
        existing=[]
        for p in psutil.process_iter(['pid','name','cmdline']):
            if p.info['pid']==os.getpid():continue
            command=p.info.get('cmdline') or []
            if p.info.get('name')=='BailongPet' or len(command)>1 and command[1].endswith('/app/pet.py'):existing.append(p.info['pid'])
        check('启动前没有同类桌宠',not existing)
        a=launch();b=launch();deadline=time.monotonic()+10
        while a.poll() is None and b.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        exited=[p for p in (a,b) if p.poll() is not None]
        living=[p for p in (a,b) if p.poll() is None]
        if len(exited)!=1 or len(living)!=1:raise RuntimeError('并发启动没有形成一个活动实例')
        loser=exited[0];winner=living[0]
        check('并发启动只保留一个实例',loser.wait(timeout=10)==0 and winner.poll() is None)
        ready(winner);third=launch();check('再次启动返回且保留原PID',third.wait(timeout=10)==0 and winner.poll() is None)
        old_pid=winner.pid;winner.terminate();winner.wait(timeout=5)
        check('异常退出后的锁自动释放',not psutil.pid_exists(old_pid))
        restarted=launch();ready(restarted);check('异常退出后可重新启动',restarted.poll() is None)
        menu_exit(restarted.pid);restarted.wait(timeout=5);check('真实菜单正常退出',restarted.returncode==0)
        # The real desktop application is already open; do not close it for testing.
        monitor=launch('--autostart')
        record=wait_json(state/'自启动状态.json',lambda d:d.get('pid')==monitor.pid and bool(d.get('petPid')))
        child_pid=record['petPid'];wait_json(state/'运行状态.json',lambda d:d.get('pid')==child_pid and psutil.pid_exists(child_pid))
        pet_children.append((child_pid,psutil.Process(child_pid).create_time()))
        check('当前会话监视器识别桌面应用并启动桌宠',record.get('gptOpen') is True,monitor_pid=monitor.pid,pet_pid=child_pid)
        second_monitor=launch('--autostart');check('第二个监视器不重复启动',second_monitor.wait(timeout=10)==0)
        menu_exit(child_pid);time.sleep(3)
        check('用户退出后不会循环拉起',not psutil.pid_exists(child_pid) or psutil.Process(child_pid).status()==psutil.STATUS_ZOMBIE)
        monitor.terminate();monitor.wait(timeout=5);check('监视器已退出',not psutil.pid_exists(monitor.pid))
        report['passed']=True
    except BaseException:
        import traceback;report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        for pid,created in pet_children:
            try:
                child=psutil.Process(pid)
                if abs(child.create_time()-created)<.01 and child.status()!=psutil.STATUS_ZOMBIE:
                    child.terminate()
                    try:child.wait(timeout=5)
                    except psutil.TimeoutExpired:child.kill()
            except psutil.NoSuchProcess:pass
        for process in owned:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        remaining=[]
        for p in psutil.process_iter(['pid','name','cmdline']):
            if p.info.get('name')=='BailongPet':remaining.append(p.info['pid'])
        report['remaining_pet_pids']=remaining
        if remaining:report['passed']=False
        (output/'lifecycle-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':sys.exit(main())

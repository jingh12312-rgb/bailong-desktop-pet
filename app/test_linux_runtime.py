"""Linux 回归：登录路径、实例竞争、进程树和测试模型约束。"""
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import linux_runtime as runtime
import platform_support as paths
import quota
from chat_backend import CodexSession
from video_frames import ffmpeg_path


@unittest.skipUnless(sys.platform.startswith('linux'),'Linux only')
class RuntimeTests(unittest.TestCase):
    def test_relative_xdg_paths_are_ignored(self):
        with patch.dict(os.environ,{'XDG_STATE_HOME':'relative','XDG_CACHE_HOME':'relative','BAILONG_DATA_DIR':''}):
            self.assertEqual(paths.state_root(),Path.home()/'.local/state/BailongPet')
            self.assertEqual(paths.cache_root(),Path.home()/'.cache/BailongPet/frame_cache')

    def test_fnm_discovery_with_minimal_login_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for version in ('v9.1.0','v24.15.0'):
                executable=root/'.local/share/fnm/node-versions'/version/'installation/bin/codex'
                executable.parent.mkdir(parents=True);executable.write_text('#!/bin/sh\nexit 0\n');executable.chmod(0o700)
            with patch.dict(os.environ,{'PATH':'/usr/bin:/bin','BAILONG_CODEX':'','USERPROFILE':folder}),patch.object(quota.shutil,'which',return_value=None):
                found=quota.find_codex()
            self.assertIn('v24.15.0',found)
            env=runtime.child_environment(found)
            self.assertEqual(env['PATH'].split(os.pathsep)[0],str(Path(found).parent))

    def test_frozen_external_child_does_not_inherit_private_libraries(self):
        with patch.object(sys,'frozen',True,create=True),patch.dict(os.environ,{'LD_LIBRARY_PATH':'/bundle','LD_LIBRARY_PATH_ORIG':'/original'}):
            self.assertEqual(runtime.child_environment()['LD_LIBRARY_PATH'],'/original')

    def test_invalid_ffmpeg_override_fails_explicitly(self):
        with patch.dict(os.environ,{'BAILONG_FFMPEG':'/does/not/exist'}):
            with self.assertRaises(RuntimeError):ffmpeg_path()

    def test_desktop_renderer_is_not_an_open_main_application(self):
        import linux_autostart
        from types import SimpleNamespace
        renderer=SimpleNamespace(info={'name':'ChatGPT','exe':'/usr/lib/chatgpt/ChatGPT','cmdline':['ChatGPT','--type=renderer']})
        with patch.object(linux_autostart.psutil,'process_iter',return_value=[renderer]):
            self.assertFalse(linux_autostart.gpt_is_open())

    @unittest.skipUnless(shutil.which('gio') and shutil.which('desktop-file-validate'),'需要 GLib 桌面启动器')
    def test_desktop_exec_roundtrip_with_real_glib_parser(self):
        import json,linux_autostart
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'空 格 $HOME %test "quote" back\\slash';folder.mkdir()
            script=folder/'fixture.py';result=root/'result.json'
            script.write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n')
            values=['literal $HOME','50%','quote"value','back\\slash','literal`value']
            with patch.object(linux_autostart,'command',return_value=[sys.executable,str(script),str(result),*values]):
                entry=root/'fixture.desktop';entry.write_text(linux_autostart._desktop_text())
            subprocess.run(['desktop-file-validate',str(entry)],capture_output=True,check=True)
            subprocess.run(['gio','launch',str(entry)],capture_output=True,check=True,timeout=10)
            for _ in range(100):
                if result.exists():break
                time.sleep(.02)
            self.assertEqual(json.loads(result.read_text()),values)

    def test_singleton_lock_and_isolated_endpoint(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'BAILONG_DATA_DIR':folder}):
            first=runtime.acquire_instance()
            try:
                self.assertIsNotNone(first);self.assertIsNone(runtime.acquire_instance())
                name=runtime.instance_name()
                with patch.dict(os.environ,{'BAILONG_DATA_DIR':folder+'/other'}):self.assertNotEqual(name,runtime.instance_name())
            finally:first.close()
            second=runtime.acquire_instance();self.assertIsNotNone(second);second.close()

    def test_owned_process_group_reaps_descendants(self):
        import psutil
        code='import subprocess,time,sys; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);print(p.pid,flush=True);time.sleep(60)'
        process=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True,**runtime.child_options())
        child=int(process.stdout.readline())
        try:
            self.assertEqual(os.getpgid(child),process.pid)
            runtime.stop_child(process)
            for _ in range(20):
                if not psutil.pid_exists(child) or psutil.Process(child).status()==psutil.STATUS_ZOMBIE:break
                time.sleep(.05)
            self.assertTrue(not psutil.pid_exists(child) or psutil.Process(child).status()==psutil.STATUS_ZOMBIE)
            self.assertIsNotNone(process.returncode)
        finally:
            runtime.stop_child(process);process.stdout.close()


class ModelTests(unittest.TestCase):
    def test_explicit_model_is_passed_to_thread_and_turn(self):
        session=CodexSession('.',model='gpt-6-luna',effort='low');calls=[]
        def rpc(method,params,timeout=45):
            calls.append((method,params))
            if method=='thread/start':return {'thread':{'id':'local-test','model':'gpt-6-luna'}}
            if method=='turn/start':
                session.finished_turn={'status':'completed'}
                return {'turn':{'id':'local-turn'}}
            return {}
        with patch.object(session,'start'),patch.object(session,'send'),patch.object(session,'rpc',side_effect=rpc):session.run('offline')
        self.assertEqual(next(p for m,p in calls if m=='thread/start')['model'],'gpt-6-luna')
        turn=next(p for m,p in calls if m=='turn/start')
        self.assertEqual((turn['model'],turn['effort']),('gpt-6-luna','low'))

    def test_missing_luna_does_not_fallback(self):
        session=CodexSession('.',model='gpt-6-luna',effort='lowest');calls=[]
        def rpc(method,params,timeout=45):
            calls.append(method)
            return {'data':[]} if method=='model/list' else {}
        with patch.object(session,'start'),patch.object(session,'send'),patch.object(session,'close'),patch.object(session,'rpc',side_effect=rpc):
            with self.assertRaises(RuntimeError):session.run('offline')
        self.assertNotIn('turn/start',calls)

if __name__=='__main__':unittest.main()

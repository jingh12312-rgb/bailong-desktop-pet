import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from desktop_task_sync import DesktopTaskReader,DesktopTaskSync
app=QApplication.instance() or QApplication([])

class ReaderTests(unittest.TestCase):
 def test_public_fields_only_and_root_to_model_mapping(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);logical='11111111-1111-1111-1111-111111111111';actual='22222222-2222-2222-2222-222222222222'
   c=sqlite3.connect(root/'state_5.sqlite');c.execute('CREATE TABLE threads(id,rollout_path,title,cwd,archived,thread_source,source,updated_at)');c.execute('INSERT INTO threads VALUES(?,?,?,?,0,?,?,?)',(logical,'rollout-'+logical+'_'+actual+'.jsonl','测试任务',tmp,'user','vscode',int(time.time())));c.commit();c.close()
   c=sqlite3.connect(root/'thread_history_1.sqlite');c.execute('CREATE TABLE thread_turns(thread_id,turn_id,status,error_json,started_at,completed_at)');c.execute('CREATE TABLE thread_items(thread_id,turn_id,item_id,item_type,item_json,rollout_ordinal)');c.execute('INSERT INTO thread_turns VALUES(?,?,?,NULL,?,NULL)',(actual,'turn','inProgress',int(time.time())))
   for i,item in enumerate([{'type':'reasoning','text':'PRIVATE-MUST-NOT-SHOW','summary':['PRIVATE']},{'type':'agentMessage','phase':'analysis','text':'PRIVATE-ANALYSIS'},{'type':'agentMessage','phase':'commentary','text':'正在核对文件'},{'type':'commandExecution','status':'failed','exitCode':1,'command':'PRIVATE-COMMAND','aggregatedOutput':'PRIVATE-OUTPUT'},{'type':'agentMessage','phase':'final_answer','text':'完成结果'}]):
    c.execute('INSERT INTO thread_items VALUES(?,?,?,?,?,?)',(actual,'turn',str(i),item['type'],json.dumps(item),i))
   c.commit();c.close();rows=DesktopTaskReader(root).snapshots();self.assertEqual(len(rows),1);r=rows[0]
   self.assertEqual(r['thread'],logical);self.assertEqual(r['actual'],actual)
   self.assertEqual(r['messages'],['正在核对文件']);self.assertEqual(r['final'],'完成结果');self.assertEqual(len(r['alerts']),1)
   self.assertNotIn('PRIVATE',str(rows));self.assertEqual(DesktopTaskReader(root).snapshots({logical}),[])

class FakePet(QObject):
 def __init__(self):
  super().__init__();self.chat=None;self.settings=Mock();self.settings.value.return_value=True
  for name in ('task_started','task_finished','task_progress','task_completed','task_result'):setattr(self,name,Mock())
class SyncTests(unittest.TestCase):
 def setUp(self):
  self.now=[1000.];self.pet=FakePet();self.reader=Mock();self.sync=DesktopTaskSync(self.pet,self.reader,lambda:self.now[0]);self.sync.history=Mock();self.sync.excluded=Mock(return_value=set())
  self.r=dict(key='t:a',thread='t',actual='t',turn='a',title='任务',cwd='.',status='inProgress',error=None,started=1000,messages=[],final='',alerts=[],step='')
  self.reader.snapshots.return_value=[self.r]
 def test_start_progress_finish_dedup(self):
  self.sync.poll();self.pet.task_started.assert_called_once();self.assertIn('收到',self.pet.task_progress.call_args.args[0])
  self.now[0]+=4;self.r['messages']=['公开进度'];self.sync.poll();self.assertEqual(self.pet.task_progress.call_args.args[1],'公开进度')
  self.r.update(status='completed',final='完整结果');self.sync.poll();self.sync.poll()
  self.pet.task_completed.assert_called_once();self.assertEqual(self.pet.task_completed.call_args.args[0],'完整结果');self.pet.task_finished.assert_called_once()
 def test_failure_and_interrupted_never_celebrate(self):
  for status in ('failed','interrupted'):
   self.setUp();self.sync.poll();self.r.update(status=status,error='连接失败');self.sync.poll();self.pet.task_completed.assert_not_called();self.assertIn('还没有完成',self.pet.task_progress.call_args.args[0])
 def test_alert_not_overwritten_and_read_failure_notice(self):
  self.sync.poll();self.now[0]+=5;self.r['alerts']=[('approval','请到 Codex 确认')];self.sync.poll();self.assertEqual(self.pet.task_progress.call_args.args[1],'请到 Codex 确认')
  self.reader.snapshots.side_effect=sqlite3.OperationalError('locked')
  for i in range(10):self.sync.poll()
  self.assertIn('同步',self.pet.task_progress.call_args.args[0]);self.pet.task_completed.assert_not_called()
 def test_no_completed_history_replay_and_no_early_finish_with_parallel_tasks(self):
  self.r['status']='completed';self.sync.poll();self.pet.task_completed.assert_not_called()
  self.r['status']='inProgress';self.sync.poll();other=dict(self.r,key='t:b',turn='b');self.reader.snapshots.return_value=[self.r,other];self.sync.poll()
  self.r['status']='completed';self.sync.poll();self.pet.task_finished.assert_not_called()
  other['status']='completed';self.sync.poll();self.pet.task_finished.assert_called_once()
 def test_unchanged_reminder_has_five_minute_cooldown(self):
  self.sync.poll();self.pet.task_progress.reset_mock()
  self.now[0]+=299;self.sync.poll();self.pet.task_progress.assert_not_called()
  self.now[0]+=1;self.sync.poll();self.pet.task_progress.assert_called_once()
  self.now[0]+=299;self.sync.poll();self.pet.task_progress.assert_called_once()
  self.now[0]+=1;self.sync.poll();self.assertEqual(self.pet.task_progress.call_count,2)
  self.r['messages']=['新的公开进度'];self.sync.poll();self.assertEqual(self.pet.task_progress.call_args.args[1],'新的公开进度')
 def test_same_progress_is_not_reopened_on_other_state_updates(self):
  self.sync.poll();self.now[0]+=5;self.r['messages']=['同一段进度'];self.sync.poll()
  count=self.pet.task_progress.call_count
  self.r['step']='正在执行操作';self.sync.poll()
  self.r['step']='正在修改文件';self.sync.poll()
  self.assertEqual(self.pet.task_progress.call_count,count)
 def test_unresolved_warning_repeats_every_five_minutes_until_progress(self):
  self.sync.poll();self.now[0]+=5;self.r['alerts']=[('a','需要你确认')];self.sync.poll()
  self.pet.task_progress.reset_mock()
  self.now[0]+=299;self.sync.poll();self.pet.task_progress.assert_not_called()
  self.now[0]+=1;self.sync.poll();self.pet.task_progress.assert_called_once()
  self.r['messages']=['问题已处理，继续工作'];self.sync.poll()
  self.assertEqual(self.pet.task_progress.call_args.args[1],'问题已处理，继续工作')
  self.assertNotIn('warning',self.sync.known['t:a'])
 def test_failed_task_repeats_but_success_does_not(self):
  self.sync.poll();self.r.update(status='failed',error='失败');self.sync.poll();self.pet.task_progress.reset_mock()
  self.now[0]+=300;self.sync.poll();self.pet.task_progress.assert_called_once()
  self.r.update(status='completed',error=None,final='处理好了');self.sync.poll()
  self.assertNotIn('warning',self.sync.known['t:a'])

class DockIntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from pet import Pet
  cls.pet=Pet();cls.pet.tick.stop()
 @classmethod
 def tearDownClass(cls):cls.pet.close()
 def test_docked_start_progress_completion_failure_only_bubbles(self):
  p=self.pet;p.dock_edge='left';p.play(p.idles[0],'idle')
  with patch.object(p,'play_click_sound'):
   p.task_started();p.task_progress('主人，我收到啦！','任务已收到',lambda:None)
   self.assertEqual(p.mode,'idle');self.assertEqual(p.dock_edge,'left');self.assertTrue(p.bubble.isVisible())
   p.task_progress('主人，遇到一个问题。','请确认权限',lambda:None);self.assertEqual(p.mode,'idle')
   p.task_finished();p.task_completed('完整任务结果',lambda:None)
   self.assertEqual(p.mode,'idle');self.assertEqual(p.dock_edge,'left');self.assertEqual(p.bubble.result_view.toPlainText(),'完整任务结果')
  p.undock()
 def test_can_dock_during_active_task(self):
  p=self.pet;area=QApplication.primaryScreen().availableGeometry()
  p.task_started();p.move(area.left(),area.top()+100)
  self.assertTrue(p.try_dock());self.assertEqual(p.dock_edge,'left')
  self.assertTrue(p.task_active);self.assertEqual(p.mode,'idle')
  p.task_progress('进展','正在处理',lambda:None);self.assertTrue(p.bubble.isVisible())
  p.undock();p.task_finished()
 def test_docked_bubble_is_close_and_can_be_dismissed(self):
  from PySide6.QtCore import QRectF
  from PySide6.QtGui import QRegion
  p=self.pet;area=QApplication.primaryScreen().availableGeometry()
  for side in ('left','right'):
   p.move(area.left() if side=='left' else area.right()+1-p.width(),area.center().y()-p.height()//2)
   p.dock_edge=side;p.dock_started=time.monotonic()-1
   p.task_progress('主人，进度来了。','测试进展',lambda:None)
   pixmap=p.grab();b=QRegion(pixmap.mask()).boundingRect();r=pixmap.devicePixelRatio()
   visible=QRectF(b.x()/r,b.y()/r,b.width()/r,b.height()/r).toAlignedRect().translated(p.pos())
   gap=p.bubble.x()-visible.right()-1 if side=='left' else visible.left()-p.bubble.frameGeometry().right()-1
   self.assertGreaterEqual(gap,0);self.assertLessEqual(gap,8)
   self.assertTrue(p.bubble.close_button.isVisible())
   p.task_active=True;p.bubble.close_button.click()
   self.assertFalse(p.bubble.isVisible());self.assertFalse(p.bubble_timer.isActive());self.assertTrue(p.task_active)
   p.task_active=False;p.undock()
 def test_pose_changes_select_the_right_animation_policy(self):
  p=self.pet;area=QApplication.primaryScreen().availableGeometry();p.task_started()
  p.move(area.left(),area.top()+100);self.assertTrue(p.try_dock())
  with patch('pet.random.choices',return_value=[p.idles[0]]) as choice:
   p.idle();self.assertEqual(choice.call_args.kwargs['weights'],[7,3])
  p.begin_undock();start=p.dock_exit[0];work=p.regular_work_animations()
  with patch('pet.time.monotonic',return_value=start+.31),patch('pet.random.choices',return_value=[('working',work)]),patch('pet.random.choice',return_value=work[0]):p.animate()
  self.assertIsNone(p.dock_edge);self.assertEqual(p.mode,'working')
  p.move(area.left(),area.top()+100);self.assertTrue(p.try_dock());p.task_finished()
  with patch.object(p,'play_click_sound'):p.task_completed('完成',lambda:None)
  self.assertEqual(p.mode,'idle');self.assertEqual(p.dock_edge,'left')
  p.begin_undock();start=p.dock_exit[0]
  with patch('pet.time.monotonic',return_value=start+.31):p.animate()
  self.assertIsNone(p.dock_edge);self.assertEqual(p.mode,'idle');self.assertFalse(p.task_active)

if __name__=='__main__':unittest.main()

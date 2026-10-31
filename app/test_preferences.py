import os,sys
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from pet import Pet
from desktop_task_sync import problem_summary
app=QApplication.instance() or QApplication([])
class PreferencesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.pet=Pet();cls.pet.tick.stop()
 @classmethod
 def tearDownClass(cls):cls.pet.close()
 def setUp(self):
  p=self.pet;self.old=(p.bubble_percent,p.task_bubbles_disabled,p.sound_disabled)
  self.save=patch.object(p.settings,'setValue');self.save.start();p.task_bubbles_disabled=False;p.sound_disabled=False;p.bubble.hide()
 def tearDown(self):
  p=self.pet;p.bubble_percent,p.task_bubbles_disabled,p.sound_disabled=self.old;p.bubble.set_scale_percent(p.bubble_percent);p.bubble.hide()
  if hasattr(p,'bubble_settings_dialog'):p.bubble_settings_dialog.hide()
  self.save.stop()
 def test_bubble_size_dialog_live_reset_and_fixed_position(self):
  p=self.pet;p.task_progress('主人，正在处理','进展内容',lambda:None);p.show_bubble_settings()
  self.assertEqual((p.bubble_slider.minimum(),p.bubble_slider.maximum()),(50,150));pos=p.bubble_settings_dialog.pos()
  p.bubble_slider.setValue(50);self.assertEqual(p.bubble.width(),150)
  p.bubble_slider.setValue(150);self.assertEqual(p.bubble.width(),450)
  self.assertEqual(p.bubble_settings_dialog.pos(),pos)
  p.bubble_reset.click();self.assertEqual(p.bubble_percent,100);self.assertEqual(p.bubble_slider.value(),100);self.assertEqual(p.bubble.width(),300)
  self.assertTrue(p.bubble.close_button.isVisible())
 def test_blank_preview_is_temporary_and_real_bubbles_survive(self):
  p=self.pet;p.bubble.hide();p.show_bubble_settings()
  self.assertTrue(p.bubble.is_size_preview);self.assertTrue(p.bubble.isVisible())
  p.bubble_slider.setValue(150);self.assertEqual(p.bubble.width(),450)
  p.bubble_settings_dialog.reject();self.assertFalse(p.bubble.isVisible());self.assertFalse(p.bubble.is_size_preview)
  p.show_bubble_settings();self.assertTrue(p.bubble.is_size_preview)
  p.task_progress('主人，进度更新','真实任务进展',lambda:None)
  p.bubble_settings_dialog.accept();self.assertTrue(p.bubble.isVisible());self.assertFalse(p.bubble.is_size_preview)
  self.assertEqual(p.bubble.result_view.toPlainText(),'真实任务进展')
  p.show_bubble_settings();self.assertFalse(p.bubble.is_size_preview)
  p.bubble_settings_dialog.reject();self.assertTrue(p.bubble.isVisible())
 def test_task_mute_keeps_interaction_and_quota(self):
  p=self.pet;p.task_progress('进展','处理任务',lambda:None);self.assertTrue(p.bubble.isVisible())
  p.set_task_bubbles_disabled(True);self.assertFalse(p.bubble.isVisible())
  p.task_progress('新进展','不显示',lambda:None);p.task_result('任务完成','不显示',lambda:None);self.assertFalse(p.bubble.isVisible())
  p.say('互动气泡');self.assertTrue(p.bubble.isVisible());p.dismiss_bubble()
  p.bubble.quota([{'name':'5小时','remaining':70,'resetsAt':None}]);self.assertTrue(p.bubble.isVisible())
  p.set_task_bubbles_disabled(True);self.assertTrue(p.bubble.isVisible())
 def test_sound_mute_and_menu_options(self):
  p=self.pet;p.set_sound_disabled(True)
  if sys.platform=='win32':
   with patch('winsound.PlaySound') as sound:p.play_click_sound();sound.assert_not_called()
  else:p.play_click_sound()
  menu=p.context_menu();names=[a.text() for a in menu.actions() if not a.isSeparator()]
  self.assertIn('对话框大小…',names);self.assertIn('桌宠大小…',names)
  toggle=next(a for a in menu.actions() if a.text()=='禁用音效');self.assertTrue(toggle.isChecked())
  self.assertEqual(names[-1],'退出桌宠');menu.deleteLater()
 def test_progress_title_reflows_when_updated(self):
  p=self.pet;p.set_bubble_percent(150)
  p.task_progress('短标题','进度内容',lambda:None)
  p.task_progress('主人，这一步需要的文件和资料已经准备好，接下来继续认真处理。','新进度',lambda:None)
  app.processEvents();title=p.bubble.result_title
  self.assertGreaterEqual(title.height(),title.heightForWidth(title.width()))
 def test_exception_summary_is_specific_and_redacts_secrets(self):
  text=problem_summary("Traceback:\nFileNotFoundError: [Errno 2] No such file: test.png\nAuthorization: Bearer SECRET",1)
  self.assertIn('文件或路径不存在',text);self.assertIn('test.png',text);self.assertNotIn('SECRET',text)
  self.assertIn('网络连接异常',problem_summary('Error: connection reset by peer'))
if __name__=='__main__':unittest.main()

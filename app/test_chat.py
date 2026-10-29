import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from chat_backend import HistoryStore, CodexSession, TaskCancelled


class BackendTests(unittest.TestCase):
    def test_persistence_and_unfinished_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            store=HistoryStore(folder);chat=store.new(folder)
            chat['threadId']='persisted-thread'
            chat['turns'].append({'status':'running','prompt':'hello'})
            store.save();reloaded=HistoryStore(folder)
            self.assertEqual(reloaded.conversations[0]['threadId'],'persisted-thread')
            self.assertEqual(reloaded.conversations[0]['turns'][0]['status'],'interrupted')

    def test_corrupt_history_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'conversations.json';path.write_text('broken')
            with self.assertRaises(RuntimeError):HistoryStore(folder)
            self.assertEqual(path.read_text(),'broken')

    def test_output_assembly_prefers_final_answer(self):
        s=CodexSession('.')
        s.thread_id='t'
        s.event({'method':'item/agentMessage/delta','params':{'threadId':'other','itemId':'bad','delta':'wrong'}})
        for item in [{'id':'comment','type':'agentMessage','phase':'commentary','text':'Checking…'},
                     {'id':'final','type':'agentMessage','phase':'final_answer','text':'Done'}]:
            s.event({'method':'item/completed','params':{'threadId':'t','item':item}})
        self.assertEqual(s.final_text(),'Done');self.assertEqual(s.transcript(),'Checking…\n\nDone')

    def test_missing_interaction_handler_never_auto_approves(self):
        s=CodexSession('.')
        with patch.object(s,'send') as send:
            s.answer_request({'id':12,'method':'unknown/tool','params':{}})
            self.assertIn('error',send.call_args.args[0])

    def test_cancellation_interrupts_current_turn(self):
        s=CodexSession('.',thread_id='t');s.turn_id='turn';s.cancel.set()
        with patch.object(s,'send') as send:
            with self.assertRaises(TaskCancelled):s.next(10**20)
            self.assertEqual(send.call_args.args[0]['method'],'turn/interrupt')

    def test_resume_keeps_context_and_workspace_permissions(self):
        s=CodexSession('.',thread_id='saved-thread')
        calls=[]
        def rpc(method,params,timeout=45):
            calls.append((method,params))
            if method=='initialize':return {}
            if method=='thread/resume':return {'thread':{'id':'saved-thread'}}
            if method=='turn/start':
                s.event({'method':'item/completed','params':{'item':{'id':'a','type':'agentMessage','text':'Okay','phase':'final_answer'}}})
                s.finished_turn={'status':'completed'};return {'turn':{'id':'x'}}
        with patch.object(s,'start'),patch.object(s,'close'),patch.object(s,'send'),patch.object(s,'rpc',side_effect=rpc):
            self.assertEqual(s.run('continue')['text'],'Okay')
        self.assertEqual(calls[1][0],'thread/resume')
        self.assertEqual(calls[2][1]['sandboxPolicy']['type'],'workspaceWrite')
        self.assertEqual(calls[2][1]['approvalPolicy'],'on-request')


from PySide6.QtWidgets import QApplication,QLabel,QPushButton
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from pet import Pet
from chat_ui import ChatController,TaskWorker

app=QApplication.instance() or QApplication([])


class ChatUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.pet=Pet();cls.pet.show()
        cls.controller=ChatController(cls.pet,cls.temp.name);cls.pet.chat=cls.controller

    @classmethod
    def tearDownClass(cls):
        cls.controller.shutdown();cls.pet.tick.stop();cls.pet.bubble.hide();cls.pet.hide()
        cls.temp.cleanup()

    def tearDown(self):
        self.controller.hide();self.controller.window.hide();self.pet.bubble.hide()

    def test_menu_submenus_and_idle_preview(self):
        menu=self.pet.context_menu();actions={a.text():a for a in menu.actions()}
        self.assertEqual(len(actions['互动差分动画'].menu().actions()),15)
        self.assertEqual(len(actions['工作差分动画'].menu().actions()),5)
        self.assertTrue(actions['工作差分动画'].menu().actions()[0].isEnabled())
        idle=actions['待机差分动画'].menu().actions()
        self.assertEqual(idle[1].text(),'待机动作02');idle[1].trigger()
        self.assertEqual(self.pet.current,self.pet.idles[1]);menu.deleteLater()

    def test_composer_stays_below_pet_at_screen_edges(self):
        c=self.controller;c.toggle()
        self.pet.move(self.pet.constrained_position(QPoint(99999,99999)))
        app.processEvents();c.position()
        area=app.primaryScreen().availableGeometry()
        self.assertEqual(c.composer.y(),self.pet.y()+self.pet.height()+8)
        self.assertTrue(area.contains(c.composer.frameGeometry()))
        c.composer.close();self.assertFalse(c.enabled)

    def test_long_result_details_and_full_history(self):
        c=self.controller;chat=c.store.new(c.temp.name if hasattr(c,'temp') else self.temp.name)
        text='完整结果，不能丢失。\n'*80
        turn={'prompt':'test','created':'now','status':'running','output':'','events':[]}
        chat['turns'].append(turn);c.active=chat;c.running_chat=chat;c.running_turn=turn
        c.completed({'threadId':'x','text':text,'transcript':text})
        app.processEvents()
        labels=self.pet.bubble.findChildren(QLabel)
        self.assertEqual(labels[0].text(),'主人，完成啦！')
        buttons=[b for b in self.pet.bubble.findChildren(QPushButton) if b.text()=='详情']
        self.assertEqual(len(buttons),1);buttons[0].click()
        self.assertTrue(c.window.isVisible());self.assertIn(text.strip(),c.window.view.toPlainText())
        self.assertEqual(HistoryStore(self.temp.name).conversations[-1]['turns'][-1]['result'],text)

    def test_failure_does_not_claim_success(self):
        c=self.controller;chat=c.store.new(self.temp.name)
        turn={'prompt':'test','created':'now','status':'running','output':'','events':[]}
        chat['turns'].append(turn);c.active=chat;c.running_chat=chat;c.running_turn=turn
        c.failed('模拟连接中断',False)
        self.assertEqual(turn['status'],'failed')
        self.assertNotIn('任务完成啦',self.pet.bubble.findChildren(QLabel)[0].text())

    def test_close_history_keeps_pet_and_draft(self):
        c=self.controller;c.open_history();c.window.editor.setPlainText('未发送的草稿')
        c.window.close();app.processEvents()
        self.assertFalse(c.window.isVisible());self.assertTrue(self.pet.isVisible())
        self.assertEqual(c.window.editor.toPlainText(),'未发送的草稿')

    def test_async_worker_does_not_block_and_preserves_thread(self):
        c=self.controller;c.active=c.store.new(self.temp.name)
        with patch('quota.find_codex',return_value='codex'),patch('chat_ui.CodexSession.run',return_value={'threadId':'returned','text':'答复','transcript':'答复'}):
            c.submit('测试后台')
            self.assertTrue(c.busy)
            for _ in range(30):
                QTest.qWait(30)
                if not c.busy:break
            self.assertFalse(c.busy)
            self.assertEqual(c.active['threadId'],'returned')
            self.assertEqual(c.active['turns'][-1]['status'],'completed')


if __name__=='__main__':unittest.main()

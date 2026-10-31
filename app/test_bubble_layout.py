"""回归用户报告的中文换行气泡裁切；不启动桌宠主窗口。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
import time
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtTest import QTest
from pet import Bubble

app=QApplication.instance() or QApplication([])
CAPTION='今日份喜欢，已经送到主人的桌面啦。'
LONG_TITLE='主人，这一步需要的文件和资料已经准备好，接下来继续认真处理。'

class BubbleLayoutTests(unittest.TestCase):
    def setUp(self):self.bubble=Bubble()
    def tearDown(self):self.bubble.close();self.bubble.deleteLater();app.processEvents()
    def assert_text_fits(self):
        def settled():
            return all(label.height()>=label.heightForWidth(label.width()) and self.bubble.rect().contains(label.geometry())
                       for label in self.bubble.findChildren(QLabel))
        # XCB ConfigureNotify replies can arrive after the first event drain.
        deadline=time.monotonic()+1
        while not settled() and time.monotonic()<deadline:QTest.qWait(10)
        self.assertTrue(settled(),'窗口未完成换行高度调整')
        for label in self.bubble.findChildren(QLabel):
            required=label.heightForWidth(label.width())
            self.assertGreaterEqual(label.height(),required,(label.text(),label.size(),required))
            self.assertTrue(self.bubble.rect().contains(label.geometry()),(label.text(),self.bubble.size(),label.geometry(),self.bubble.minimumHeight(),self.bubble.maximumHeight()))
        self.assertTrue(self.bubble.rect().contains(self.bubble.close_button.geometry()))
    def test_first_multiline_caption(self):
        self.bubble.set_scale_percent(150);self.bubble.message(CAPTION);self.assert_text_fits()
    def test_short_then_long_caption_and_shrink(self):
        self.bubble.message('短句');self.assert_text_fits();short=self.bubble.height()
        self.bubble.message(CAPTION*3);self.assert_text_fits();long=self.bubble.height()
        self.assertGreater(long,short)
        self.bubble.message('短句');self.assert_text_fits();self.assertLess(self.bubble.height(),long)
    def test_scale_and_text_transitions(self):
        for scale in (50,75,100,125,150,100,50):
            self.bubble.set_scale_percent(scale)
            for text in ('短句',CAPTION,'收到啦，主人！让我先把你的嘱咐认真记下来。','完成啦！给主人悄悄贴一颗小星星！','第一行\n第二行\n第三行','中英文 mixed: hello, world! '+CAPTION):
                with self.subTest(scale=scale,text=text):self.bubble.message(text);self.assert_text_fits()
    def test_quota_result_caption_switches(self):
        for scale in (50,100,150):
            self.bubble.set_scale_percent(scale)
            self.bubble.task_result(LONG_TITLE,'可滚动的结果\n'*20,lambda:None);self.assert_text_fits()
            self.bubble.quota([{'name':'5小时','remaining':70,'resetsAt':None}]);self.assert_text_fits()
            self.bubble.message(CAPTION);self.assert_text_fits()

if __name__=='__main__':unittest.main()

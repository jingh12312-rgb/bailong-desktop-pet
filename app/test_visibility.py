import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from desktop_visibility import covers_monitor
from pet import Pet

app=QApplication.instance() or QApplication([])

class VisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pet=Pet()

    @classmethod
    def tearDownClass(cls):
        cls.pet.close()

    def setUp(self):
        self.pet.manual_hidden=False;self.pet.fullscreen_hidden=False
        self.pet.apply_visibility()

    def test_monitor_bounds(self):
        self.assertTrue(covers_monitor((0,0,1920,1080),(0,0,1920,1080)))
        self.assertFalse(covers_monitor((0,0,1920,1040),(0,0,1920,1080)))
        self.assertTrue(covers_monitor((-1920,0,0,1080),(-1920,0,0,1080)))
        self.assertFalse(covers_monitor((0,0,1920,1080),(-1920,0,0,1080)))

    def test_manual_hide_survives_fullscreen_exit(self):
        p=self.pet
        with patch.object(p.tray,'isVisible',return_value=True):p.set_manual_hidden(True)
        p.fullscreen_hidden=True;p.apply_visibility()
        p.fullscreen_hidden=False;p.apply_visibility()
        self.assertFalse(p.isVisible());self.assertFalse(p.tick.isActive())
        p.set_manual_hidden(False)
        self.assertTrue(p.isVisible());self.assertTrue(p.tick.isActive())

    def test_auto_restore_and_suppressed_bubbles(self):
        p=self.pet;p.fullscreen_hidden=True;p.apply_visibility()
        p.say('hidden');self.assertFalse(p.bubble.isVisible())
        p.set_manual_hidden(False);self.assertFalse(p.isVisible())
        p.fullscreen_hidden=False;p.apply_visibility();self.assertTrue(p.isVisible())

    def test_identical_menus(self):
        p=self.pet;p.refresh_tray_menu()
        menu=p.context_menu()
        self.assertEqual([a.text() for a in menu.actions()],[a.text() for a in p.tray_menu.actions()])
        self.assertEqual(menu.actions()[0].text(),'隐藏桌宠')
        menu.deleteLater()

if __name__=='__main__':unittest.main()

import sys
import unittest


@unittest.skipUnless(sys.platform == 'darwin', 'macOS native window check')
class MacWindowTests(unittest.TestCase):
    def test_tool_window_can_join_all_spaces(self):
        import objc
        from AppKit import (NSWindowCollectionBehaviorCanJoinAllSpaces,
                            NSWindowCollectionBehaviorMoveToActiveSpace,
                            NSWindowCollectionBehaviorFullScreenAuxiliary)
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QWidget
        from platform_support import configure_mac_window
        app = QApplication.instance() or QApplication([])
        if app.platformName() != 'cocoa':
            self.skipTest('Requires native Cocoa platform')
        widget = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        widget.show()
        try:
            window = objc.objc_object(c_void_p=int(widget.winId())).window()
            window.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)
            configure_mac_window(widget)
            self.assertFalse(window.hidesOnDeactivate())
            behavior = int(window.collectionBehavior())
            self.assertTrue(behavior & NSWindowCollectionBehaviorCanJoinAllSpaces)
            self.assertTrue(behavior & NSWindowCollectionBehaviorFullScreenAuxiliary)
            self.assertFalse(behavior & NSWindowCollectionBehaviorMoveToActiveSpace)
            configure_mac_window(widget)
            self.assertEqual(behavior, int(window.collectionBehavior()))
        finally:
            widget.close()


if __name__ == '__main__':
    unittest.main()

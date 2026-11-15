"""Run repository checks with temporary QSettings instead of user preferences."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from PySide6.QtCore import QSettings
from unittest.mock import patch
import pet

with tempfile.TemporaryDirectory(prefix='bailong-tests-') as settings_dir:
    def isolated_settings(organization, application):
        return QSettings(str(Path(settings_dir)/organization/(application+'.ini')), QSettings.Format.IniFormat)
    assert Path(isolated_settings('BailongPet','DesktopPet').fileName()).is_relative_to(settings_dir)
    with patch.object(pet, 'QSettings', isolated_settings):
        suite = unittest.defaultTestLoader.discover(str(ROOT/'app'), pattern='test_*.py')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

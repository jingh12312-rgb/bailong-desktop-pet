"""Real-asset differential and memory test, isolated from user preferences."""
import argparse
import atexit
import json
import os
import statistics
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_SCALE_FACTOR'] = '2'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import psutil
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication
import pet as pet_module
from pet import Pet
from video_frames import rgba_frames


def percentile(values, quantile):
    return sorted(values)[min(len(values)-1, int(len(values)*quantile))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--soak-seconds', type=float, default=600)
    parser.add_argument('--output', type=Path, default=ROOT/'memory-results.json')
    args = parser.parse_args()
    process = psutil.Process()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bailong-performance-') as settings_dir:
        def isolated_settings(organization, application):
            return QSettings(str(Path(settings_dir)/organization/(application+'.ini')), QSettings.Format.IniFormat)
        pet_module.QSettings = isolated_settings
        settings = isolated_settings('BailongPet', 'DesktopPet')
        assert Path(settings.fileName()).is_relative_to(settings_dir), settings.fileName()
        settings.setValue('soundDisabled', True)
        app = QApplication.instance() or QApplication([])
        started = time.perf_counter()
        pet = Pet()
        atexit.register(pet.frame_buffer.close)
        pet.tick.stop()
        assert pet.frame_size == 512, pet.frame_size
        samples = []

        def snapshot(phase):
            memory = process.memory_info()
            children = [p for p in process.children() if p.is_running()]
            child_private = 0
            for child in children:
                try:
                    child_private += child.memory_info().private
                except psutil.NoSuchProcess:
                    pass
            sample = {'elapsedSeconds':time.perf_counter()-started, 'phase':phase,
                      'privateBytes':memory.private, 'workingSetBytes':memory.rss,
                      'peakPrivateBytes':memory.peak_pagefile,
                      'decoderCount':len(children), 'decoderPrivateBytes':child_private,
                      'buffer':pet.frame_buffer.snapshot()}
            samples.append(sample)
            return sample

        warm = snapshot('warm')
        items = pet.idles + pet.extra_idles + pet.variants + pet.movement_slots + [i for i in pet.work_slots if i]
        items += [pet.manifest[k] for k in ('dragAnimation','landingAnimation','quotaAnimation')]
        items = list({str(pet.asset_path(item)):item for item in items}.values())
        assert len(items) == len(pet.pinned_frames) == 35
        assert sum(len(frames) for frames in pet.pinned_frames.values()) == 4426
        switches, ready_times, compared = [], [], []
        for item in items:
            before = time.perf_counter()
            pet.play(item, 'variant')
            first = pet.frames[0]
            assert first.width() == first.height() == 512
            assert first.hasAlphaChannel()
            switches.append((time.perf_counter()-before)*1000)
            target = min(12, len(pet.frames)-1)
            before = time.perf_counter()
            while pet.frames.last_index != target:
                pet.frames.refresh(target)
                app.processEvents()
                if time.perf_counter()-before > 5:
                    raise AssertionError('Frame not ready: '+item['id'])
                time.sleep(.001)
            ready_times.append((time.perf_counter()-before)*1000)
            # Original full-decode conversion, consuming just the selected prefix.
            with closing(rgba_frames(pet.asset_path(item), 512)) as reference:
                for _ in range(target+1):
                    raw = next(reference)
            image = QImage(raw, 512, 512, 2048, QImage.Format.Format_RGBA8888).copy()
            expected = QPixmap.fromImage(image).toImage()
            assert pet.frames[target].toImage() == expected, item['id']
            compared.append(item['id'])
        snapshot('all-actions-verified')
        result = {'frameSize':512, 'actions':len(items), 'framePackets':4426,
                  'startupSeconds':warm['elapsedSeconds'],
                  'settingsIsolated':True, 'pixelComparedActionIds':compared,
                  'pixelComparison':'Frame 12 (or final frame of shorter clips), same RGBA-to-QPixmap conversion as baseline.',
                  'warmSwitchMs':{'p50':statistics.median(switches),'p95':percentile(switches,.95),'max':max(switches)},
                  'frame12ReadyMs':{'p50':statistics.median(ready_times),'p95':percentile(ready_times,.95),'max':max(ready_times)},
                  'soakRequestedSeconds':args.soak_seconds, 'soakCompleted':False, 'samples':samples}

        def save():
            result['maxSampledPrivateBytes'] = max(s['privateBytes'] for s in samples)
            result['peakPrivateBytes'] = max(s['peakPrivateBytes'] for s in samples)
            result['maxSampledProcessTreePrivateBytes'] = max(s['privateBytes']+s['decoderPrivateBytes'] for s in samples)
            result['maxBufferedFrames'] = max(s['buffer']['buffered_frames'] for s in samples)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        save()
        print(json.dumps({k:v for k,v in result.items() if k != 'samples'}, ensure_ascii=False), flush=True)
        pet.show()
        pet.tick.start()
        soak_started = time.monotonic()
        next_switch = soak_started
        next_sample = soak_started + .5
        action = 0
        while time.monotonic()-soak_started < args.soak_seconds:
            now = time.monotonic()
            if now >= next_switch:
                pet.play(items[action % len(items)], 'variant')
                action += 1
                next_switch = now+1
            if now >= next_sample:
                sample = snapshot('soak')
                assert sample['buffer']['buffered_frames'] <= 10
                assert sample['decoderCount'] <= 1
                assert sample['privateBytes'] < 512*1024*1024
                save()
                next_sample = now+5
            app.processEvents()
            time.sleep(.003)
        pet.tick.stop()
        snapshot('soak-end')
        pet.close()
        result['soakPlaybackCompleted'] = True
        result['soakActualSeconds'] = time.monotonic()-soak_started
        result['soakSwitches'] = action
        result['closedBuffer'] = pet.frame_buffer.snapshot()
        closing_children = process.children()
        result['initialChildrenAfterClose'] = []
        for child in closing_children:
            try:
                result['initialChildrenAfterClose'].append({'pid':child.pid,'name':child.name(),'command':child.cmdline()})
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(closing_children, timeout=3)
        result['childrenAfterClose'] = [p.pid for p in alive]
        save()
        assert not result['closedBuffer']['worker_alive']
        assert not result['childrenAfterClose']
        result['soakCompleted'] = True
        save()
        print('COMPLETE '+str(output), flush=True)


if __name__ == '__main__':
    main()

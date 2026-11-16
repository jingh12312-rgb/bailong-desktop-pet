"""Unit tests for the standard-library frame buffer. No Qt, no real assets."""

import threading
import time
import unittest

from frame_buffer import FrameBuffer

TIMEOUT = 3.0


class FakeProc:
    """Minimal Popen stand-in: poll() reports exit, kill() records the call."""

    def __init__(self):
        self.killed = False

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True


def wait_for(predicate, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.005)
    raise AssertionError('condition not reached within %.1fs' % timeout)


class CountingFactory:
    """Small fake producer that records how much was consumed."""

    def __init__(self, count=100, tag=b'f'):
        self.count = count
        self.tag = tag
        self.calls = 0
        self.produced = 0

    def __call__(self, register):
        self.calls += 1
        for index in range(self.count):
            self.produced += 1
            yield self.tag + b':' + str(index).encode()


class StuckProc(FakeProc):
    """A live process whose kill() fails; poll() never reports exit."""

    def kill(self):
        raise OSError('kill refused')


class CleanupFails:
    """Iterator whose close() fails after a normal EOF."""

    def __init__(self, count=1, tag=b'f'):
        self.remaining = count
        self.tag = tag

    def __iter__(self):
        return self

    def __next__(self):
        if not self.remaining:
            raise StopIteration
        index = self.remaining
        self.remaining -= 1
        return self.tag + b':' + str(index - 1).encode()

    def close(self):
        raise RuntimeError('cleanup failed')


class FrameBufferTests(unittest.TestCase):

    def tearDown(self):
        for buffer in getattr(self, '_buffers', []):
            buffer.close()

    def make(self, **kwargs):
        buffer = FrameBuffer(**kwargs)
        self._buffers = getattr(self, '_buffers', []) + [buffer]
        return buffer

    def test_prefetch_is_bounded_and_cache_stays_within_prefetch_plus_two(self):
        factory = CountingFactory()
        buffer = self.make(prefetch=3)
        buffer.activate('a', factory)
        wait_for(lambda: buffer.snapshot()['buffered_frames'] == 4)
        time.sleep(0.05)
        self.assertEqual(4, factory.produced, 'only prefetch+1 frames up front')
        self.assertLessEqual(buffer.snapshot()['buffered_frames'], 5)
        wait_for(lambda: buffer.get('a', 3) == b'f:3')
        self.assertLessEqual(buffer.snapshot()['buffered_frames'], 5)

    def test_target_jump_drops_old_frames_and_skips_ahead(self):
        factory = CountingFactory()
        buffer = self.make(prefetch=2)
        buffer.activate('a', factory)
        wait_for(lambda: buffer.get('a', 0) == b'f:0')
        self.assertIsNone(buffer.get('a', 10))
        wait_for(lambda: buffer.get('a', 10) == b'f:10')
        self.assertIsNone(buffer.get('a', 5), 'frames below the target were released')
        self.assertLessEqual(buffer.snapshot()['buffered_frames'], 4)
        self.assertEqual(10, buffer.snapshot()['target'])

    def test_activate_replays_same_key_and_discards_old_bytes(self):
        first = CountingFactory(tag=b'one')
        second = CountingFactory(tag=b'two')
        buffer = self.make(prefetch=4)
        buffer.activate('k', first)
        wait_for(lambda: buffer.get('k', 2) == b'one:2')
        buffer.activate('k', second)
        wait_for(lambda: buffer.get('k', 0) == b'two:0')
        wait_for(lambda: (buffer.get('k', 1) or b'').startswith(b'two:'))
        wait_for(lambda: (buffer.get('k', 2) or b'').startswith(b'two:'))
        self.assertNotEqual(b'one:2', buffer.get('k', 2))
        self.assertEqual('k', buffer.snapshot()['active_key'])

    def test_other_key_returns_none_without_changing_target(self):
        factory = CountingFactory()
        buffer = self.make(prefetch=2)
        buffer.activate('a', factory)
        wait_for(lambda: buffer.get('a', 0) == b'f:0')
        self.assertIsNone(buffer.get('b', 50))
        self.assertEqual(0, buffer.snapshot()['target'])

    def test_error_is_raised_as_runtime_error_with_original_cause(self):
        class Boom(Exception):
            pass

        def factory(register):
            yield b'ok:0'
            raise Boom('boom')

        buffer = self.make(prefetch=0)
        buffer.activate('a', factory)
        wait_for(lambda: buffer.get('a', 0) == b'ok:0')

        def failed():
            try:
                buffer.get('a', 1)
            except RuntimeError as error:
                return error
            return None

        error = wait_for(failed)
        self.assertIn('boom', str(error))
        self.assertIsInstance(error.__cause__, Boom)
        with self.assertRaises(RuntimeError):
            buffer.get('a', 1)

    def test_eof_does_not_call_factory_or_next_again(self):
        factory = CountingFactory(count=3)
        buffer = self.make(prefetch=4)
        buffer.activate('a', factory)
        wait_for(lambda: buffer.snapshot()['eof'])
        time.sleep(0.05)
        self.assertEqual(1, factory.calls)
        self.assertEqual(3, factory.produced)
        self.assertEqual(b'f:2', buffer.get('a', 2))
        buffer.activate('a', factory)
        wait_for(lambda: factory.calls == 2 and buffer.snapshot()['eof'])

    def test_close_while_paused_kills_process_and_joins_worker(self):
        proc = FakeProc()
        factory = CountingFactory()

        def producer(register):
            register(proc)
            yield from factory(register)

        buffer = self.make(prefetch=2)
        buffer.activate('a', producer)
        wait_for(lambda: buffer.snapshot()['buffered_frames'] == 3)
        buffer.close()
        self.assertTrue(proc.killed)
        self.assertFalse(buffer.snapshot()['worker_alive'])
        buffer.close()  # idempotent
        with self.assertRaises(RuntimeError):
            buffer.activate('a', factory)

    def test_process_registered_after_switch_is_killed(self):
        entered = threading.Event()
        go = threading.Event()
        proc = FakeProc()
        new_factory = CountingFactory(tag=b'new')

        def stale(register):
            entered.set()
            go.wait(TIMEOUT)
            register(proc)
            yield b'stale:0'

        buffer = self.make(prefetch=2)
        buffer.activate('old', stale)
        self.assertTrue(entered.wait(TIMEOUT))
        buffer.activate('new', new_factory)
        go.set()
        wait_for(lambda: proc.killed)
        wait_for(lambda: buffer.get('new', 0) == b'new:0')
        self.assertIsNone(buffer.get('old', 0))
        self.assertEqual('new', buffer.snapshot()['active_key'])

    def test_kill_failure_of_live_process_propagates(self):
        proc = StuckProc()
        factory = CountingFactory()

        def producer(register):
            register(proc)
            yield from factory(register)

        buffer = self.make(prefetch=2)
        buffer.activate('a', producer)
        wait_for(lambda: buffer.snapshot()['buffered_frames'] == 3)
        with self.assertRaises(OSError):
            buffer.close()
        self.assertFalse(buffer.snapshot()['worker_alive'])

    def test_cleanup_failure_of_current_generation_reaches_get(self):
        buffer = self.make(prefetch=0)
        buffer.activate('a', lambda register: CleanupFails())
        wait_for(lambda: buffer.get('a', 0) == b'f:0')

        def surfaced():
            try:
                buffer.get('a', 1)
            except RuntimeError as error:
                return error
            return None

        error = wait_for(surfaced)
        self.assertIn('cleanup failed', str(error))
        self.assertIsInstance(error.__cause__, RuntimeError)

    def test_cleanup_failure_of_stale_generation_is_ignored(self):
        def stale(register):
            try:
                while True:
                    yield b'stale'
            finally:
                raise RuntimeError('stale cleanup')

        new_factory = CountingFactory(tag=b'new')
        buffer = self.make(prefetch=1)
        buffer.activate('old', stale)
        wait_for(lambda: buffer.get('old', 0) == b'stale')
        buffer.activate('new', new_factory)
        wait_for(lambda: buffer.get('new', 0) == b'new:0')
        self.assertIsNone(buffer.get('old', 0))
        self.assertTrue(buffer.snapshot()['worker_alive'])
        self.assertIsNone(buffer.snapshot()['error'])

    def test_process_registered_after_close_started_is_killed(self):
        entered = threading.Event()
        gate = threading.Event()
        proc = FakeProc()
        factory = CountingFactory()

        def producer(register):
            entered.set()
            gate.wait(TIMEOUT)
            register(proc)
            yield b'late:0'

        buffer = self.make(prefetch=2)
        buffer.activate('a', producer)
        self.assertTrue(entered.wait(TIMEOUT))
        closer = threading.Thread(target=buffer.close, name='closer')
        closer.start()
        wait_for(lambda: buffer.snapshot()['active_key'] is None)
        self.assertTrue(closer.is_alive(), 'close is still joining the blocked worker')
        gate.set()
        wait_for(lambda: proc.killed)
        closer.join(TIMEOUT)
        self.assertFalse(closer.is_alive())
        self.assertFalse(buffer.snapshot()['worker_alive'])


if __name__ == '__main__':
    unittest.main()

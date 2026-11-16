"""Bounded background frame buffer for the desktop pet.

Pure standard library, no Qt. One lazy worker thread consumes the iterator
returned by ``factory``; the GUI thread only calls ``activate``/``get``/
``close``. At most ``prefetch + 2`` frames are kept, in a window that starts
at the requested target, so memory does not grow with the number of frames.
"""

import threading


class _Generation:
    """Per-``activate`` state. Replaced on every switch; never reused."""

    __slots__ = ('gen', 'key', 'factory', 'target', 'frames', 'eof',
                 'error', 'proc', 'started')

    def __init__(self, gen, key, factory):
        self.gen = gen
        self.key = key
        self.factory = factory
        self.target = 0
        self.frames = {}
        self.eof = False
        self.error = None
        self.proc = None
        self.started = False


def _terminate(proc):
    """Kill ``proc`` unless it has already exited.

    An ``OSError`` from kill() is only the normal exit race when a second
    poll() confirms the process is gone. A process that is still alive is a
    real failure and propagates.
    """
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.kill()
    except OSError:
        if proc.poll() is None:
            raise


class FrameBuffer:
    """Bounded, generation-scoped prefetch of raw frame bytes."""

    def __init__(self, prefetch=8):
        prefetch = int(prefetch)
        if prefetch < 0:
            raise ValueError('prefetch must be non-negative')
        self._prefetch = prefetch
        self._cond = threading.Condition()
        self._generation = 0
        self._state = None
        self._closed = False
        self._thread = None

    # -- GUI thread -------------------------------------------------------

    def activate(self, key, factory):
        """Start a new generation at frame 0, replaying even for the same key."""
        with self._cond:
            if self._closed:
                raise RuntimeError('frame buffer is closed')
            self._generation += 1
            old = self._state
            self._state = _Generation(self._generation, key, factory)
            if self._thread is None:
                thread = threading.Thread(target=self._run, name='frame-buffer',
                                          daemon=True)
                self._thread = thread
                thread.start()
            self._cond.notify_all()
        # Outside the lock: a failing kill reaches the caller instead of
        # wedging the new generation inside the critical section.
        if old is not None:
            _terminate(old.proc)

    def get(self, key, index):
        """Move the target to ``index`` and return its bytes, or ``None``.

        Never blocks. Indices are expected to be non-negative and
        non-decreasing within one activation.
        """
        with self._cond:
            state = self._state
            if state is None or state.key != key:
                return None
            if state.error is not None:
                raise RuntimeError('frame source failed: %r' % (state.error,)) from state.error
            if index > state.target:
                state.target = index
                self._trim(state)
                self._cond.notify_all()
            return state.frames.get(index)

    def close(self):
        """Stop the worker, killing any live producer. Idempotent."""
        failure = None
        with self._cond:
            if not self._closed:
                self._closed = True
                self._generation += 1
                state = self._state
                self._state = None
                self._cond.notify_all()
                if state is not None:
                    try:
                        _terminate(state.proc)
                    except OSError as error:
                        # Still join below: a failed kill must not leak the worker.
                        failure = error
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        if failure is not None:
            raise failure

    def snapshot(self):
        """Small diagnostic view; safe to call from any thread."""
        with self._cond:
            state = self._state
            return {
                'active_key': None if state is None else state.key,
                'target': 0 if state is None else state.target,
                'buffered_frames': 0 if state is None else len(state.frames),
                'worker_alive': self._thread is not None and self._thread.is_alive(),
                'eof': bool(state is not None and state.eof),
                'error': None if state is None or state.error is None else repr(state.error),
            }

    # -- worker thread ----------------------------------------------------

    def _run(self):
        while True:
            with self._cond:
                state = None
                while True:
                    if self._closed:
                        return
                    candidate = self._state
                    if candidate is not None and not candidate.started:
                        candidate.started = True
                        state = candidate
                        break
                    # Idle: wait for a new generation, a target, or close.
                    self._cond.wait()
            self._decode(state)

    def _register(self, state, proc):
        """Factory callback: adopt ``proc`` for cancellation, or kill it."""
        with self._cond:
            if not self._closed and self._state is state:
                state.proc = proc
                return
        # Registered after cancellation or a generation switch: kill it now.
        _terminate(proc)

    def _fail(self, state, error):
        with self._cond:
            # The first failure wins; a superseded generation keeps nothing.
            if self._state is state and state.error is None:
                state.error = error
                self._cond.notify_all()

    def _decode(self, state):
        iterator = None
        try:
            try:
                iterator = state.factory(lambda proc: self._register(state, proc))
            except Exception as error:
                self._fail(state, error)
                return
            index = 0
            while True:
                with self._cond:
                    while not (self._closed or self._state is not state
                               or state.eof
                               or index <= state.target + self._prefetch):
                        self._cond.wait()
                    if self._closed or self._state is not state or state.eof:
                        return
                try:
                    frame = next(iterator)
                except StopIteration:
                    with self._cond:
                        if self._state is state:
                            state.eof = True
                            self._cond.notify_all()
                    return
                except Exception as error:  # surface it to get(), not to the GUI thread
                    self._fail(state, error)
                    return
                with self._cond:
                    if self._closed or self._state is not state:
                        return
                    if index >= state.target:
                        state.frames[index] = frame
                        self._trim(state)
                    self._cond.notify_all()
                index += 1
        finally:
            self._close_iterator(state, iterator)

    def _close_iterator(self, state, iterator):
        """Run the factory's cleanup here, in the worker thread.

        Cleanup failure of the live generation is reported through get(); a
        superseded or closed generation must not pollute the new one or kill
        the worker.
        """
        if iterator is None:
            return
        close = getattr(iterator, 'close', None)
        if close is None:
            return
        try:
            close()
        except Exception as error:
            self._fail(state, error)

    def _trim(self, state):
        for index in [i for i in state.frames if i < state.target]:
            del state.frames[index]
        limit = self._prefetch + 2
        while len(state.frames) > limit:
            del state.frames[min(state.frames)]

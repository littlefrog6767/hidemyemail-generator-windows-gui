"""Runs asyncio coroutines and blocking calls (e.g. IMAP) off the Qt main
thread. Qt widgets must only ever be touched from the main thread; unlike
the previous Tkinter version (which polled a queue every 80ms), this uses
Qt's signal/slot mechanism, which is thread-safe by design — emitting a
signal from a background thread automatically queues delivery onto the
receiving QObject's own thread (the main thread here), no polling needed."""

import asyncio
import threading

from PySide6.QtCore import QObject, Signal, Qt


class _ResultRelay(QObject):
    done = Signal(object, object, object)  # on_done callback, value, error
    progress = Signal(object, object)  # callback, args tuple


class AsyncWorker(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._relay = _ResultRelay()
        self._relay.done.connect(self._dispatch, Qt.QueuedConnection)
        self._relay.progress.connect(self._dispatch_progress, Qt.QueuedConnection)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _dispatch(self, callback, value, error):
        if callback is not None:
            callback(value, error)

    def _dispatch_progress(self, callback, args):
        if callback is not None:
            callback(*args)

    def post(self, callback, *args):
        """Thread-safe: schedules callback(*args) to run on the Qt main
        thread. For reporting incremental progress from inside a coroutine
        passed to run_coro — that coroutine runs on the background asyncio
        loop thread, so it can't touch widgets directly, same as on_done."""
        self._relay.progress.emit(callback, args)

    def run_coro(self, coro, on_done=None):
        """Schedules an async coroutine on the worker loop. on_done(value, error)
        fires on the Qt main thread once it completes."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _on_complete(fut):
            try:
                value = fut.result()
                self._relay.done.emit(on_done, value, None)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI callback
                self._relay.done.emit(on_done, None, exc)

        future.add_done_callback(_on_complete)
        return future

    def run_sync(self, func, *args, on_done=None):
        """Runs a blocking function (e.g. IMAP calls) in a worker thread pool,
        without blocking the Qt main thread. on_done(value, error) fires on
        the Qt main thread once it completes."""

        async def _runner():
            return await self._loop.run_in_executor(None, func, *args)

        return self.run_coro(_runner(), on_done=on_done)

    def shutdown(self):
        self._loop.call_soon_threadsafe(self._loop.stop)

"""Runs asyncio coroutines and blocking calls (e.g. IMAP) off the Tk main
thread, delivering results back on the Tk main thread via polling. Tkinter
widgets must only ever be touched from the main thread, so every background
result is handed back through a queue that a `root.after()` loop drains."""

import asyncio
import queue
import threading


class AsyncWorker:
    def __init__(self, tk_root):
        self._root = tk_root
        self._results = queue.Queue()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._poll()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _poll(self):
        try:
            while True:
                callback, value, error = self._results.get_nowait()
                if callback is not None:
                    callback(value, error)
        except queue.Empty:
            pass
        self._root.after(80, self._poll)

    def run_coro(self, coro, on_done=None):
        """Schedules an async coroutine on the worker loop. on_done(value, error)
        fires on the Tk main thread once it completes."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _on_complete(fut):
            try:
                value = fut.result()
                self._results.put((on_done, value, None))
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI callback
                self._results.put((on_done, None, exc))

        future.add_done_callback(_on_complete)
        return future

    def run_sync(self, func, *args, on_done=None):
        """Runs a blocking function (e.g. IMAP calls) in a worker thread pool,
        without blocking the Tk main thread. on_done(value, error) fires on
        the Tk main thread once it completes."""

        async def _runner():
            return await self._loop.run_in_executor(None, func, *args)

        return self.run_coro(_runner(), on_done=on_done)

    def shutdown(self):
        self._loop.call_soon_threadsafe(self._loop.stop)

"""Bridge between the Qt UI thread and the core asyncio loop.

The core (Telegram, jobs, sync) runs on a dedicated asyncio thread so heavy
work never freezes the UI. Results and EventBus events are marshalled back to
the UI thread through queued Qt signals.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import sys
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ..core.events import Event, EventBus

log = logging.getLogger(__name__)


class _Dispatcher(QObject):
    call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:
            log.exception("UI callback failed")


class CoreRuntime(QObject):
    event = Signal(str, dict)  # topic, payload (emitted on the UI thread)

    def __init__(self, bus: EventBus) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop() if sys.platform != "win32" else asyncio.SelectorEventLoop()
        self._thread = threading.Thread(target=self._run_loop, name="arcivo-core", daemon=True)
        self._dispatch = _Dispatcher()
        self._thread.start()
        bus.subscribe("*", self._on_event)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _on_event(self, ev: Event) -> None:
        self.ui(lambda: self.event.emit(ev.topic, ev.payload))

    def ui(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the UI thread."""
        self._dispatch.call.emit(fn)

    def submit(self, coro: Coroutine[Any, Any, Any], on_ok: Callable[[Any], None] | None = None,
               on_err: Callable[[BaseException], None] | None = None) -> Future:
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def done(f: Future) -> None:
            try:
                result = f.result()
            except BaseException as exc:
                if on_err:
                    self.ui(lambda e=exc: on_err(e))
                else:
                    log.error("Background task failed: %s", exc)
                return
            if on_ok:
                self.ui(lambda: on_ok(result))

        fut.add_done_callback(done)
        return fut

    def call_sync(self, fn: Callable[[], Any], timeout: float = 30) -> Any:
        """Run a plain function on the core loop thread and wait (used for loop-bound objects)."""
        async def wrapper() -> Any:
            return fn()
        return asyncio.run_coroutine_threadsafe(wrapper(), self.loop).result(timeout)

    def stop(self, cleanup: Coroutine[Any, Any, Any] | None = None) -> None:
        if cleanup is not None:
            try:
                asyncio.run_coroutine_threadsafe(cleanup, self.loop).result(15)
            except Exception:
                log.exception("Shutdown cleanup failed")
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)


class UiThreadGarbageCollector(QObject):
    """Run Python's cyclic GC on the UI thread only.

    With a background asyncio thread, the automatic collector may fire there and finalize Qt wrappers
    (e.g. chart slices captured in closures), destroying QObjects off the GUI thread → native crashes.
    We disable automatic collection and replicate its generational thresholds from a UI timer.
    """

    def __init__(self, interval_ms: int = 500) -> None:
        super().__init__()
        from PySide6.QtCore import QTimer

        self.threshold = gc.get_threshold()
        gc.disable()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(interval_ms)

    def check(self) -> None:
        c0, c1, c2 = gc.get_count()
        t0, t1, t2 = self.threshold
        if c0 > t0:
            gc.collect(0)
            if c1 > t1:
                gc.collect(1)
                if c2 > t2:
                    gc.collect(2)

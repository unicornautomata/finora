"""Run API calls off the UI thread so the window never freezes (important with many users).
Results are delivered back on the UI thread through a QObject that lives there."""
from __future__ import annotations
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

_dispatcher = None


class _Dispatcher(QObject):
    call = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    def _run(self, fn):
        fn()


def run_async(fn, on_ok=None, on_fail=None, raw_errors: bool = False):
    """Call run_async from the UI thread. fn runs in a worker; on_ok/on_fail run in the UI thread.
    on_fail receives the error message, or the exception object itself when raw_errors=True."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _Dispatcher()
    disp = _dispatcher

    class _Task(QRunnable):
        def run(self):
            try:
                result = fn()
            except Exception as ex:  # shown to the user, never swallowed
                err = ex if raw_errors else str(ex)
                disp.call.emit(lambda: on_fail(err) if on_fail else None)
            else:
                disp.call.emit(lambda: on_ok(result) if on_ok else None)

    QThreadPool.globalInstance().start(_Task())

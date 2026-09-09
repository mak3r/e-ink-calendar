"""Mock button controller for Mac development — keyboard instead of GPIO.

Selected by :func:`eink_calendar.buttons.factory.create_buttons` when
``config.display.driver == "mock"``. Instead of four physical buttons wired to
GPIO pins, it watches stdin: pressing the lowercased first character of a button
label (``a`` / ``b`` / ``c`` / ``d`` for the default ``A`` / ``B`` / ``C`` / ``D``
pin map) fires that label's configured binding, so ``python -m eink_calendar.app``
is fully driveable from a Mac terminal.

Reading is non-blocking (a short ``select`` poll on a daemon thread) and only
starts when stdin is an interactive TTY — under pytest, a pipe, or systemd
there is nothing to listen to and :meth:`MockButtons.start` is a no-op.
"""

from __future__ import annotations

import select
import sys
import threading

from eink_calendar.buttons.base import ButtonCallback, ButtonController

__all__ = ["MockButtons"]

_POLL_INTERVAL_S = 0.2


def _noop() -> None:
    """Explicit no-op for buttons bound to the 'noop' action (C/D)."""


class MockButtons(ButtonController):
    def __init__(self, pin_map: dict[str, int], bindings: dict[str, str]) -> None:
        self._pin_map = dict(pin_map)
        self._bindings = dict(bindings)
        self._handlers: dict[str, ButtonCallback] = {
            "cycle_view": _noop,
            "force_refresh": _noop,
        }
        # A keypress is matched to a button by the lowercased first character of
        # its label, then to an action via the configured bindings.
        self._keymap: dict[str, str] = {
            label[:1].lower(): self._bindings.get(label, "noop")
            for label in self._pin_map
        }
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- registration ---------------------------------------------------

    def on_view_cycle(self, callback: ButtonCallback) -> None:
        self._handlers["cycle_view"] = callback

    def on_refresh(self, callback: ButtonCallback) -> None:
        self._handlers["force_refresh"] = callback

    # -- simulation ---------------------------------------------------

    def press(self, key: str) -> None:
        """Fire the binding for ``key`` — the stdin reader's per-character entry point.

        Unknown keys and keys bound to ``noop`` (C/D) are ignored, matching a
        press of an unwired or reserved button.
        """
        action = self._keymap.get(key.lower())
        if action and action != "noop":
            self._handlers.get(action, _noop)()

    # -- lifecycle ---------------------------------------------------

    def start(self) -> None:
        stdin = sys.stdin
        if stdin is None or not stdin.isatty():
            # Piped / redirected / no stdin (tests, systemd) — nothing to read.
            return
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._read_loop, name="mock-buttons", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([sys.stdin], [], [], _POLL_INTERVAL_S)
            except (OSError, ValueError):
                return
            if not ready:
                continue
            line = sys.stdin.readline()
            if line == "":
                return  # EOF — stdin closed
            for char in line.strip():
                self.press(char)

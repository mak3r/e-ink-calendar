"""MockButtons + ``create_buttons("mock", ...)`` — the Mac keyboard button path.

Regression coverage for #51: the mock buttons module was missing, so
``python -m eink_calendar.app`` crashed before the main loop started.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from eink_calendar.buttons.factory import create_buttons
from eink_calendar.buttons.mock_buttons import MockButtons

PIN_MAP = {"A": 5, "B": 6, "C": 16, "D": 24}
BINDINGS = {"A": "cycle_view", "B": "force_refresh", "C": "noop", "D": "noop"}


def _buttons() -> MockButtons:
    controller = create_buttons("mock", pin_map=PIN_MAP, bindings=BINDINGS)
    assert isinstance(controller, MockButtons)
    return controller


def _recording_controller() -> tuple[MockButtons, list[str]]:
    fired: list[str] = []
    controller = _buttons()
    controller.on_view_cycle(lambda: fired.append("cycle"))
    controller.on_refresh(lambda: fired.append("refresh"))
    return controller, fired


def test_factory_rejects_unknown_driver():
    with pytest.raises(ValueError, match="unknown button driver"):
        create_buttons("plasma", pin_map=PIN_MAP, bindings=BINDINGS)


def test_press_a_cycles_view():
    controller, fired = _recording_controller()
    controller.press("a")
    assert fired == ["cycle"]


def test_press_b_forces_refresh():
    controller, fired = _recording_controller()
    controller.press("b")
    assert fired == ["refresh"]


def test_press_is_case_insensitive():
    controller, fired = _recording_controller()
    controller.press("A")
    assert fired == ["cycle"]


def test_noop_bound_buttons_do_nothing():
    controller, fired = _recording_controller()
    controller.press("c")
    controller.press("d")
    assert fired == []


def test_unknown_key_is_ignored():
    controller, fired = _recording_controller()
    controller.press("z")
    assert fired == []


def test_start_is_a_noop_when_stdin_is_not_a_tty():
    # Under pytest sys.stdin is not an interactive terminal.
    controller = _buttons()
    controller.start()
    try:
        assert controller._thread is None
    finally:
        controller.stop()


def test_read_loop_dispatches_keypresses_from_stdin(monkeypatch):
    read_fd, write_fd = os.pipe()
    reader = os.fdopen(read_fd)

    class _FakeTTY:
        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return reader.fileno()

        def readline(self) -> str:
            return reader.readline()

    monkeypatch.setattr(sys, "stdin", _FakeTTY())

    controller, fired = _recording_controller()
    controller.start()
    try:
        os.write(write_fd, b"ab\n")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(fired) < 2:
            time.sleep(0.02)
    finally:
        controller.stop()
        os.close(write_fd)
        reader.close()

    assert fired == ["cycle", "refresh"]


def test_mock_path_imports_no_hardware_module():
    _buttons()
    assert "gpiozero" not in sys.modules

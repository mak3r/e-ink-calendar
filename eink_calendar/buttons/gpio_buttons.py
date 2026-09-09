"""Real Raspberry Pi button wiring via ``gpiozero``.

Imports ``gpiozero``, which only installs on the Pi. Imported lazily by
:func:`eink_calendar.buttons.factory.create_buttons` and only when config selects
the real driver, so the package stays importable on a Mac.

Pin numbers and pull-up direction are confirmed against Pimoroni's current
pinout during Pi bring-up — see ``docs/runbook.md``.
"""

from __future__ import annotations

from eink_calendar.buttons.base import ButtonCallback, ButtonController

__all__ = ["GpioButtons"]


def _noop() -> None:
    """Explicit no-op for buttons bound to the 'noop' action (C/D)."""


class GpioButtons(ButtonController):
    def __init__(self, pin_map: dict[str, int], bindings: dict[str, str]) -> None:
        self._pin_map = pin_map
        self._bindings = bindings
        self._handlers: dict[str, ButtonCallback] = {
            "cycle_view": _noop,
            "force_refresh": _noop,
        }
        self._buttons: list[object] = []

    def on_view_cycle(self, callback: ButtonCallback) -> None:
        self._handlers["cycle_view"] = callback

    def on_refresh(self, callback: ButtonCallback) -> None:
        self._handlers["force_refresh"] = callback

    def start(self) -> None:
        from gpiozero import Button

        self._buttons = []
        for label, pin in self._pin_map.items():
            action = self._bindings.get(label, "noop")
            button = Button(pin)
            # C and D map to "noop" — explicitly bound to a real no-op callback
            # so a press is a defined event, not an unhandled one.
            button.when_pressed = self._handlers.get(action, _noop)
            self._buttons.append(button)

    def stop(self) -> None:
        for button in self._buttons:
            close = getattr(button, "close", None)
            if callable(close):
                close()
        self._buttons = []

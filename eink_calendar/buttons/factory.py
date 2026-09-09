"""Select a button controller from config without importing GPIO modules.

``gpio_buttons`` (Pi-only ``gpiozero`` import) and ``mock_buttons`` are both
imported lazily inside :func:`create_buttons`.
"""

from __future__ import annotations

from eink_calendar.buttons.base import ButtonController

__all__ = ["VALID_DRIVERS", "create_buttons"]

VALID_DRIVERS = ("inky", "mock")


def create_buttons(
    driver: str,
    *,
    pin_map: dict[str, int],
    bindings: dict[str, str],
) -> ButtonController:
    """Build the button controller matching ``config.display.driver``.

    ``"inky"`` → real ``gpiozero`` wiring; ``"mock"`` → stdin keypress simulation
    for Mac development.
    """
    if driver == "inky":
        from eink_calendar.buttons.gpio_buttons import GpioButtons

        return GpioButtons(pin_map=pin_map, bindings=bindings)

    if driver == "mock":
        from eink_calendar.buttons.mock_buttons import (  # type: ignore[import-not-found]
            MockButtons,
        )

        return MockButtons(pin_map=pin_map, bindings=bindings)

    raise ValueError(
        f"unknown button driver {driver!r}; expected one of {VALID_DRIVERS}"
    )

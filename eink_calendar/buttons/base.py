"""Button controller interface.

Two physical buttons matter to the app: one cycles Day/Week/Month, one forces a
refresh. The other two (C/D) are wired but do nothing yet — reserved for a
future settings menu. ``app.py`` registers its callbacks and calls
:meth:`ButtonController.start`; it never imports a concrete controller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

__all__ = ["ButtonCallback", "ButtonController"]

ButtonCallback = Callable[[], None]


class ButtonController(ABC):
    @abstractmethod
    def on_view_cycle(self, callback: ButtonCallback) -> None:
        """Register the handler for the view-cycle button (A)."""

    @abstractmethod
    def on_refresh(self, callback: ButtonCallback) -> None:
        """Register the handler for the force-refresh button (B)."""

    @abstractmethod
    def start(self) -> None:
        """Begin listening for presses. Non-blocking."""

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and release any resources."""

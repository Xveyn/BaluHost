"""Reusable confirmation modal for destructive actions.

ConfirmDialog dismisses True on confirm, False on cancel. When require_text is
given, the Confirm button only proceeds if the user types that exact phrase
(type-to-confirm) — used for the most dangerous operations.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Label, Button, Input
from textual.binding import Binding


def confirm_matches(expected: str, typed: str) -> bool:
    """True when *typed* (trimmed) exactly equals *expected* (case-sensitive)."""
    return typed.strip() == expected


class ConfirmDialog(ModalScreen):
    """Yes/No confirmation modal. dismiss(True) on confirm, dismiss(False) otherwise."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    ConfirmDialog { align: center middle; }
    #confirm-box {
        width: 64;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    #confirm-title { text-style: bold; color: $error; margin-bottom: 1; }
    #confirm-message { margin-bottom: 1; }
    Input { width: 1fr; margin-bottom: 1; }
    .button-row { height: auto; align: center middle; }
    Button { margin: 0 1; }
    """

    def __init__(
        self,
        title: str,
        message: str,
        confirm_label: str = "Confirm",
        require_text: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_label = confirm_label
        self._require_text = require_text

    def compose(self) -> ComposeResult:
        with Container(id="confirm-box"):
            yield Label(self._title, id="confirm-title")
            yield Label(self._message, id="confirm-message")
            if self._require_text is not None:
                yield Label(f"Type [b]{self._require_text}[/b] to confirm:")
                yield Input(id="confirm-input")
            with Horizontal(classes="button-row"):
                yield Button(self._confirm_label, variant="error", id="confirm-yes")
                yield Button("Cancel", variant="default", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-no":
            self.dismiss(False)
        elif event.button.id == "confirm-yes":
            if self._require_text is not None:
                typed = self.query_one("#confirm-input", Input).value
                if not confirm_matches(self._require_text, typed):
                    self.notify("Confirmation text does not match", severity="error")
                    return
            self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

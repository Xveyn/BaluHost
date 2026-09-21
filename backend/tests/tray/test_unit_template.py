"""The unit template must stay a user unit and stay unprivileged."""

from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "deploy" / "install" / "templates" / "baluhost-tray.service"
)


@pytest.fixture
def text() -> str:
    return TEMPLATE.read_text()


def test_template_exists():
    assert TEMPLATE.exists()


def test_is_bound_to_the_graphical_session(text: str):
    assert "graphical-session.target" in text


def test_restarts_on_failure(text: str):
    assert "Restart=on-failure" in text


def test_never_asks_for_root(text: str):
    """Ein User=root hier waere ein Bruch der Zusage aus der Spec."""
    assert "User=root" not in text
    assert "sudo" not in text


def test_uses_the_repo_placeholder_convention(text: str):
    """@@KEY@@ plus process_template, nicht rohes sed."""
    assert "@@INSTALL_DIR@@" in text
    assert "@@WEB_URL@@" in text
    assert "__INSTALL_DIR__" not in text


def test_opens_the_web_ui_not_the_api_port(text: str):
    """Die Unit startet ohne Argumente sonst immer mit dem Default."""
    assert "--web-url" in text


def test_does_not_thrash_when_unpaired(text: str):
    """Ohne Token soll die Unit gar nicht erst starten."""
    assert "ConditionPathExists=" in text

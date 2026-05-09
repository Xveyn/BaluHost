"""Tests for the os_sleep_inspector issue classifier."""
import pytest

from app.services.power import os_sleep_inspector as ins


def _classify(
    *,
    logind: dict[str, str] | None = None,
    sleep_conf: dict[str, str] | None = None,
    targets: dict[str, str] | None = None,
    has_lid: bool = False,
) -> list[ins.OsSleepIssue]:
    return ins._classify(
        logind=logind or {},
        sleep_conf=sleep_conf or {},
        targets=targets or {},
        has_lid=has_lid,
    )


class TestClassifier:
    def test_idle_action_suspend_warns(self):
        issues = _classify(logind={"IdleAction": "suspend", "IdleActionSec": "30min"})
        keys = {i.key for i in issues}
        assert "logind.idle_action.suspend" in keys
        suspend = next(i for i in issues if i.key == "logind.idle_action.suspend")
        assert suspend.severity == "warning"
        assert suspend.detail is not None and "30min" in suspend.detail

    def test_idle_action_hibernate_warns_with_distinct_key(self):
        issues = _classify(logind={"IdleAction": "hibernate"})
        assert any(i.key == "logind.idle_action.hibernate" and i.severity == "warning" for i in issues)

    def test_idle_action_hybrid_sleep_warns(self):
        issues = _classify(logind={"IdleAction": "hybrid-sleep"})
        assert any(i.key == "logind.idle_action.hybrid_sleep" and i.severity == "warning" for i in issues)

    def test_idle_action_ignore_does_not_warn(self):
        issues = _classify(logind={"IdleAction": "ignore"})
        assert not any(i.key.startswith("logind.idle_action.") for i in issues)

    def test_lid_switch_suspend_with_lid_emits_info(self):
        issues = _classify(logind={"HandleLidSwitch": "suspend"}, has_lid=True)
        assert any(i.key == "logind.lid_switch.suspend" and i.severity == "info" for i in issues)

    def test_lid_switch_suspend_without_lid_silent(self):
        issues = _classify(logind={"HandleLidSwitch": "suspend"}, has_lid=False)
        assert not any(i.key.startswith("logind.lid_switch.") for i in issues)

    def test_lid_switch_hibernate_emits_info_with_distinct_key(self):
        issues = _classify(logind={"HandleLidSwitch": "hibernate"}, has_lid=True)
        assert any(i.key == "logind.lid_switch.hibernate" for i in issues)

    def test_sleep_conf_suspend_disabled_emits_info(self):
        issues = _classify(sleep_conf={"AllowSuspend": "no"})
        assert any(i.key == "sleep_conf.suspend_disabled" and i.severity == "info" for i in issues)

    def test_suspend_target_masked_is_error(self):
        issues = _classify(targets={"suspend.target": "masked"})
        assert any(i.key == "targets.suspend.masked" and i.severity == "error" for i in issues)

    def test_clean_config_emits_no_issues(self):
        issues = _classify(
            logind={"IdleAction": "ignore", "HandleLidSwitch": "ignore"},
            sleep_conf={"AllowSuspend": "yes"},
            targets={"suspend.target": "enabled"},
            has_lid=True,
        )
        assert issues == []

"""Tests for fan_curve_eval.evaluate_curve."""
from types import SimpleNamespace

import pytest

from app.services.power.fan_curve_eval import evaluate_curve


def _cfg(**overrides):
    """Mock FanConfig with sensible defaults."""
    base = dict(
        curve_type="graph",
        curve_json='[{"temp":40,"pwm":30},{"temp":80,"pwm":100}]',
        flat_pwm_percent=None,
        target_temp_celsius=None,
        target_pwm_percent=None,
        mix_curve_a_id=None,
        mix_curve_b_id=None,
        mix_function=None,
        sync_fan_id=None,
        start_pwm_percent=None,
        stop_below_temp_celsius=None,
        response_time_seconds=0.0,
        pwm_steps=1,
        min_pwm_percent=0,
        max_pwm_percent=100,
        hysteresis_celsius=0.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_graph_interpolates():
    out = evaluate_curve(_cfg(), temp=60.0, prev_pwm=0, other_fan_pwms={},
                         profile_loader=lambda _id: [], dt_seconds=1.0)
    # 60 is midpoint of 40–80 → midpoint PWM (30 + 100) / 2 = 65
    assert out == 65


def test_flat_returns_constant():
    out = evaluate_curve(
        _cfg(curve_type="flat", flat_pwm_percent=42),
        temp=99.0, prev_pwm=0, other_fan_pwms={}, profile_loader=lambda _: [], dt_seconds=1.0
    )
    assert out == 42


def test_target_holds_at_target_temp():
    cfg = _cfg(curve_type="target", target_temp_celsius=70, target_pwm_percent=80)
    # Below target: linear ramp from (0,0) to (70,80)
    assert evaluate_curve(cfg, 35.0, 0, {}, lambda _: [], 1.0) == 40
    # At/above target: hold at target_pwm
    assert evaluate_curve(cfg, 70.0, 0, {}, lambda _: [], 1.0) == 80
    assert evaluate_curve(cfg, 95.0, 0, {}, lambda _: [], 1.0) == 80


def test_mix_function_max():
    cfg = _cfg(curve_type="mix", mix_curve_a_id=1, mix_curve_b_id=2, mix_function="max")
    profiles = {
        1: [{"temp": 40, "pwm": 30}, {"temp": 80, "pwm": 60}],
        2: [{"temp": 40, "pwm": 50}, {"temp": 80, "pwm": 100}],
    }
    # At 60°C: curve1 → 45, curve2 → 75 → max=75
    out = evaluate_curve(cfg, 60.0, 0, {}, profiles.get, 1.0)
    assert out == 75


def test_mix_function_sum_clamps_to_100():
    cfg = _cfg(curve_type="mix", mix_curve_a_id=1, mix_curve_b_id=2, mix_function="sum")
    profiles = {
        1: [{"temp": 40, "pwm": 60}, {"temp": 80, "pwm": 80}],
        2: [{"temp": 40, "pwm": 50}, {"temp": 80, "pwm": 70}],
    }
    out = evaluate_curve(cfg, 80.0, 0, {}, profiles.get, 1.0)
    assert out == 100  # 80 + 70 = 150 → clamped


def test_sync_copies_master_pwm():
    cfg = _cfg(curve_type="sync", sync_fan_id="hwmon0_pwm2")
    out = evaluate_curve(cfg, 50.0, 0, {"hwmon0_pwm2": 73}, lambda _: [], 1.0)
    assert out == 73


def test_sync_falls_back_to_prev_when_master_missing():
    cfg = _cfg(curve_type="sync", sync_fan_id="missing")
    out = evaluate_curve(cfg, 50.0, 40, {}, lambda _: [], 1.0)
    assert out == 40


def test_stop_below_temp_sets_pwm_zero():
    cfg = _cfg(stop_below_temp_celsius=35.0, hysteresis_celsius=2.0)
    out = evaluate_curve(cfg, 30.0, 50, {}, lambda _: [], 1.0)
    assert out == 0


def test_stop_below_temp_releases_at_threshold():
    cfg = _cfg(stop_below_temp_celsius=35.0, hysteresis_celsius=2.0)
    # Was at 0 (below stop), now at 60 → should resume normal curve
    out = evaluate_curve(cfg, 60.0, 0, {}, lambda _: [], 1.0)
    assert out == 65  # graph midpoint


def test_start_pwm_does_not_kick_in_when_curve_already_above():
    cfg = _cfg(start_pwm_percent=40)
    # Curve [(40,30),(80,100)] at 50°C → 47.5 → 48. Since 48 ≥ start_pwm (40),
    # no start bump. Result: 48.
    out = evaluate_curve(cfg, 50.0, 0, {}, lambda _: [], 1.0)
    assert out == 48


def test_start_pwm_kicks_in_when_curve_low():
    cfg = _cfg(curve_json='[{"temp":40,"pwm":10},{"temp":80,"pwm":100}]', start_pwm_percent=30)
    # At 42°C: curve → ~12. Prev was 0, so jump to max(12, 30) = 30
    out = evaluate_curve(cfg, 42.0, 0, {}, lambda _: [], 1.0)
    assert out == 30


def test_response_time_smooths_changes():
    cfg = _cfg(response_time_seconds=4.0)
    # dt=1, response=4 → α=0.25. Curve at 80°C gives 100, prev=20 → 0.25*100 + 0.75*20 = 40
    out = evaluate_curve(cfg, 80.0, 20, {}, lambda _: [], 1.0)
    assert out == 40


def test_pwm_steps_quantize():
    cfg = _cfg(pwm_steps=10)
    out = evaluate_curve(cfg, 60.0, 0, {}, lambda _: [], 1.0)  # raw 65 → quantize to 70
    assert out == 70


def test_min_max_clamp_applied_last():
    cfg = _cfg(min_pwm_percent=40, max_pwm_percent=90)
    # Curve gives 65, but min/max already pass through; raise min above raw
    cfg2 = _cfg(min_pwm_percent=80, max_pwm_percent=90)
    out = evaluate_curve(cfg2, 60.0, 0, {}, lambda _: [], 1.0)
    assert out == 80


def test_pipeline_order_emergency_handled_outside():
    # evaluate_curve never returns 100 forced — emergency override is the caller's job
    cfg = _cfg(curve_type="flat", flat_pwm_percent=20, max_pwm_percent=90)
    out = evaluate_curve(cfg, 200.0, 0, {}, lambda _: [], 1.0)
    assert out == 20

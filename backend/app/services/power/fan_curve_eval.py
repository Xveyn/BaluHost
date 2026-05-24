"""Curve type dispatch + post-processing pipeline.

Pipeline order (matters):
1. Resolve raw target from curve_type
2. stop_below_temp_celsius → may force 0
3. start_pwm_percent → minimum spin-up when prev was 0
4. response_time_seconds → exponential smoothing
5. pwm_steps → quantize
6. min/max clamp
Hysteresis and emergency override are applied by the caller (FanControlService).
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def evaluate_curve(
    config,                                            # FanConfig-shaped (real or SimpleNamespace)
    temp: Optional[float],
    prev_pwm: int,
    other_fan_pwms: Dict[str, int],
    profile_loader: Callable[[int], List[dict]],
    dt_seconds: float,
) -> int:
    """Compute target PWM (0-100) given config, temp, and previous PWM."""
    curve_type = getattr(config, "curve_type", "graph")

    # --- 1. Raw target per curve type ---
    if curve_type == "flat":
        target = int(config.flat_pwm_percent or 0)

    elif curve_type == "target":
        if temp is None or config.target_temp_celsius is None or config.target_pwm_percent is None:
            target = prev_pwm
        elif temp >= config.target_temp_celsius:
            target = int(config.target_pwm_percent)
        else:
            ratio = max(0.0, temp / config.target_temp_celsius)
            target = round(ratio * config.target_pwm_percent)

    elif curve_type == "mix":
        a = _interpolate(profile_loader(config.mix_curve_a_id) if config.mix_curve_a_id else [], temp)
        b = _interpolate(profile_loader(config.mix_curve_b_id) if config.mix_curve_b_id else [], temp)
        if config.mix_function == "sum":
            target = min(100, a + b)
        else:  # "max" or unknown defaults to max
            target = max(a, b)

    elif curve_type == "sync":
        target = other_fan_pwms.get(config.sync_fan_id or "", prev_pwm)

    else:  # "graph"
        points = _parse_curve_json(config.curve_json)
        target = _interpolate(points, temp)

    # --- 2. stop_below_temp_celsius ---
    if config.stop_below_temp_celsius is not None and temp is not None:
        hysteresis = getattr(config, "hysteresis_celsius", 0.0) or 0.0
        # While running, drop to 0 when temp falls below (threshold - hysteresis).
        # Once at 0, only resume when temp rises back above threshold.
        if prev_pwm == 0:
            if temp < config.stop_below_temp_celsius:
                return 0
        else:
            if temp < config.stop_below_temp_celsius - hysteresis:
                return 0

    # --- 3. start_pwm_percent ---
    if (
        config.start_pwm_percent is not None
        and prev_pwm == 0
        and target > 0
        and target < config.start_pwm_percent
    ):
        target = int(config.start_pwm_percent)

    # --- 4. response_time_seconds (exponential smoothing) ---
    rt = float(getattr(config, "response_time_seconds", 0.0) or 0.0)
    if rt > 0.0 and dt_seconds > 0.0:
        alpha = min(1.0, dt_seconds / rt)
        target = round(alpha * target + (1 - alpha) * prev_pwm)

    # --- 5. pwm_steps quantization ---
    steps = int(getattr(config, "pwm_steps", 1) or 1)
    if steps > 1:
        target = int((target + steps / 2) // steps) * steps

    # --- 6. min/max clamp ---
    min_pwm = int(getattr(config, "min_pwm_percent", 0) or 0)
    max_pwm = int(getattr(config, "max_pwm_percent", 100) or 100)
    target = max(min_pwm, min(max_pwm, target))

    return int(target)


def _interpolate(points: List[dict], temp: Optional[float]) -> int:
    if not points or temp is None:
        return 0
    pts = sorted(points, key=lambda p: p["temp"])
    if len(pts) == 1:
        return int(pts[0]["pwm"])
    if temp <= pts[0]["temp"]:
        return int(pts[0]["pwm"])
    if temp >= pts[-1]["temp"]:
        return int(pts[-1]["pwm"])
    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        if p1["temp"] <= temp <= p2["temp"]:
            ratio = (temp - p1["temp"]) / (p2["temp"] - p1["temp"])
            return round(p1["pwm"] + (p2["pwm"] - p1["pwm"]) * ratio)
    return int(pts[-1]["pwm"])


def _parse_curve_json(raw: Optional[str]) -> List[dict]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []

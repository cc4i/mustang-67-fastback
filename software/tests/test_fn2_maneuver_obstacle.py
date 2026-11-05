"""Verify FN-2: 7 Predefined Maneuvers, VL53L1X Emergency Brake, Reverse-to-Clearance, and Optical S-Curve Bypass."""

from __future__ import annotations

import pytest

from mustang_ai.config import RadxaPinConfig
from mustang_ai.features.maneuver_obstacle import (
    MANEUVER_LIBRARY,
    ManeuverObstacleSequencer,
)
from mustang_ai.protocol.messages import ToFReading, VisionFrameMetrics


@pytest.mark.parametrize(
    "maneuver_name",
    [
        "circle_left",
        "circle_right",
        "figure_eight",
        "slalom",
        "spin_wiggle",
        "u_turn_3pt",
        "patrol",
    ],
)
def test_all_7_predefined_maneuvers_complete_on_clear_path(
    pins: RadxaPinConfig,
    maneuver_name: str,
) -> None:
    seq = ManeuverObstacleSequencer(pins=pins)
    assert seq.start(maneuver_name, speed_scale=0.80) is True
    assert seq.is_active is True

    clear_tof = ToFReading(timestamp_s=1.0, distance_mm=900, valid=True, zone="CLEAR")
    vision = VisionFrameMetrics(
        timestamp_s=1.0,
        frame_seq=1,
        rgb_bytes=b"",
        left_clearance_score=210.0,
        right_clearance_score=210.0,
        preferred_bypass_dir=1,
        person_detected=False,
        person_bearing_deg=0.0,
    )
    steps = 0
    while seq.is_active and steps < 120:
        intent = seq.step(dt_sec=0.10, tof=clear_tof, vision=vision)
        steps += 1
        assert -15.0 <= intent.desired_steering_deg <= 15.0

    assert seq.is_active is False


def test_obstacle_avoidance_fsm_reverse_and_optical_s_curve_bypass(
    pins: RadxaPinConfig,
) -> None:
    seq = ManeuverObstacleSequencer(pins=pins)
    assert seq.start("circle_left", speed_scale=0.85) is True

    # Vision indicates LEFT side is much clearer than RIGHT side (`preferred_bypass_dir = -1`)
    vision_left_clear = VisionFrameMetrics(
        timestamp_s=1.0,
        frame_seq=10,
        rgb_bytes=b"",
        left_clearance_score=235.0,
        right_clearance_score=110.0,
        preferred_bypass_dir=-1,
        person_detected=False,
        person_bearing_deg=0.0,
    )

    # 1. Trigger obstacle at 95 mm (< 120 mm emergency stop threshold)
    blocked_tof = ToFReading(timestamp_s=1.0, distance_mm=95, valid=True, zone="EMERGENCY_STOP")
    intent_brake = seq.step(dt_sec=0.05, tof=blocked_tof, vision=vision_left_clear)
    assert seq.obstacle_state == "EVASIVE_REVERSE"
    assert intent_brake.desired_throttle == 0.0
    assert seq.preferred_bypass_dir == -1

    # 2. Next tick in EVASIVE_REVERSE while still < 240 mm backs up at -0.40 throttle
    intent_rev = seq.step(dt_sec=0.10, tof=blocked_tof, vision=vision_left_clear)
    assert seq.obstacle_state == "EVASIVE_REVERSE"
    assert intent_rev.desired_throttle == -0.40

    # 3. Once ToF reaches >= 240 mm (290 mm), transitions to EVASIVE_BYPASS_PASS (-15 deg left steer)
    clear_tof = ToFReading(timestamp_s=1.2, distance_mm=290, valid=True, zone="STANDOFF_HOLD")
    intent_pass = seq.step(dt_sec=0.10, tof=clear_tof, vision=vision_left_clear)
    assert seq.obstacle_state == "EVASIVE_BYPASS_PASS"
    assert intent_pass.desired_steering_deg == -15.0
    assert intent_pass.desired_throttle == 0.45

    # 4. Advance past 0.65 s into EVASIVE_BYPASS_REJOIN (+10 deg counter-steer)
    for _ in range(7):
        intent_rejoin = seq.step(dt_sec=0.10, tof=clear_tof, vision=vision_left_clear)
    assert seq.obstacle_state == "EVASIVE_BYPASS_REJOIN"
    assert intent_rejoin.desired_steering_deg == 10.0

    # 5. Advance past 1.10 s -> resumes CLEAR maneuver execution
    for _ in range(6):
        seq.step(dt_sec=0.10, tof=clear_tof, vision=vision_left_clear)
    assert seq.obstacle_state == "CLEAR"
    assert len(MANEUVER_LIBRARY) == 7

"""Verify FN-3: Equidistant Fisheye Bearing Math, PD Steering, 4-Zone 350 mm Standoff, and Target-Loss Search."""

from __future__ import annotations

import time

import pytest

from mustang_ai.config import RadxaPinConfig
from mustang_ai.features.person_follower import PersonFollowerController
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.protocol.messages import ToFReading, VisionFrameMetrics


def test_equidistant_fisheye_bearing_and_pd_steering_signs(
    pins: RadxaPinConfig,
    sim_camera: SimFisheyeCamera,
) -> None:
    follower = PersonFollowerController(pins=pins)
    follower.configure(enabled=True, target_mode="body_legs_torso", standoff_mm=350)

    rgb = sim_camera.capture_frame()
    # Target centered at [200, 400, 800, 600] -> 0 deg bearing
    metrics_center = sim_camera.extract_vision_metrics(rgb, target_box_2d=(200, 400, 800, 600))
    assert metrics_center.person_detected is True
    assert metrics_center.person_bearing_deg == pytest.approx(0.0, abs=1e-4)

    # Target on right side [200, 650, 800, 850] -> positive bearing and right (+steer_deg) turn
    metrics_right = sim_camera.extract_vision_metrics(rgb, target_box_2d=(200, 650, 800, 850))
    assert metrics_right.person_bearing_deg > 0.0
    tof_follow = ToFReading(timestamp_s=time.monotonic(), distance_mm=650, valid=True, zone="CLEAR")
    intent_right = follower.step(dt_sec=0.066, tof=tof_follow, vision=metrics_right)
    assert intent_right.desired_steering_deg > 0.0
    assert intent_right.desired_throttle > 0.0

    # Target on left side [200, 150, 800, 350] -> negative bearing and left (-steer_deg) turn
    metrics_left = sim_camera.extract_vision_metrics(rgb, target_box_2d=(200, 150, 800, 350))
    assert metrics_left.person_bearing_deg < 0.0
    intent_left = follower.step(dt_sec=0.066, tof=tof_follow, vision=metrics_left)
    assert intent_left.desired_steering_deg < 0.0


def test_4_zone_vl53l1x_standoff_throttle_law(pins: RadxaPinConfig) -> None:
    follower = PersonFollowerController(pins=pins)
    follower.configure(enabled=True, target_mode="body_legs_torso", standoff_mm=350)
    vision = VisionFrameMetrics(
        timestamp_s=time.monotonic(),
        frame_seq=1,
        rgb_bytes=b"",
        left_clearance_score=200.0,
        right_clearance_score=200.0,
        preferred_bypass_dir=1,
        person_detected=True,
        person_bearing_deg=0.0,
        person_box_2d=(200, 420, 780, 580),
    )

    # Zone 1: < 120 mm (Emergency Stop -> 0.0 throttle)
    tof_stop = ToFReading(timestamp_s=1.0, distance_mm=95, valid=True, zone="EMERGENCY_STOP")
    intent_stop = follower.step(dt_sec=0.066, tof=tof_stop, vision=vision)
    assert follower.state == "EMERGENCY_STOP"
    assert intent_stop.desired_throttle == pytest.approx(0.0)

    # Zone 2: 120..220 mm (Personal Space Backup -> -0.32 reverse)
    tof_back = ToFReading(timestamp_s=1.0, distance_mm=180, valid=True, zone="PERSONAL_SPACE")
    intent_back = follower.step(dt_sec=0.066, tof=tof_back, vision=vision)
    assert follower.state == "PERSONAL_SPACE_BACKUP"
    assert intent_back.desired_throttle == pytest.approx(-0.32)

    # Zone 3: 220..450 mm (350 mm Standoff Hold -> 0.0 throttle + HEART_EYES)
    tof_hold = ToFReading(timestamp_s=1.0, distance_mm=350, valid=True, zone="STANDOFF_HOLD")
    intent_hold = follower.step(dt_sec=0.066, tof=tof_hold, vision=vision)
    assert follower.state == "STANDOFF_HOLD"
    assert intent_hold.desired_throttle == pytest.approx(0.0)
    assert intent_hold.hud_emoji == "HEART_EYES"

    # Zone 4: > 450 mm (Proportional approach throttle)
    tof_far = ToFReading(timestamp_s=1.0, distance_mm=820, valid=True, zone="CLEAR")
    intent_far = follower.step(dt_sec=0.066, tof=tof_far, vision=vision)
    assert follower.state == "APPROACHING"
    assert 0.28 < intent_far.desired_throttle <= 0.65


def test_target_loss_after_1500ms_triggers_stop_and_confused_emoji(pins: RadxaPinConfig) -> None:
    follower = PersonFollowerController(pins=pins)
    follower.configure(enabled=True, target_mode="body_legs_torso", standoff_mm=350)
    follower.last_seen_ts = time.monotonic() - 2.0  # > 1.50 s ago

    tof = ToFReading(timestamp_s=time.monotonic(), distance_mm=800, valid=True, zone="CLEAR")
    vision_none = VisionFrameMetrics(
        timestamp_s=time.monotonic(),
        frame_seq=5,
        rgb_bytes=b"",
        left_clearance_score=200.0,
        right_clearance_score=200.0,
        preferred_bypass_dir=1,
        person_detected=False,
        person_bearing_deg=0.0,
    )
    intent_lost = follower.step(dt_sec=0.066, tof=tof, vision=vision_none)
    assert follower.state == "TARGET_LOST"
    assert intent_lost.desired_throttle == 0.0
    assert intent_lost.hud_emoji == "CONFUSED"

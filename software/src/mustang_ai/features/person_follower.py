"""Function 3 (`person_follower.py`): Equidistant Fisheye Bearing PD Steering +
4-Zone `350 mm` `VL53L1X` Laser Standoff Person-Following controller (`v3.2.0`).
"""

from __future__ import annotations

import time

from mustang_ai.config import RadxaPinConfig
from mustang_ai.protocol.messages import ControlIntent, ToFReading, VisionFrameMetrics


class PersonFollowerController:
    """`15 Hz` coupled visual-laser person-following controller (`Function 3`)."""

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        self.pins = pins or RadxaPinConfig()
        self.enabled: bool = False
        self.target_mode: str = "body_legs_torso"
        self.standoff_mm: int = self.pins.follow_standoff_mm
        self.hint_box_2d: tuple[int, int, int, int] | None = None
        self.last_bearing_deg: float = 0.0
        self._has_prev_bearing: bool = False
        self.last_seen_ts: float = 0.0
        self.state: str = "DISABLED"

    def configure(
        self,
        enabled: bool,
        target_mode: str = "body_legs_torso",
        target_box_2d: list[int] | tuple[int, int, int, int] | None = None,
        standoff_mm: int | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.target_mode = target_mode or "body_legs_torso"
        if standoff_mm is not None:
            self.standoff_mm = max(200, min(600, int(standoff_mm)))
        if target_box_2d is not None and len(target_box_2d) == 4:
            self.hint_box_2d = (
                int(target_box_2d[0]),
                int(target_box_2d[1]),
                int(target_box_2d[2]),
                int(target_box_2d[3]),
            )
        if self.enabled:
            self.last_seen_ts = time.monotonic()
            self._has_prev_bearing = False
            self.last_bearing_deg = 0.0
        else:
            self.state = "DISABLED"
            self._has_prev_bearing = False

    def step(
        self,
        dt_sec: float,
        tof: ToFReading,
        vision: VisionFrameMetrics,
    ) -> ControlIntent:
        """Compute PD steering and 4-zone longitudinal standoff throttle from `VisionFrameMetrics` + `ToFReading`."""
        now = time.monotonic()
        if not self.enabled:
            self.state = "DISABLED"
            return ControlIntent(
                timestamp_s=now,
                source_mode="IDLE",
                desired_throttle=0.0,
                desired_steering_deg=0.0,
                hud_emoji="CRUISE",
                hud_caption="FOLLOW OFF",
            )

        if vision.person_detected:
            self.last_seen_ts = now
            bearing = vision.person_bearing_deg
            d_bearing = (
                (bearing - self.last_bearing_deg) / max(0.02, dt_sec) if self._has_prev_bearing else 0.0
            )
            self.last_bearing_deg = bearing
            self._has_prev_bearing = True
        else:
            self._has_prev_bearing = False
            if (now - self.last_seen_ts) > self.pins.follow_lost_timeout_sec:
                self.state = "TARGET_LOST"
                return ControlIntent(
                    timestamp_s=now,
                    source_mode="FOLLOW_PERSON",
                    desired_throttle=0.0,
                    desired_steering_deg=0.0,
                    hud_emoji="CONFUSED",
                    hud_caption="WHERE'D U GO?",
                )
            bearing = self.last_bearing_deg
            d_bearing = 0.0

        # Lateral PD steering law
        raw_steer = self.pins.follow_kp_steer * bearing + self.pins.follow_kd_steer * d_bearing
        steer_deg = max(
            -self.pins.max_steering_deg,
            min(self.pins.max_steering_deg, round(raw_steer, 2)),
        )

        # 4-Zone Longitudinal Standoff Law
        if not tof.valid or tof.distance_mm < self.pins.emergency_stop_mm:
            self.state = "EMERGENCY_STOP"
            return ControlIntent(
                timestamp_s=now,
                source_mode="FOLLOW_PERSON",
                desired_throttle=0.0,
                desired_steering_deg=steer_deg,
                hud_emoji="ALERT_STOP",
                hud_caption="TOO CLOSE!",
            )

        if tof.distance_mm < self.pins.follow_backup_mm:
            self.state = "PERSONAL_SPACE_BACKUP"
            return ControlIntent(
                timestamp_s=now,
                source_mode="FOLLOW_PERSON",
                desired_throttle=-0.32,
                desired_steering_deg=-steer_deg,
                hud_emoji="WINK",
                hud_caption="SPACE BACKUP",
            )

        approach_threshold_mm = max(self.pins.follow_approach_mm, self.standoff_mm + 100)
        if tof.distance_mm <= approach_threshold_mm:
            self.state = "STANDOFF_HOLD"
            return ControlIntent(
                timestamp_s=now,
                source_mode="FOLLOW_PERSON",
                desired_throttle=0.0,
                desired_steering_deg=steer_deg,
                hud_emoji="HEART_EYES",
                hud_caption=f"LOCKED {tof.distance_mm}MM",
            )

        self.state = "APPROACHING"
        approach_thr = min(0.65, max(0.28, 0.28 + 0.00055 * (tof.distance_mm - self.standoff_mm)))
        return ControlIntent(
            timestamp_s=now,
            source_mode="FOLLOW_PERSON",
            desired_throttle=round(approach_thr, 3),
            desired_steering_deg=steer_deg,
            hud_emoji="HEART_EYES",
            hud_caption="FOLLOWING YOU",
        )

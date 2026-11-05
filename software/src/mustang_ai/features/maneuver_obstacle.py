"""Function 2 (`maneuver_obstacle.py`): 7 Predefined Tricks + Optical ROI Clearance Scorer +
Auto-Reverse (`~150 mm`) & `±15°` S-Curve Obstacle Bypass state machine (`v3.2.0`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from mustang_ai.config import RadxaPinConfig
from mustang_ai.protocol.messages import ControlIntent, ToFReading, VisionFrameMetrics


@dataclass(frozen=True, slots=True)
class ManeuverStep:
    """Single timed kinematic primitive inside a predefined maneuver macro."""

    duration_sec: float
    throttle: float
    steering_deg: float
    hud_emoji: str
    hud_caption: str


MANEUVER_LIBRARY: dict[str, tuple[ManeuverStep, ...]] = {
    "circle_left": (
        ManeuverStep(3.6, 0.55, -15.0, "COOL_SHADES", "CIRCLE LEFT"),
    ),
    "circle_right": (
        ManeuverStep(3.6, 0.55, 15.0, "COOL_SHADES", "CIRCLE RIGHT"),
    ),
    "figure_eight": (
        ManeuverStep(3.2, 0.55, -15.0, "COOL_SHADES", "FIG-8 LEFT"),
        ManeuverStep(0.4, 0.50, 0.0, "WINK", "CROSSOVER"),
        ManeuverStep(3.2, 0.55, 15.0, "COOL_SHADES", "FIG-8 RIGHT"),
    ),
    "slalom": (
        ManeuverStep(0.65, 0.55, -15.0, "WINK", "SLALOM CONE 1 L"),
        ManeuverStep(1.15, 0.55, 15.0, "COOL_SHADES", "SLALOM CONE 2 R"),
        ManeuverStep(1.15, 0.55, -15.0, "WINK", "SLALOM CONE 3 L"),
        ManeuverStep(1.15, 0.55, 15.0, "COOL_SHADES", "SLALOM CONE 4 R"),
        ManeuverStep(0.65, 0.52, -14.0, "HAPPY", "SLALOM FINISH!"),
    ),
    "spin_wiggle": (
        ManeuverStep(0.28, 0.60, -15.0, "LAUGH", "WIGGLE L!"),
        ManeuverStep(0.28, -0.60, 15.0, "LAUGH", "WIGGLE R!"),
        ManeuverStep(0.28, 0.60, -15.0, "ANGRY_REV", "REV IT UP!"),
        ManeuverStep(0.28, -0.60, 15.0, "HAPPY", "YEAH 67!"),
    ),
    "u_turn_3pt": (
        ManeuverStep(1.1, 0.48, -15.0, "THINKING", "3PT TURN 1"),
        ManeuverStep(1.0, -0.45, 15.0, "THINKING", "3PT TURN 2"),
        ManeuverStep(1.1, 0.50, -12.0, "HAPPY", "3PT DONE"),
    ),
    "patrol": (
        ManeuverStep(1.8, 0.48, 0.0, "CRUISE", "PATROL FWD"),
        ManeuverStep(1.1, 0.45, -15.0, "THINKING", "SCAN LEFT"),
        ManeuverStep(1.8, 0.48, 0.0, "CRUISE", "PATROL BACK"),
    ),
}


class ManeuverObstacleSequencer:
    """`15 Hz` trajectory executor with 5-state Auto-Reverse + S-Curve Bypass obstacle avoidance."""

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        self.pins = pins or RadxaPinConfig()
        self.active_maneuver: str = ""
        self.steps: list[ManeuverStep] = []
        self.step_index: int = 0
        self.step_elapsed_sec: float = 0.0
        self.speed_scale: float = 1.0
        # States: CLEAR | CAUTION_SLOW | REFLEX_BRAKE | EVASIVE_REVERSE | EVASIVE_BYPASS_PASS | EVASIVE_BYPASS_REJOIN
        self.obstacle_state: str = "CLEAR"
        self.evasive_elapsed_sec: float = 0.0
        self.preferred_bypass_dir: int = 1  # -1 = steer Left, +1 = steer Right
        self.bypass_count: int = 0

    @property
    def is_active(self) -> bool:
        return bool(self.active_maneuver) and self.step_index < len(self.steps)

    def start(self, maneuver_name: str, speed_scale: float = 1.0) -> bool:
        name = (maneuver_name or "").strip().lower()
        if name not in MANEUVER_LIBRARY:
            return False
        self.active_maneuver = name
        self.steps = list(MANEUVER_LIBRARY[name])
        self.step_index = 0
        self.step_elapsed_sec = 0.0
        self.speed_scale = max(0.4, min(1.0, float(speed_scale)))
        self.obstacle_state = "CLEAR"
        self.evasive_elapsed_sec = 0.0
        return True

    def stop(self) -> None:
        self.active_maneuver = ""
        self.steps = []
        self.step_index = 0
        self.step_elapsed_sec = 0.0
        self.obstacle_state = "CLEAR"
        self.evasive_elapsed_sec = 0.0

    def step(
        self,
        dt_sec: float,
        tof: ToFReading,
        vision: VisionFrameMetrics,
    ) -> ControlIntent:
        """Advance maneuver or evasive obstacle bypass by `dt_sec` and emit `ControlIntent`."""
        now = time.monotonic()
        if not self.is_active:
            self.active_maneuver = ""
            self.obstacle_state = "CLEAR"
            return ControlIntent(
                timestamp_s=now,
                source_mode="IDLE",
                desired_throttle=0.0,
                desired_steering_deg=0.0,
                active_maneuver="",
                hud_emoji="CRUISE",
                hud_caption="MANEUVER DONE",
            )

        cur = self.steps[self.step_index]

        # Phase 1: EVASIVE_REVERSE (~150 mm back-up until ToF >= 240 mm or 1.20 s max)
        if self.obstacle_state == "EVASIVE_REVERSE":
            self.evasive_elapsed_sec += dt_sec
            if (tof.valid and tof.distance_mm >= self.pins.bypass_reverse_target_mm) or self.evasive_elapsed_sec >= 1.20:
                self.obstacle_state = "EVASIVE_BYPASS_PASS"
                self.evasive_elapsed_sec = 0.0
                self.bypass_count += 1
            else:
                return ControlIntent(
                    timestamp_s=now,
                    source_mode="EVASIVE_BYPASS",
                    desired_throttle=-0.40,
                    desired_steering_deg=-float(self.preferred_bypass_dir) * 8.0,
                    active_maneuver=self.active_maneuver,
                    hud_emoji="SURPRISED",
                    hud_caption="REV ~150MM",
                )

        # Phase 2 & 3: EVASIVE_BYPASS_PASS (0.65 s) -> EVASIVE_BYPASS_REJOIN (0.45 s)
        if self.obstacle_state in ("EVASIVE_BYPASS_PASS", "EVASIVE_BYPASS_REJOIN"):
            if not tof.valid or tof.distance_mm < self.pins.emergency_stop_mm:
                self.preferred_bypass_dir = int(vision.preferred_bypass_dir)
                self.obstacle_state = "EVASIVE_REVERSE"
                self.evasive_elapsed_sec = 0.0
                return ControlIntent(
                    timestamp_s=now,
                    source_mode="EVASIVE_BYPASS",
                    desired_throttle=0.0,
                    desired_steering_deg=0.0,
                    active_maneuver=self.active_maneuver,
                    hud_emoji="ALERT_STOP",
                    hud_caption=f"BRAKE {tof.distance_mm}MM",
                )

            self.evasive_elapsed_sec += dt_sec
            if self.evasive_elapsed_sec <= 0.65:
                self.obstacle_state = "EVASIVE_BYPASS_PASS"
                return ControlIntent(
                    timestamp_s=now,
                    source_mode="EVASIVE_BYPASS",
                    desired_throttle=0.45,
                    desired_steering_deg=float(self.preferred_bypass_dir) * 15.0,
                    active_maneuver=self.active_maneuver,
                    hud_emoji="THINKING",
                    hud_caption="BYPASS LEFT" if self.preferred_bypass_dir < 0 else "BYPASS RIGHT",
                )
            if self.evasive_elapsed_sec <= 1.10:
                self.obstacle_state = "EVASIVE_BYPASS_REJOIN"
                return ControlIntent(
                    timestamp_s=now,
                    source_mode="EVASIVE_BYPASS",
                    desired_throttle=0.42,
                    desired_steering_deg=-float(self.preferred_bypass_dir) * 10.0,
                    active_maneuver=self.active_maneuver,
                    hud_emoji="HAPPY",
                    hud_caption="PATH CLEAR!",
                )
            self.obstacle_state = "CLEAR"
            self.evasive_elapsed_sec = 0.0

        # Check front laser before applying forward motion
        if cur.throttle > 0.0 and (not tof.valid or tof.distance_mm < self.pins.emergency_stop_mm):
            self.preferred_bypass_dir = int(vision.preferred_bypass_dir)
            self.obstacle_state = "EVASIVE_REVERSE"
            self.evasive_elapsed_sec = 0.0
            return ControlIntent(
                timestamp_s=now,
                source_mode="EVASIVE_BYPASS",
                desired_throttle=0.0,
                desired_steering_deg=0.0,
                active_maneuver=self.active_maneuver,
                hud_emoji="ALERT_STOP",
                hud_caption=f"BRAKE {tof.distance_mm}MM",
            )

        scaled_throttle = cur.throttle * self.speed_scale
        if cur.throttle > 0.0 and tof.distance_mm < self.pins.caution_slow_mm:
            self.obstacle_state = "CAUTION_SLOW"
            scaled_throttle = min(scaled_throttle, self.pins.caution_max_throttle)
        else:
            self.obstacle_state = "CLEAR"

        self.step_elapsed_sec += dt_sec
        if self.step_elapsed_sec >= cur.duration_sec:
            self.step_index += 1
            self.step_elapsed_sec = 0.0

        return ControlIntent(
            timestamp_s=now,
            source_mode="MANEUVER",
            desired_throttle=round(scaled_throttle, 3),
            desired_steering_deg=cur.steering_deg,
            active_maneuver=self.active_maneuver,
            hud_emoji=cur.hud_emoji,
            hud_caption=cur.hud_caption,
        )

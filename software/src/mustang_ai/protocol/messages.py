"""Immutable inter-tier wire messages exchanged across the 50 Hz, 15 Hz, and AsyncIO tiers (`v3.2.0`)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

ToFZone = Literal[
    "EMERGENCY_STOP",
    "PERSONAL_SPACE",
    "CAUTION_SLOW",
    "STANDOFF_HOLD",
    "CLEAR",
]

ControlSourceMode = Literal[
    "IDLE",
    "MANUAL_TOOL",
    "MANEUVER",
    "EVASIVE_BYPASS",
    "FOLLOW_PERSON",
]


@dataclass(frozen=True, slots=True)
class ToFReading:
    """50 Hz front laser rangefinder snapshot (`VL53L1X` on `I2C3` `0x29`, Harness `H4-C`)."""

    timestamp_s: float
    distance_mm: int
    valid: bool
    zone: ToFZone
    latency_ms: float = 0.0

    @staticmethod
    def classify_zone(
        distance_mm: int,
        valid: bool,
        emergency_stop_mm: int = 120,
        personal_space_mm: int = 220,
        caution_slow_mm: int = 260,
        follow_approach_mm: int = 450,
    ) -> ToFZone:
        if not valid or distance_mm < emergency_stop_mm:
            return "EMERGENCY_STOP"
        if distance_mm < personal_space_mm:
            return "PERSONAL_SPACE"
        if distance_mm < caution_slow_mm:
            return "CAUTION_SLOW"
        if distance_mm <= follow_approach_mm:
            return "STANDOFF_HOLD"
        return "CLEAR"


@dataclass(frozen=True, slots=True)
class VisionFrameMetrics:
    """15 Hz vision features extracted from the `OV5647` `160°` fisheye camera (`Harness H1-A`)."""

    timestamp_s: float
    frame_seq: int
    rgb_bytes: bytes
    left_clearance_score: float
    right_clearance_score: float
    preferred_bypass_dir: Literal[-1, 1]
    person_detected: bool
    person_bearing_deg: float
    person_box_2d: tuple[int, int, int, int] | None = None
    person_cx_norm: float = 0.0
    person_cy_norm: float = 0.0
    person_height_norm: float = 0.0
    target_kind: str = "body_legs_torso"


@dataclass(frozen=True, slots=True)
class AudioChunkMetrics:
    """40 ms (`640`-sample @ `16 kHz`) audio frame from `INMP441` with echo guard & barge-in (`Harness H1-B`)."""

    timestamp_s: float
    pcm16_bytes: bytes
    rms_level: float
    muted_by_echo_guard: bool
    barge_in_triggered: bool


@dataclass(frozen=True, slots=True)
class ControlIntent:
    """Desired motion command published by Tier 1 (`15 Hz`) and checked by Tier 0's `100 ms` Deadman Watchdog."""

    timestamp_s: float = field(default_factory=time.monotonic)
    source_mode: ControlSourceMode = "IDLE"
    desired_throttle: float = 0.0
    desired_steering_deg: float = 0.0
    active_maneuver: str = ""
    hud_emoji: str = "CRUISE"
    hud_caption: str = "CRUISE READY"


@dataclass(frozen=True, slots=True)
class CompiledActuatorCommand:
    """Final hardware command emitted by Tier 0 (`50 Hz`) after ToF reflex and Deadman Watchdog enforcement."""

    timestamp_s: float
    applied_throttle: float
    applied_steering_deg: float
    motor_in1_duty: float
    motor_in2_duty: float
    servo_pulse_us: int
    emergency_brake: bool
    watchdog_tripped: bool
    override_reason: str = "NONE"


@dataclass(frozen=True, slots=True)
class HUDFrameState:
    """State rendered at `15 Hz` onto the `1.28"` Round `GC9A01` `240×240` rear window HUD (`Harness H2`)."""

    timestamp_s: float
    emoji: str
    caption: str
    tof_mm: int
    steering_deg: float
    throttle: float = 0.0
    voice_rms: float = 0.0
    alert_override: bool = False


@dataclass(frozen=True, slots=True)
class GeminiStreamEvent:
    """Event emitted by `GeminiLiveSessionProtocol.receive_events()` (`TEXT` or `NON_BLOCKING` Tool Call)."""

    timestamp_s: float
    event_type: Literal["tool_call", "text", "disconnect"]
    tool_name: str = ""
    tool_call_id: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    text: str = ""

"""Atomic inter-tier `StateBus` exchanging immutable `@dataclass(frozen=True, slots=True)` messages (`v3.2.0`)."""

from __future__ import annotations

import time

from mustang_ai.protocol.messages import (
    AudioChunkMetrics,
    CompiledActuatorCommand,
    ControlIntent,
    HUDFrameState,
    ToFReading,
    VisionFrameMetrics,
)


class StateBus:
    """Lock-free atomic state exchange between Tier 0 (`50 Hz`), Tier 1 (`15 Hz`), and Tier 2 (`AsyncIO`).

    Because every message (`ToFReading`, `VisionFrameMetrics`, `ControlIntent`, `CompiledActuatorCommand`,
    `HUDFrameState`) is `@dataclass(frozen=True, slots=True)`, attribute rebinding is atomic in Python
    and readers never observe partially mutated fields.
    """

    def __init__(self) -> None:
        now = time.monotonic()
        self.tof: ToFReading = ToFReading(
            timestamp_s=now,
            distance_mm=850,
            valid=True,
            zone="CLEAR",
        )
        self.vision: VisionFrameMetrics = VisionFrameMetrics(
            timestamp_s=now,
            frame_seq=0,
            rgb_bytes=b"",
            left_clearance_score=200.0,
            right_clearance_score=200.0,
            preferred_bypass_dir=1,
            person_detected=False,
            person_bearing_deg=0.0,
        )
        self.audio: AudioChunkMetrics = AudioChunkMetrics(
            timestamp_s=now,
            pcm16_bytes=b"",
            rms_level=0.0,
            muted_by_echo_guard=False,
            barge_in_triggered=False,
        )
        self.intent: ControlIntent = ControlIntent(
            timestamp_s=now,
            source_mode="IDLE",
            desired_throttle=0.0,
            desired_steering_deg=0.0,
        )
        self.actuator_cmd: CompiledActuatorCommand = CompiledActuatorCommand(
            timestamp_s=now,
            applied_throttle=0.0,
            applied_steering_deg=0.0,
            motor_in1_duty=0.0,
            motor_in2_duty=0.0,
            servo_pulse_us=1500,
            emergency_brake=False,
            watchdog_tripped=False,
            override_reason="NONE",
        )
        self.hud: HUDFrameState = HUDFrameState(
            timestamp_s=now,
            emoji="CRUISE",
            caption="CRUISE READY",
            tof_mm=850,
            steering_deg=0.0,
        )

    def publish_tof(self, reading: ToFReading) -> None:
        self.tof = reading

    def publish_vision(self, metrics: VisionFrameMetrics) -> None:
        self.vision = metrics

    def publish_audio(self, metrics: AudioChunkMetrics) -> None:
        self.audio = metrics

    def publish_intent(self, intent: ControlIntent) -> None:
        self.intent = intent

    def publish_actuator_cmd(self, cmd: CompiledActuatorCommand) -> None:
        self.actuator_cmd = cmd

    def publish_hud(self, state: HUDFrameState) -> None:
        self.hud = state

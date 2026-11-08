"""Tier 0 (`watchdog_reflex.py`): `50 Hz` (`20 ms`) ToF Reflex Safety Governor & `100 ms` Deadman Watchdog (`v3.2.0`)."""

from __future__ import annotations

import threading
import time

from mustang_ai.config import RadxaPinConfig
from mustang_ai.protocol.hal_contracts import DriveActuatorProtocol, RangefinderProtocol
from mustang_ai.protocol.messages import CompiledActuatorCommand
from mustang_ai.runtime.state_bus import StateBus


class WatchdogReflexGovernor:
    """Tier 0 `50 Hz` (`20.0 ms`) safety governor enforcing:
    1. `100 ms` Deadman Watchdog (`now - intent.timestamp_s > 0.100`) -> `DRV8833` Short-Brake + `0.0°` steer.
    2. Fail-Closed ToF I2C Fault (`not tof.valid`) -> Blocks all forward throttle (`override_reason="TOF_SENSOR_FAULT"`).
    3. `< 20 ms` Front Obstacle Reflex (`tof.distance_mm < 120 mm` while `desired_throttle > 0`) -> `DRV8833` Short-Brake.
    4. Caution Zone Speed Cap (`120 <= tof.distance_mm < 260 mm`) -> Clamps forward throttle to `<= 0.35`.
    """

    def __init__(
        self,
        rangefinder: RangefinderProtocol,
        actuators: DriveActuatorProtocol,
        bus: StateBus,
        pins: RadxaPinConfig | None = None,
    ) -> None:
        self.rangefinder = rangefinder
        self.actuators = actuators
        self.bus = bus
        self.pins = pins or RadxaPinConfig()
        self.reflex_brake_count: int = 0
        self.watchdog_trip_count: int = 0
        self._running: bool = False
        self._thread: threading.Thread | None = None

    def step_once(self, now_s: float | None = None) -> CompiledActuatorCommand:
        """Execute a single `20 ms` (`50 Hz`) reflex & watchdog evaluation tick."""
        now = now_s if now_s is not None else time.monotonic()
        tof = self.rangefinder.read_tof()
        self.bus.publish_tof(tof)

        intent = self.bus.intent
        intent_age_s = max(0.0, now - intent.timestamp_s)

        clamped_steer = max(
            -self.pins.max_steering_deg,
            min(self.pins.max_steering_deg, float(intent.desired_steering_deg)),
        )
        desired_thr = max(-1.0, min(1.0, float(intent.desired_throttle)))

        emergency_brake = False
        watchdog_tripped = False
        override_reason = "NONE"
        applied_thr = desired_thr

        # 1. 100 ms Deadman Watchdog check
        if intent_age_s > self.pins.deadman_timeout_sec:
            watchdog_tripped = True
            emergency_brake = True
            applied_thr = 0.0
            clamped_steer = 0.0
            override_reason = "DEADMAN_WATCHDOG_100MS"
            self.watchdog_trip_count += 1
        # 2. Fail-closed I2C ToF sensor fault check
        elif not tof.valid and desired_thr > 0.0:
            emergency_brake = True
            applied_thr = 0.0
            override_reason = "TOF_SENSOR_FAULT"
            self.reflex_brake_count += 1
        # 3. < 20 ms Front Obstacle Reflex Brake (< 120 mm)
        elif tof.valid and tof.distance_mm < self.pins.emergency_stop_mm and desired_thr > 0.0:
            emergency_brake = True
            applied_thr = 0.0
            override_reason = f"TOF_REFLEX_BRAKE_{tof.distance_mm}MM"
            self.reflex_brake_count += 1
        # 4. Caution Slow Zone (120..260 mm)
        elif tof.valid and tof.distance_mm < self.pins.caution_slow_mm and desired_thr > self.pins.caution_max_throttle:
            applied_thr = self.pins.caution_max_throttle
            override_reason = f"CAUTION_CAP_{tof.distance_mm}MM"

        if emergency_brake:
            in1_duty, in2_duty = 1.0, 1.0
        elif applied_thr > 0.01:
            in1_duty, in2_duty = abs(applied_thr), 0.0
        elif applied_thr < -0.01:
            in1_duty, in2_duty = 0.0, abs(applied_thr)
        else:
            in1_duty, in2_duty = 0.0, 0.0

        steer_norm = clamped_steer / max(1.0, self.pins.max_steering_deg)
        half_span_us = (self.pins.servo_max_pulse_us - self.pins.servo_min_pulse_us) / 2.0
        servo_pulse_us = int(round(self.pins.servo_center_pulse_us + steer_norm * half_span_us))

        cmd = CompiledActuatorCommand(
            timestamp_s=now,
            applied_throttle=round(applied_thr, 3),
            applied_steering_deg=round(clamped_steer, 2),
            motor_in1_duty=round(in1_duty, 3),
            motor_in2_duty=round(in2_duty, 3),
            servo_pulse_us=servo_pulse_us,
            emergency_brake=emergency_brake,
            watchdog_tripped=watchdog_tripped,
            override_reason=override_reason,
        )
        self.actuators.apply_command(cmd)
        self.bus.publish_actuator_cmd(cmd)
        return cmd

    def start_background_thread(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="Tier0-Reflex-50Hz", daemon=True)
        self._thread.start()

    def stop_background_thread(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None
        self.actuators.emergency_coast_all()

    def _run_loop(self) -> None:
        period_s = 1.0 / float(self.pins.tof_poll_hz)
        while self._running:
            t0 = time.monotonic()
            try:
                self.step_once(now_s=t0)
            except Exception:
                self.reflex_brake_count += 1
                try:
                    self.actuators.emergency_coast_all()
                except Exception:
                    pass
            elapsed = time.monotonic() - t0
            sleep_s = max(0.001, period_s - elapsed)
            time.sleep(sleep_s)

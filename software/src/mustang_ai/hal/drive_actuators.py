"""`DRV8833` N25 motor (`H3-C/H4-A`) + `1.7g` steering servo (`H4-B`) HAL backends (`SimDriveActuator` & `RadxaDriveActuator`)."""

from __future__ import annotations

import pathlib
import time

from mustang_ai.config import RadxaPinConfig
from mustang_ai.protocol.messages import CompiledActuatorCommand


class SimDriveActuator:
    """Deterministic simulated motor + servo actuator satisfying `DriveActuatorProtocol`."""

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        self.pins = pins or RadxaPinConfig()
        self.last_command: CompiledActuatorCommand = CompiledActuatorCommand(
            timestamp_s=time.monotonic(),
            applied_throttle=0.0,
            applied_steering_deg=0.0,
            motor_in1_duty=0.0,
            motor_in2_duty=0.0,
            servo_pulse_us=self.pins.servo_center_pulse_us,
            emergency_brake=False,
            watchdog_tripped=False,
            override_reason="INIT",
        )
        self.command_history: list[CompiledActuatorCommand] = []

    def apply_command(self, cmd: CompiledActuatorCommand) -> None:
        self.last_command = cmd
        self.command_history.append(cmd)
        if len(self.command_history) > 500:
            self.command_history.pop(0)

    def emergency_coast_all(self) -> None:
        coast_cmd = CompiledActuatorCommand(
            timestamp_s=time.monotonic(),
            applied_throttle=0.0,
            applied_steering_deg=0.0,
            motor_in1_duty=0.0,
            motor_in2_duty=0.0,
            servo_pulse_us=self.pins.servo_center_pulse_us,
            emergency_brake=False,
            watchdog_tripped=False,
            override_reason="COAST_SHUTDOWN",
        )
        self.apply_command(coast_cmd)


class RadxaDriveActuator(SimDriveActuator):
    """Physical Linux `sysfs` PWM driver (`PWM8/PWM9` DRV8833 + `PWM14` Servo) on Radxa Zero 3W."""

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        super().__init__(pins=pins)
        self._has_sysfs_pwm = pathlib.Path("/sys/class/pwm").exists()

    def apply_command(self, cmd: CompiledActuatorCommand) -> None:
        super().apply_command(cmd)
        if not self._has_sysfs_pwm:
            return
        try:
            motor_period_ns = int(1_000_000_000 // self.pins.motor_pwm_freq_hz)
            servo_period_ns = int(1_000_000_000 // self.pins.servo_pwm_freq_hz)
            self._write_sysfs_pwm(
                self.pins.motor_in1_pwm_chip,
                self.pins.motor_in1_pwm_chan,
                motor_period_ns,
                int(cmd.motor_in1_duty * motor_period_ns),
            )
            self._write_sysfs_pwm(
                self.pins.motor_in2_pwm_chip,
                self.pins.motor_in2_pwm_chan,
                motor_period_ns,
                int(cmd.motor_in2_duty * motor_period_ns),
            )
            self._write_sysfs_pwm(
                self.pins.servo_pwm_chip,
                self.pins.servo_pwm_chan,
                servo_period_ns,
                int(cmd.servo_pulse_us * 1000),
            )
        except OSError:
            self._has_sysfs_pwm = False

    @staticmethod
    def _write_sysfs_pwm(chip: int, chan: int, period_ns: int, duty_ns: int) -> None:
        base = pathlib.Path(f"/sys/class/pwm/pwmchip{chip}/pwm{chan}")
        if not base.exists():
            export = pathlib.Path(f"/sys/class/pwm/pwmchip{chip}/export")
            if export.exists():
                export.write_text(str(chan), encoding="utf-8")
        if base.exists():
            (base / "period").write_text(str(period_ns), encoding="utf-8")
            (base / "duty_cycle").write_text(str(duty_ns), encoding="utf-8")
            (base / "enable").write_text("1", encoding="utf-8")

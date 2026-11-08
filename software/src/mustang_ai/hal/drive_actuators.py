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

    def __init__(self, pins: RadxaPinConfig | None = None, *, pwm_root: pathlib.Path | None = None) -> None:
        super().__init__(pins=pins)
        self._pwm_root = pwm_root or pathlib.Path("/sys/class/pwm")
        self._has_sysfs_pwm = self._pwm_root.exists()
        self.hardware_ready: bool = self._has_sysfs_pwm and any(self._pwm_root.glob("pwmchip*"))
        self.last_error: str = ""
        self._configured_periods: dict[tuple[int, int], int] = {}

    def apply_command(self, cmd: CompiledActuatorCommand) -> None:
        super().apply_command(cmd)
        if not self._pwm_root.exists():
            self._has_sysfs_pwm = False
            self.hardware_ready = False
            return
        self._has_sysfs_pwm = True
        motor_period_ns = int(1_000_000_000 // self.pins.motor_pwm_freq_hz)
        servo_period_ns = int(1_000_000_000 // self.pins.servo_pwm_freq_hz)
        channels = (
            (
                self.pins.motor_in1_pwm_chip,
                self.pins.motor_in1_pwm_chan,
                motor_period_ns,
                max(0, min(motor_period_ns, int(cmd.motor_in1_duty * motor_period_ns))),
            ),
            (
                self.pins.motor_in2_pwm_chip,
                self.pins.motor_in2_pwm_chan,
                motor_period_ns,
                max(0, min(motor_period_ns, int(cmd.motor_in2_duty * motor_period_ns))),
            ),
            (
                self.pins.servo_pwm_chip,
                self.pins.servo_pwm_chan,
                servo_period_ns,
                max(0, min(servo_period_ns, int(cmd.servo_pulse_us * 1000))),
            ),
        )
        any_ok = False
        for chip, chan, period_ns, duty_ns in channels:
            try:
                self._write_sysfs_pwm(chip, chan, period_ns, duty_ns)
                any_ok = True
            except OSError as exc:
                self.last_error = f"pwmchip{chip}/pwm{chan}: {exc}"
        self.hardware_ready = any_ok

    def _write_sysfs_pwm(self, chip: int, chan: int, period_ns: int, duty_ns: int) -> None:
        chip_dir = self._pwm_root / f"pwmchip{chip}"
        base = chip_dir / f"pwm{chan}"
        if not base.exists():
            export = chip_dir / "export"
            if export.exists():
                export.write_text(str(chan), encoding="utf-8")
        if not base.exists():
            raise OSError(f"Missing PWM channel directory {base}")

        key = (chip, chan)
        duty_file = base / "duty_cycle"
        period_file = base / "period"
        enable_file = base / "enable"

        if self._configured_periods.get(key) != period_ns:
            # Kernel sysfs PWM rejects period < current duty_cycle with EINVAL; zero duty_cycle first.
            try:
                duty_file.write_text("0", encoding="utf-8")
            except OSError:
                pass
            period_file.write_text(str(period_ns), encoding="utf-8")
            duty_file.write_text(str(duty_ns), encoding="utf-8")
            enable_file.write_text("1", encoding="utf-8")
            self._configured_periods[key] = period_ns
        else:
            duty_file.write_text(str(duty_ns), encoding="utf-8")

    def close(self) -> None:
        self.emergency_coast_all()

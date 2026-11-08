"""`VL53L1X` Time-of-Flight front laser rangefinder HAL backends (`SimRangefinder` & `RadxaVL53L1X`)."""

from __future__ import annotations

import time
from typing import Callable

from mustang_ai.config import RadxaPinConfig
from mustang_ai.protocol.messages import ToFReading


class SimRangefinder:
    """Deterministic simulated `VL53L1X` rangefinder (`Harness H4-C`) supporting fault injection and arena ray-casts."""

    def __init__(
        self,
        pins: RadxaPinConfig | None = None,
        initial_distance_mm: int = 850,
        distance_provider: Callable[[], int] | None = None,
    ) -> None:
        self.pins = pins or RadxaPinConfig()
        self._distance_mm: int = initial_distance_mm
        self._valid: bool = True
        self._distance_provider = distance_provider
        self.closed: bool = False
        self.last_reading: ToFReading | None = None

    def set_distance_mm(self, distance_mm: int, valid: bool = True) -> None:
        """Set synthetic range (`mm`) or inject an I2C sensor fault (`valid=False`)."""
        self._distance_mm = int(distance_mm)
        self._valid = bool(valid)

    def read_tof(self) -> ToFReading:
        t0 = time.perf_counter()
        if self._distance_provider is not None and self._valid:
            dist = int(self._distance_provider())
        else:
            dist = self._distance_mm

        valid = self._valid and (10 <= dist <= 4000)
        zone = ToFReading.classify_zone(
            distance_mm=dist if valid else 0,
            valid=valid,
            emergency_stop_mm=self.pins.emergency_stop_mm,
            personal_space_mm=self.pins.follow_backup_mm,
            caution_slow_mm=self.pins.caution_slow_mm,
            follow_approach_mm=self.pins.follow_approach_mm,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        reading = ToFReading(
            timestamp_s=time.monotonic(),
            distance_mm=dist if valid else 0,
            valid=valid,
            zone=zone,
            latency_ms=round(latency_ms, 4),
        )
        self.last_reading = reading
        return reading

    def close(self) -> None:
        self.closed = True


class RadxaVL53L1X:
    """Physical `VL53L1X` I2C3 (`0x29`) driver for Radxa Zero 3W (`Harness H4-C`) with fail-closed fallback."""

    # ST VL53L1X 16-bit register addresses
    _REG_IDENTIFICATION_MODEL_ID = 0x010F
    _REG_SYSTEM_MODE_START = 0x0087
    _REG_RESULT_RANGE_STATUS = 0x0089
    _REG_RESULT_FINAL_CROSSTALK_CORRECTED_RANGE_MM = 0x0096

    def __init__(
        self,
        pins: RadxaPinConfig | None = None,
        fallback_distance_mm: int = 850,
        strict_hardware: bool = True,
    ) -> None:
        self.pins = pins or RadxaPinConfig()
        self.fallback_distance_mm = fallback_distance_mm
        self.strict_hardware = strict_hardware
        self.closed: bool = False
        self.hardware_ready: bool = False
        self.last_error: str = ""
        self._bus: object | None = None
        self._ranging_started: bool = False
        self.last_reading: ToFReading | None = None

    def _get_or_open_bus(self) -> object:
        if self._bus is not None:
            return self._bus
        import smbus2  # type: ignore[import-not-found]

        self._bus = smbus2.SMBus(self.pins.i2c_bus)
        return self._bus

    def _write_reg16(self, bus: object, reg16: int, payload: list[int]) -> None:
        import smbus2  # type: ignore[import-not-found]

        if hasattr(smbus2, "i2c_msg") and hasattr(bus, "i2c_rdwr"):
            msg = smbus2.i2c_msg.write(
                self.pins.vl53l1x_addr,
                [(reg16 >> 8) & 0xFF, reg16 & 0xFF, *[b & 0xFF for b in payload]],
            )
            bus.i2c_rdwr(msg)  # type: ignore[attr-defined]
        else:
            bus.write_i2c_block_data(  # type: ignore[attr-defined]
                self.pins.vl53l1x_addr, (reg16 >> 8) & 0xFF, [reg16 & 0xFF, *[b & 0xFF for b in payload]]
            )

    def _read_reg16(self, bus: object, reg16: int, length: int) -> list[int]:
        import smbus2  # type: ignore[import-not-found]

        if hasattr(smbus2, "i2c_msg") and hasattr(bus, "i2c_rdwr"):
            w_msg = smbus2.i2c_msg.write(self.pins.vl53l1x_addr, [(reg16 >> 8) & 0xFF, reg16 & 0xFF])
            r_msg = smbus2.i2c_msg.read(self.pins.vl53l1x_addr, length)
            bus.i2c_rdwr(w_msg, r_msg)  # type: ignore[attr-defined]
            return list(r_msg)
        if hasattr(bus, "read_byte_data") and length == 2:
            hi = int(bus.read_byte_data(self.pins.vl53l1x_addr, reg16))  # type: ignore[attr-defined]
            lo = int(bus.read_byte_data(self.pins.vl53l1x_addr, reg16 + 1))  # type: ignore[attr-defined]
            return [hi, lo]
        raise OSError("Unsupported SMBus interface for 16-bit VL53L1X register access")

    def _ensure_ranging_started(self, bus: object) -> None:
        if self._ranging_started:
            return
        model_bytes = self._read_reg16(bus, self._REG_IDENTIFICATION_MODEL_ID, 2)
        model_id = (model_bytes[0] << 8) | model_bytes[1]
        if model_id not in (0xEACC, 0xEA00) and model_id == 0:
            raise OSError(f"Unexpected VL53L1X model ID: 0x{model_id:04X}")
        self._write_reg16(bus, self._REG_SYSTEM_MODE_START, [0x40])
        self._ranging_started = True
        self.hardware_ready = True

    def read_tof(self) -> ToFReading:
        t0 = time.perf_counter()
        dist_mm = 0 if self.strict_hardware else self.fallback_distance_mm
        valid = not self.strict_hardware
        try:
            bus = self._get_or_open_bus()
            self._ensure_ranging_started(bus)
            hi, lo = self._read_reg16(bus, self._REG_RESULT_FINAL_CROSSTALK_CORRECTED_RANGE_MM, 2)
            raw = ((hi & 0xFF) << 8) | (lo & 0xFF)
            if 10 <= raw <= 4000:
                dist_mm = raw
                valid = True
                self.last_error = ""
            else:
                valid = False
                dist_mm = 0
                self.last_error = f"Out-of-range VL53L1X reading: {raw} mm"
        except Exception as exc:
            self.hardware_ready = False
            self.last_error = f"{type(exc).__name__}: {exc}"
            if self.strict_hardware:
                valid = False
                dist_mm = 0
            else:
                valid = True
                dist_mm = self.fallback_distance_mm

        zone = ToFReading.classify_zone(
            distance_mm=dist_mm,
            valid=valid,
            emergency_stop_mm=self.pins.emergency_stop_mm,
            personal_space_mm=self.pins.follow_backup_mm,
            caution_slow_mm=self.pins.caution_slow_mm,
            follow_approach_mm=self.pins.follow_approach_mm,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        reading = ToFReading(
            timestamp_s=time.monotonic(),
            distance_mm=dist_mm,
            valid=valid,
            zone=zone,
            latency_ms=round(latency_ms, 4),
        )
        self.last_reading = reading
        return reading

    def close(self) -> None:
        self.closed = True
        if self._bus is not None:
            try:
                close_fn = getattr(self._bus, "close", None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                pass
            self._bus = None

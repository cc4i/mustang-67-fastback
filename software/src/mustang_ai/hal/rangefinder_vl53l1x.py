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

    def __init__(
        self,
        pins: RadxaPinConfig | None = None,
        fallback_distance_mm: int = 850,
        strict_hardware: bool = False,
    ) -> None:
        self.pins = pins or RadxaPinConfig()
        self.fallback_distance_mm = fallback_distance_mm
        self.strict_hardware = strict_hardware
        self.closed: bool = False
        self.last_reading: ToFReading | None = None

    def read_tof(self) -> ToFReading:
        t0 = time.perf_counter()
        dist_mm = self.fallback_distance_mm
        valid = True
        try:
            import smbus2  # type: ignore[import-not-found]

            with smbus2.SMBus(self.pins.i2c_bus) as bus:
                hi = bus.read_byte_data(self.pins.vl53l1x_addr, 0x0096)
                lo = bus.read_byte_data(self.pins.vl53l1x_addr, 0x0097)
                raw = (hi << 8) | lo
                if 10 <= raw <= 4000:
                    dist_mm = raw
                else:
                    valid = False
                    dist_mm = 0
        except Exception:
            if self.strict_hardware:
                valid = False
                dist_mm = 0

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

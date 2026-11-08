"""Hardware Bring-Up CLI (`mustang-ai doctor --harness {H1,H2,H3,H4,H5,all}`) for Cable Harnesses H1..H5."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Sequence

from mustang_ai.config import CORE_12_EMOJIS, GeminiERConfig
from mustang_ai.hal.audio_i2s import RadxaI2SAudio, SimAudioStream
from mustang_ai.hal.camera_ov5647 import RadxaOV5647, SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import RadxaGC9A01Display, SimGC9A01Display
from mustang_ai.hal.drive_actuators import RadxaDriveActuator, SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import RadxaVL53L1X, SimRangefinder
from mustang_ai.hal.tts_piper import LocalPiperTTS, SimPiperTTS
from mustang_ai.protocol.messages import ControlIntent, HUDFrameState
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor


@dataclass(frozen=True, slots=True)
class HarnessCheckResult:
    """Result of an individual cable harness diagnostic check."""

    harness_id: str
    title: str
    passed: bool
    mode: str
    latency_ms: float
    details: dict[str, object]


def check_h1_roof_pod(mode: str, config: GeminiERConfig | None = None) -> HarnessCheckResult:
    """Verify H1: Roof WaymoPod (OV5647 MIPI-CSI Camera + INMP441 I2S0 Mic)."""
    cfg = config or GeminiERConfig()
    t0 = time.monotonic()
    camera = SimFisheyeCamera(cfg.camera) if mode == "sim" else RadxaOV5647(cfg.camera)
    audio = SimAudioStream(cfg.pins) if mode == "sim" else RadxaI2SAudio(cfg.pins)
    rgb = camera.capture_frame()
    metrics = camera.extract_vision_metrics(rgb)
    jpeg = camera.encode_telemetry_jpeg(rgb, tof_mm=850, steer_deg=0.0, emoji="CRUISE", mode="DOCTOR")
    aud_metrics = audio.read_mic_chunk()
    cam_hw_ok = True if mode == "sim" else getattr(camera, "hardware_ready", False)
    aud_hw_ok = True if mode == "sim" else getattr(audio, "hardware_ready", False)
    if hasattr(camera, "close"):
        camera.close()
    if hasattr(audio, "close"):
        audio.close()
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    passed = bool(
        cam_hw_ok
        and aud_hw_ok
        and len(rgb) == cfg.camera.width * cfg.camera.height * 3
        and len(jpeg) > 500
        and metrics.frame_seq >= 1
        and len(aud_metrics.pcm16_bytes) == cfg.pins.audio_chunk_samples * 2
    )
    return HarnessCheckResult(
        harness_id="H1",
        title="Roof WaymoPod (OV5647 MIPI-CSI + INMP441 I2S0 Mic)",
        passed=passed,
        mode=mode,
        latency_ms=elapsed_ms,
        details={
            "v4l2_device": cfg.camera.v4l2_device,
            "camera_hardware_ready": cam_hw_ok,
            "audio_hardware_ready": aud_hw_ok,
            "rgb_bytes": len(rgb),
            "jpeg_bytes": len(jpeg),
            "left_clearance_score": metrics.left_clearance_score,
            "right_clearance_score": metrics.right_clearance_score,
            "pcm16_bytes": len(aud_metrics.pcm16_bytes),
            "mic_rms": aud_metrics.rms_level,
        },
    )


def check_h2_rear_hud(mode: str, config: GeminiERConfig | None = None) -> HarnessCheckResult:
    """Verify H2: Rear Fastback 1.28-inch Round GC9A01 SPI3 HUD (12-emoji sweep)."""
    cfg = config or GeminiERConfig()
    t0 = time.monotonic()
    display = SimGC9A01Display(cfg.pins) if mode == "sim" else RadxaGC9A01Display(cfg.pins)
    rendered_frames = 0
    for idx, (emo, caption) in enumerate(CORE_12_EMOJIS):
        state = HUDFrameState(
            timestamp_s=time.monotonic(),
            emoji=emo,
            caption=caption,
            tof_mm=700 - idx * 40,
            steering_deg=float((idx % 3 - 1) * 8),
            throttle=0.35,
            voice_rms=0.45,
        )
        byte_count = display.render_and_push(state)
        if byte_count == 240 * 240 * 2:
            rendered_frames += 1
    disp_hw_ok = True if mode == "sim" else getattr(display, "hardware_ready", False)
    if hasattr(display, "close"):
        display.close()
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    passed = bool(disp_hw_ok and rendered_frames == len(CORE_12_EMOJIS))
    return HarnessCheckResult(
        harness_id="H2",
        title="Rear Fastback 1.28-inch Round GC9A01 SPI3 HUD",
        passed=passed,
        mode=mode,
        latency_ms=elapsed_ms,
        details={
            "spi_bus": cfg.pins.spi_bus,
            "spi_device": cfg.pins.spi_device,
            "display_hardware_ready": disp_hw_ok,
            "emojis_tested": rendered_frames,
            "expected_emojis": len(CORE_12_EMOJIS),
            "rgb565_frame_bytes": len(display.last_rgb565_bytes),
        },
    )


def check_h3_cabin_deck(mode: str, config: GeminiERConfig | None = None) -> HarnessCheckResult:
    """Verify H3: Lower Cabin Deck (LocalPiperTTS + MAX98357A I2S Amp + DRV8833 H-Bridge)."""
    cfg = config or GeminiERConfig()
    t0 = time.monotonic()
    tts = SimPiperTTS(cfg.tts) if mode == "sim" else LocalPiperTTS(cfg.tts)
    audio = SimAudioStream(cfg.pins) if mode == "sim" else RadxaI2SAudio(cfg.pins)
    act = SimDriveActuator(cfg.pins) if mode == "sim" else RadxaDriveActuator(cfg.pins)
    pcm16, synth_ms = tts.synthesize_to_pcm16("Mustang sixty seven cabin audio check.")
    rms = audio.play_pcm16_async(pcm16)
    audio.stop_playback()
    act.emergency_coast_all()
    aud_hw_ok = True if mode == "sim" else getattr(audio, "hardware_ready", False)
    act_hw_ok = True if mode == "sim" else getattr(act, "hardware_ready", False)
    if hasattr(audio, "close"):
        audio.close()
    if hasattr(act, "close"):
        act.close()
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    passed = bool(
        aud_hw_ok
        and act_hw_ok
        and len(pcm16) > 1000
        and rms > 0.0
        and act.last_command.servo_pulse_us == cfg.pins.servo_center_pulse_us
    )
    return HarnessCheckResult(
        harness_id="H3",
        title="Lower Cabin Deck (LocalPiperTTS + MAX98357A I2S0 + DRV8833 H-Bridge)",
        passed=passed,
        mode=mode,
        latency_ms=elapsed_ms,
        details={
            "audio_hardware_ready": aud_hw_ok,
            "actuator_hardware_ready": act_hw_ok,
            "tts_pcm16_bytes": len(pcm16),
            "tts_synthesis_ms": synth_ms,
            "speaker_rms": rms,
            "drv8833_coast_reason": act.last_command.override_reason,
        },
    )


def check_h4_front_engine_bay(mode: str, config: GeminiERConfig | None = None) -> HarnessCheckResult:
    """Verify H4: Front Engine Bay (VL53L1X I2C3 ToF + GH-S37D Servo + N20/N25 Motor)."""
    cfg = config or GeminiERConfig()
    t0 = time.monotonic()
    tof = SimRangefinder(cfg.pins) if mode == "sim" else RadxaVL53L1X(cfg.pins)
    act = SimDriveActuator(cfg.pins) if mode == "sim" else RadxaDriveActuator(cfg.pins)
    bus = StateBus()
    gov = WatchdogReflexGovernor(rangefinder=tof, actuators=act, bus=bus, pins=cfg.pins)

    now = time.monotonic()
    bus.publish_intent(ControlIntent(timestamp_s=now, source_mode="MANUAL_TOOL", desired_throttle=0.0, desired_steering_deg=-6.0))
    cmd_left = gov.step_once(now_s=now + 0.01)
    bus.publish_intent(ControlIntent(timestamp_s=now + 0.02, source_mode="MANUAL_TOOL", desired_throttle=0.0, desired_steering_deg=6.0))
    cmd_right = gov.step_once(now_s=now + 0.03)
    reading = tof.read_tof()
    tof.close()
    act.emergency_coast_all()
    act_hw_ok = True if mode == "sim" else getattr(act, "hardware_ready", False)
    if hasattr(act, "close"):
        act.close()
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    passed = bool(
        act_hw_ok
        and reading.valid
        and reading.distance_mm > 0
        and cmd_left.servo_pulse_us < cfg.pins.servo_center_pulse_us < cmd_right.servo_pulse_us
    )
    return HarnessCheckResult(
        harness_id="H4",
        title="Front Engine Bay (VL53L1X I2C3 ToF + GH-S37D Servo + N20/N25 Motor)",
        passed=passed,
        mode=mode,
        latency_ms=elapsed_ms,
        details={
            "i2c_bus": cfg.pins.i2c_bus,
            "i2c_address": hex(cfg.pins.vl53l1x_addr),
            "tof_valid": reading.valid,
            "tof_distance_mm": reading.distance_mm,
            "actuator_hardware_ready": act_hw_ok,
            "servo_left_us": cmd_left.servo_pulse_us,
            "servo_center_us": cfg.pins.servo_center_pulse_us,
            "servo_right_us": cmd_right.servo_pulse_us,
        },
    )


def check_h5_power_and_watchdog(mode: str, config: GeminiERConfig | None = None) -> HarnessCheckResult:
    """Verify H5: Power Distribution & 100 ms Deadman Watchdog Fail-Closed Interlock."""
    cfg = config or GeminiERConfig()
    t0 = time.monotonic()
    bus = StateBus()
    tof = SimRangefinder(cfg.pins, initial_distance_mm=800) if mode == "sim" else RadxaVL53L1X(cfg.pins)
    act = SimDriveActuator(cfg.pins) if mode == "sim" else RadxaDriveActuator(cfg.pins)
    gov = WatchdogReflexGovernor(rangefinder=tof, actuators=act, bus=bus, pins=cfg.pins)

    now = time.monotonic()
    bus.publish_intent(
        ControlIntent(
            timestamp_s=now,
            source_mode="MANUAL_TOOL",
            desired_throttle=0.45,
            desired_steering_deg=4.0,
        )
    )
    cmd_fresh = gov.step_once(now_s=now + 0.010)  # +10 ms (fresh)
    cmd_stale = gov.step_once(now_s=now + 0.150)  # +150 ms (> 100 ms watchdog)

    tof.close()
    act.emergency_coast_all()
    act_hw_ok = True if mode == "sim" else getattr(act, "hardware_ready", False)
    if hasattr(act, "close"):
        act.close()
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    passed = bool(
        act_hw_ok
        and not cmd_fresh.watchdog_tripped
        and (cmd_fresh.motor_in1_duty > 0.0 if cmd_fresh.override_reason == "NONE" else cmd_fresh.emergency_brake)
        and cmd_stale.watchdog_tripped
        and cmd_stale.emergency_brake
    )
    return HarnessCheckResult(
        harness_id="H5",
        title="Power Distribution & 100 ms Deadman Watchdog Governor",
        passed=passed,
        mode=mode,
        latency_ms=elapsed_ms,
        details={
            "actuator_hardware_ready": act_hw_ok,
            "fresh_10ms_watchdog_tripped": cmd_fresh.watchdog_tripped,
            "stale_150ms_watchdog_tripped": cmd_stale.watchdog_tripped,
            "stale_150ms_emergency_brake": cmd_stale.emergency_brake,
            "watchdog_trip_count": gov.watchdog_trip_count,
        },
    )


def run_doctor(harness: str = "all", mode: str = "sim") -> dict[str, object]:
    """Run one or all harness checks and return a structured report dictionary."""
    dispatch = {
        "H1": check_h1_roof_pod,
        "H2": check_h2_rear_hud,
        "H3": check_h3_cabin_deck,
        "H4": check_h4_front_engine_bay,
        "H5": check_h5_power_and_watchdog,
    }
    selected = list(dispatch.keys()) if harness.lower() == "all" else [harness.upper()]
    results = [dispatch[h](mode) for h in selected]
    all_passed = all(r.passed for r in results)
    return {
        "status": "PASS" if all_passed else "FAIL",
        "mode": mode,
        "harnesses_checked": len(results),
        "results": [asdict(r) for r in results],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mustang-ai doctor",
        description="Cable Harness H1..H5 diagnostic verifier for 1967 Mustang Fastback AI Edition.",
    )
    parser.add_argument(
        "--harness",
        choices=["H1", "H2", "H3", "H4", "H5", "all"],
        default="all",
        help="Target cable harness to verify (default: all).",
    )
    parser.add_argument(
        "--mode",
        choices=["sim", "radxa"],
        default="sim",
        help="Hardware backend mode ('sim' for pre-hardware verification, 'radxa' for physical SBC).",
    )
    args = parser.parse_args(argv)
    report = run_doctor(harness=args.harness, mode=args.mode)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

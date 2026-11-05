"""End-to-End 2D VirtualArena Simulation Tests (Closed-Loop Kinematics + Ray-Cast ToF + Fisheye Vision + MockGemini)."""

from __future__ import annotations

import asyncio
import math
import time

from pathlib import Path

from mustang_ai.cli import doctor, run_agent
from mustang_ai.config import GeminiERConfig
from mustang_ai.hal.audio_i2s import SimAudioStream
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.hal.tts_piper import LocalPiperTTS, SimPiperTTS
from mustang_ai.runtime.gemini_live_stream import GeminiLiveOrchestrator
from mustang_ai.runtime.local_autonomy_loop import LocalAutonomyEngine
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor
from mustang_ai.simulator.mac_live_workbench import (
    MacLiveWorkbench,
    coalesce_turn_tool_calls,
    run_voice_e2e_session,
)
from mustang_ai.simulator.mock_gemini_session import MockGeminiLiveSession
from mustang_ai.simulator.virtual_arena import VirtualArena


def test_virtual_arena_closed_loop_obstacle_bypass(
    config: GeminiERConfig,
    sim_display: SimGC9A01Display,
    sim_tts: SimPiperTTS,
    sim_audio: SimAudioStream,
) -> None:
    arena = VirtualArena(camera_config=config.camera, car_x_mm=0.0, car_y_mm=0.0, car_heading_rad=0.0)

    bus = StateBus()
    tof = SimRangefinder(config.pins, distance_provider=arena.compute_tof_distance_mm)
    cam = SimFisheyeCamera(config.camera, frame_provider=arena.render_fisheye_rgb)
    act = SimDriveActuator(config.pins)
    gov = WatchdogReflexGovernor(rangefinder=tof, actuators=act, bus=bus, pins=config.pins)
    engine = LocalAutonomyEngine(
        camera=cam,
        audio=sim_audio,
        tts=sim_tts,
        display=sim_display,
        bus=bus,
        pins=config.pins,
    )
    engine.handle_tool_call("execute_maneuver", {"maneuver_name": "circle_right", "speed_scale": 0.85})

    visited_states: set[str] = set()
    for step in range(45):
        if step == 3:
            # Place obstacle directly in front of the moving car (<120 mm surface distance) while desired_throttle > 0
            arena.add_obstacle(
                x_mm=arena.car_x_mm + 205.0 * math.cos(arena.car_heading_rad),
                y_mm=arena.car_y_mm + 205.0 * math.sin(arena.car_heading_rad),
                radius_mm=55.0,
            )
        if step == 18:
            arena.obstacles.clear()
        gov.step_once(now_s=time.monotonic())
        engine.step_once(dt_sec=0.05)
        cmd = gov.step_once(now_s=time.monotonic())
        arena.step_kinematics(dt_sec=0.05, cmd=cmd)
        visited_states.add(engine.maneuver_seq.obstacle_state)

    assert "EVASIVE_REVERSE" in visited_states
    assert "EVASIVE_BYPASS_PASS" in visited_states
    assert gov.reflex_brake_count >= 1


def test_virtual_arena_closed_loop_person_following_with_mock_gemini(
    config: GeminiERConfig,
    sim_display: SimGC9A01Display,
    sim_tts: SimPiperTTS,
    sim_audio: SimAudioStream,
) -> None:
    arena = VirtualArena(camera_config=config.camera, car_x_mm=0.0, car_y_mm=0.0, car_heading_rad=0.0)
    arena.set_person_position(780.0, 160.0)

    bus = StateBus()
    tof = SimRangefinder(config.pins, distance_provider=arena.compute_tof_distance_mm)
    cam = SimFisheyeCamera(config.camera, frame_provider=arena.render_fisheye_rgb)
    act = SimDriveActuator(config.pins)
    gov = WatchdogReflexGovernor(rangefinder=tof, actuators=act, bus=bus, pins=config.pins)
    engine = LocalAutonomyEngine(
        camera=cam,
        audio=sim_audio,
        tts=sim_tts,
        display=sim_display,
        bus=bus,
        pins=config.pins,
    )

    mock_session = MockGeminiLiveSession()
    mock_session.enqueue_tool_call(
        "set_follow_person_mode",
        {"enabled": True, "target_mode": "body_legs_torso", "standoff_mm": 350},
    )
    orchestrator = GeminiLiveOrchestrator(
        session=mock_session,
        camera=cam,
        autonomy=engine,
        bus=bus,
    )
    asyncio.run(orchestrator.process_incoming_events())
    assert engine.person_follower.enabled is True

    px, py = arena.person_xy_mm or (780.0, 160.0)
    initial_dist = math.hypot(px - arena.car_x_mm, py - arena.car_y_mm)
    for _ in range(35):
        gov.step_once(now_s=time.monotonic())
        engine.step_once(dt_sec=0.05)
        cmd = gov.step_once(now_s=time.monotonic())
        arena.step_kinematics(dt_sec=0.05, cmd=cmd)

    final_dist = math.hypot(px - arena.car_x_mm, py - arena.car_y_mm)
    assert arena.car_x_mm > 100.0
    assert arena.car_y_mm > 5.0
    assert final_dist < initial_dist


def test_cli_doctor_and_self_test_entrypoints() -> None:
    assert doctor.main(["--harness", "all", "--mode", "sim"]) == 0
    assert run_agent.main(["--self-test"]) == 0
    assert run_agent.main(["simulate"]) == 0


def test_local_piper_onnx_tts_and_voice_e2e_workbench(
    tmp_path: Path,
    config: GeminiERConfig,
) -> None:
    tts = LocalPiperTTS(config.tts)
    pcm, latency_ms = tts.synthesize_to_pcm16(
        "I am feeling stellar today! My battery is charged and I am ready to roll."
    )
    assert tts.backend_used.startswith("piper-onnx:")
    assert len(pcm) > 20_000
    assert latency_ms > 0.0

    # Verify multi-call speech coalescing prevents overlapping TTS calls in a single turn
    raw_calls = [
        ("speak_with_emoji", {"emoji": "HAPPY", "hud_message": "SENTENCE 1", "spoken_text": "Sentence one!"}, "c1"),
        ("execute_maneuver", {"maneuver_name": "slalom", "speed_scale": 0.9}, "c2"),
        ("speak_with_emoji", {"emoji": "COOL_SHADES", "hud_message": "SENTENCE 2", "spoken_text": "Sentence two!"}, "c3"),
    ]
    coalesced = coalesce_turn_tool_calls(raw_calls)
    speak_only = [c for c in coalesced if c[0] == "speak_with_emoji"]
    assert len(speak_only) == 1
    assert speak_only[0][1]["spoken_text"] == "Sentence one! Sentence two!"

    # Verify Slalom 4-Cone course setup + 2D Track Radar + Multimodal Visual Object Q&A
    wb = MacLiveWorkbench(audible_speaker=False, use_cloud_live=False)
    slalom_turn = wb.submit_voice_utterance("Weave through the slalom!", advance_steps=10)
    assert slalom_turn["active_maneuver"] == "slalom"
    assert len(wb.arena.course_markers) == 4
    assert [m.label for m in wb.arena.course_markers] == ["CONE 1", "CONE 2", "CONE 3", "CONE 4"]
    assert len(wb.arena.planned_path_xy_mm) > 20

    wb.set_showcase_object("stop_sign")
    vision_turn = wb.submit_voice_utterance("What's this object in front of you?", advance_steps=2)
    assert vision_turn["showcase_object"] == "stop_sign"
    assert "Stop Sign" in vision_turn["spoken_reply_text"] or "stop sign" in vision_turn["spoken_reply_text"].lower()

    snap = wb.snapshot_telemetry()
    assert len(snap["arena_png_b64"]) > 1000
    assert len(snap["cam_jpeg_b64"]) > 1000
    assert len(snap["hud_png_b64"]) > 1000

    e2e = run_voice_e2e_session(audible_speaker=False, use_cloud_live=False, repo_root=tmp_path)
    assert e2e["status"] == "PASS"
    assert e2e["tts_backend_used"].startswith("piper-onnx:")
    assert e2e["turns_executed"] == 4
    assert e2e["barge_in_verified"] is True

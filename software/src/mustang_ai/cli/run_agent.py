"""Main CLI (`mustang-ai`) for running the 3-Tier Autonomous Control Pipeline or `--self-test`."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from typing import Sequence

from mustang_ai.cli import doctor
from mustang_ai.config import CORE_12_EMOJIS, GeminiERConfig
from mustang_ai.features.maneuver_obstacle import MANEUVER_LIBRARY
from mustang_ai.features.voice_emoji_hud import VoiceEmojiHUDController
from mustang_ai.hal.audio_i2s import SimAudioStream
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.hal.tts_piper import SimPiperTTS
from mustang_ai.runtime.gemini_live_stream import (
    GeminiLiveOrchestrator,
    build_gemini_tool_declarations,
)
from mustang_ai.runtime.local_autonomy_loop import LocalAutonomyEngine
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor
from mustang_ai.simulator.mac_interaction_sim import run_mac_gemini_er_simulation
from mustang_ai.simulator.mac_live_workbench import (
    run_interactive_voice_repl,
    run_voice_e2e_session,
    serve_live_workbench,
)
from mustang_ai.simulator.mock_gemini_session import MockGeminiLiveSession
from mustang_ai.simulator.virtual_arena import VirtualArena


def run_self_test(repo_root: Path | None = None) -> dict[str, object]:
    """Execute end-to-end verification across FN-1, FN-2, FN-3, Watchdog, and VirtualArena."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[4]

    config = GeminiERConfig()
    emoji_sheet_path = repo_root / "docs" / "images" / "ai_gc9a01_emoji_sheet.png"
    report_path = repo_root / "tmp" / "ai_edition_runtime_report.json"

    # 1. Verify Cable Harness Doctor (H1..H5)
    doctor_report = doctor.run_doctor(harness="all", mode="sim")

    # 2. Verify FN-1: Voice + 12 Emojis + LocalPiperTTS + Half-Duplex Mute + Barge-In
    display = SimGC9A01Display(config.pins)
    tts = SimPiperTTS(config.tts)
    audio = SimAudioStream(config.pins)
    fn1 = VoiceEmojiHUDController(audio=audio, tts=tts, display=display, pins=config.pins)

    sheet_out = display.render_emoji_contact_sheet(emoji_sheet_path)
    speak_res = fn1.speak_with_emoji(
        emoji="COOL_SHADES",
        hud_message="BORN TO RUN 67",
        spoken_text="Hello! Ready to cruise in sixty-seven style.",
    )
    # Test loud barge-in while speaking
    audio.set_mic_amplitude(24000.0)
    barge_chunk = fn1.poll_mic_with_barge_in()
    audio.set_mic_amplitude(1800.0)

    # 3. Verify FN-2 in VirtualArena: Circle left interrupted by obstacle -> Reverse -> S-curve bypass
    arena_fn2 = VirtualArena(camera_config=config.camera, car_x_mm=0.0, car_y_mm=0.0, car_heading_rad=0.0)
    bus_fn2 = StateBus()
    tof_fn2 = SimRangefinder(config.pins, distance_provider=arena_fn2.compute_tof_distance_mm)
    cam_fn2 = SimFisheyeCamera(config.camera, frame_provider=arena_fn2.render_fisheye_rgb)
    act_fn2 = SimDriveActuator(config.pins)
    gov_fn2 = WatchdogReflexGovernor(rangefinder=tof_fn2, actuators=act_fn2, bus=bus_fn2, pins=config.pins)
    engine_fn2 = LocalAutonomyEngine(
        camera=cam_fn2,
        audio=audio,
        tts=tts,
        display=display,
        bus=bus_fn2,
        pins=config.pins,
    )
    engine_fn2.handle_tool_call("execute_maneuver", {"maneuver_name": "circle_left", "speed_scale": 0.85})
    fn2_states_visited: list[str] = []
    for step_idx in range(60):
        if step_idx == 8:
            # Place obstacle directly in front of the front valance (<120 mm) to trigger reflex + evasive reverse
            arena_fn2.obstacles.clear()
            arena_fn2.add_obstacle(
                x_mm=arena_fn2.car_x_mm + 210.0 * math.cos(arena_fn2.car_heading_rad),
                y_mm=arena_fn2.car_y_mm + 210.0 * math.sin(arena_fn2.car_heading_rad),
                radius_mm=55.0,
            )
        if step_idx == 24:
            # Clear obstacle once reverse completes so S-curve bypass finishes cleanly
            arena_fn2.obstacles.clear()
        gov_fn2.step_once(now_s=time.monotonic())
        engine_fn2.step_once(dt_sec=0.05)
        cmd = gov_fn2.step_once(now_s=time.monotonic())
        arena_fn2.step_kinematics(dt_sec=0.05, cmd=cmd)
        st = engine_fn2.maneuver_seq.obstacle_state
        if not fn2_states_visited or fn2_states_visited[-1] != st:
            fn2_states_visited.append(st)

    # 4. Verify FN-3 in VirtualArena: Follow person walking ahead/right using MockGeminiLiveSession
    arena_fn3 = VirtualArena(camera_config=config.camera, car_x_mm=0.0, car_y_mm=0.0, car_heading_rad=0.0)
    arena_fn3.set_person_position(760.0, 150.0)
    bus_fn3 = StateBus()
    tof_fn3 = SimRangefinder(config.pins, distance_provider=arena_fn3.compute_tof_distance_mm)
    cam_fn3 = SimFisheyeCamera(config.camera, frame_provider=arena_fn3.render_fisheye_rgb)
    act_fn3 = SimDriveActuator(config.pins)
    gov_fn3 = WatchdogReflexGovernor(rangefinder=tof_fn3, actuators=act_fn3, bus=bus_fn3, pins=config.pins)
    engine_fn3 = LocalAutonomyEngine(
        camera=cam_fn3,
        audio=audio,
        tts=tts,
        display=display,
        bus=bus_fn3,
        pins=config.pins,
    )
    mock_session = MockGeminiLiveSession()
    mock_session.enqueue_tool_call(
        "set_follow_person_mode",
        {"enabled": True, "target_mode": "body_legs_torso", "standoff_mm": 350},
    )
    orchestrator = GeminiLiveOrchestrator(
        session=mock_session,
        camera=cam_fn3,
        autonomy=engine_fn3,
        bus=bus_fn3,
    )
    asyncio.run(orchestrator.process_incoming_events())

    fn3_steer_samples: list[float] = []
    for _ in range(25):
        gov_fn3.step_once(now_s=time.monotonic())
        intent = engine_fn3.step_once(dt_sec=0.05)
        cmd = gov_fn3.step_once(now_s=time.monotonic())
        arena_fn3.step_kinematics(dt_sec=0.05, cmd=cmd)
        fn3_steer_samples.append(intent.desired_steering_deg)

    asyncio.run(orchestrator.push_telemetry_frame_and_audio())

    all_passed = bool(
        doctor_report["status"] == "PASS"
        and len(CORE_12_EMOJIS) == 12
        and barge_chunk.barge_in_triggered
        and "EVASIVE_REVERSE" in fn2_states_visited
        and "EVASIVE_BYPASS_PASS" in fn2_states_visited
        and engine_fn3.person_follower.enabled
        and max(abs(s) for s in fn3_steer_samples) > 0.0
    )

    report = {
        "version": "3.2.0",
        "package": "mustang_ai",
        "primary_model": config.primary_model,
        "all_checks_passed": all_passed,
        "status": "PASS" if all_passed else "FAIL",
        "doctor": doctor_report,
        "fn1_voice_emoji_hud": {
            "emoji_count": len(CORE_12_EMOJIS),
            "emoji_sheet_saved": str(sheet_out.relative_to(repo_root)),
            "last_emoji": speak_res["emoji"],
            "barge_in_triggered": barge_chunk.barge_in_triggered,
            "tts_synthesis_latency_ms": speak_res["synthesis_latency_ms"],
        },
        "fn2_maneuver_obstacle": {
            "maneuvers_defined": sorted(MANEUVER_LIBRARY.keys()),
            "states_visited": fn2_states_visited,
            "reflex_brakes_triggered": gov_fn2.reflex_brake_count,
            "final_car_pose_mm": [round(arena_fn2.car_x_mm, 1), round(arena_fn2.car_y_mm, 1)],
        },
        "fn3_person_follower": {
            "enabled": engine_fn3.person_follower.enabled,
            "state": engine_fn3.person_follower.state,
            "max_steer_deg": round(max(abs(s) for s in fn3_steer_samples), 2),
            "final_car_pose_mm": [round(arena_fn3.car_x_mm, 1), round(arena_fn3.car_y_mm, 1)],
            "streamed_video_frames": len(mock_session.received_video_jpegs),
        },
        "gemini_tools_declared": [t["name"] for t in build_gemini_tool_declarations()],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "doctor":
        return doctor.main(args_list[1:])
    if args_list and args_list[0] == "simulate":
        speak_mac = "--speak-mac" in args_list[1:]
        sim_report = run_mac_gemini_er_simulation(speak_mac_audio=speak_mac)
        print(json.dumps(sim_report, indent=2))
        return 0 if sim_report["status"] == "PASS" else 1
    if args_list and args_list[0] == "voice-e2e":
        speak_mac = "--speak-mac" in args_list[1:]
        use_cloud = "--offline" not in args_list[1:]
        e2e_report = run_voice_e2e_session(audible_speaker=speak_mac, use_cloud_live=use_cloud)
        print(json.dumps(e2e_report, indent=2))
        return 0 if e2e_report["status"] == "PASS" else 1
    if args_list and args_list[0] == "live":
        sub_parser = argparse.ArgumentParser(prog="mustang-ai live")
        sub_parser.add_argument("--host", default="127.0.0.1")
        sub_parser.add_argument("--port", type=int, default=8765)
        sub_parser.add_argument("--no-browser", action="store_true")
        sub_parser.add_argument("--mute", action="store_true")
        sub_args = sub_parser.parse_args(args_list[1:])
        serve_live_workbench(
            host=sub_args.host,
            port=sub_args.port,
            open_browser=not sub_args.no_browser,
            audible_speaker=not sub_args.mute,
        )
        return 0
    if args_list and args_list[0] == "repl":
        mute = "--mute" in args_list[1:]
        return run_interactive_voice_repl(audible_speaker=not mute)

    parser = argparse.ArgumentParser(
        prog="mustang-ai",
        description="1967 Ford Mustang Fastback AI Edition (v3.2.0) Autonomous Runtime.",
    )
    parser.add_argument(
        "--mode",
        choices=["sim", "radxa"],
        default="sim",
        help="Execution backend ('sim' or 'radxa').",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic VirtualArena + H1..H5 verification suite and write runtime report.",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run the 4-Act Local Mac <-> Gemini Robotics ER 2.0 closed-loop cockpit simulator.",
    )
    parser.add_argument(
        "--speak-mac",
        action="store_true",
        help="Speak synthesized replies out loud on macOS speakers during `--simulate`.",
    )
    args = parser.parse_args(args_list)

    if args.simulate:
        sim_report = run_mac_gemini_er_simulation(speak_mac_audio=args.speak_mac)
        print(json.dumps(sim_report, indent=2))
        return 0 if sim_report["status"] == "PASS" else 1

    if args.self_test or args.mode == "sim":
        report = run_self_test()
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "PASS" else 1

    print("Radxa hardware runtime mode selected. Run `mustang-ai doctor --mode radxa` first to verify H1..H5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

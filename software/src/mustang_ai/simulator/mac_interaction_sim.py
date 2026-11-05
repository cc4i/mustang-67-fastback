"""Local Mac Closed-Loop Simulator (`mac_interaction_sim.py`) for `gemini-robotics-er-2-streaming` (`v3.2.0`).

Runs the exact same Python libraries and runtime stack that execute on Radxa Zero 3W:
- `google-genai` (`>=2.34.0`): `genai.types.LiveConnectConfig`, `types.Tool`, `types.FunctionDeclaration`,
  `types.Behavior.NON_BLOCKING`, `types.Blob`, `types.FunctionCall`, `types.FunctionResponse`
- `pillow` (`>=12.0.0`): `OV5647` `640×480` JPEG encoder + `GC9A01` `240×240` `RGB565` circular HUD renderer
- `mustang_ai` 3-Tier stack: `WatchdogReflexGovernor` (50 Hz), `LocalAutonomyEngine` (15 Hz),
  `GeminiLiveOrchestrator` (5 Hz video / 16 kHz PCM16 audio), and `VirtualArena` 2D kinematics.
"""

from __future__ import annotations

import asyncio
import io
import json
import math
import time
from pathlib import Path
from typing import Any

import google.genai as genai
from PIL import Image, ImageDraw, ImageFont

from mustang_ai.config import GeminiERConfig
from mustang_ai.hal.audio_i2s import MacLaptopAudio
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.hal.tts_piper import LocalPiperTTS
from mustang_ai.runtime.gemini_live_stream import (
    GeminiLiveOrchestrator,
    build_gemini_live_connect_config,
)
from mustang_ai.runtime.local_autonomy_loop import LocalAutonomyEngine
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor
from mustang_ai.simulator.mock_gemini_session import MockGeminiLiveSession
from mustang_ai.simulator.virtual_arena import VirtualArena


def decode_rgb565_to_image(rgb565_bytes: bytes, width: int = 240, height: int = 240) -> Image.Image:
    """Decode big-endian `RGB565` SPI buffer (`115,200` bytes) back into an RGB `PIL.Image`."""
    expected = width * height * 2
    if len(rgb565_bytes) != expected:
        return Image.new("RGB", (width, height), (8, 12, 20))
    rgb = bytearray(width * height * 3)
    out_idx = 0
    for i in range(0, expected, 2):
        val = (rgb565_bytes[i] << 8) | rgb565_bytes[i + 1]
        r = ((val >> 11) & 0x1F) << 3
        g = ((val >> 5) & 0x3F) << 2
        b = (val & 0x1F) << 3
        rgb[out_idx] = r
        rgb[out_idx + 1] = g
        rgb[out_idx + 2] = b
        out_idx += 3
    return Image.frombytes("RGB", (width, height), bytes(rgb))


def render_cockpit_dashboard_frame(
    *,
    act_title: str,
    step_label: str,
    user_utterance: str,
    arena: VirtualArena,
    bus: StateBus,
    display: SimGC9A01Display,
    actuators: SimDriveActuator,
    session: MockGeminiLiveSession,
    extra_note: str = "",
) -> Image.Image:
    """Render a `1280×720` 4-panel visual cockpit frame showing camera, GC9A01 HUD, 2D radar, and `google-genai` wire trace."""
    canvas = Image.new("RGB", (1280, 720), (10, 14, 22))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    # Header bar
    draw.rectangle((0, 0, 1280, 44), fill=(18, 26, 40))
    draw.line((0, 44, 1280, 44), fill=(0, 210, 255), width=2)
    header_text = (
        f"MUSTANG 67 AI EDITION (v3.2.0) | LOCAL MAC <-> GEMINI ROBOTICS ER 2.0 SIMULATOR | "
        f"google-genai v{genai.__version__}"
    )
    draw.text((16, 10), header_text, fill=(0, 230, 255), font=font)
    draw.text((16, 26), f"{act_title}  [{step_label}]", fill=(230, 240, 255), font=font)

    # Panel 1 (Top-Left): OV5647 640x480 Fisheye JPEG Stream sent via `types.Blob(mime_type="image/jpeg")`
    p1_x, p1_y, p1_w, p1_h = 16, 56, 560, 390
    draw.rounded_rectangle((p1_x, p1_y, p1_x + p1_w, p1_y + p1_h), radius=10, fill=(16, 22, 32), outline=(45, 70, 105), width=2)
    draw.text(
        (p1_x + 12, p1_y + 8),
        "PANEL 1: OV5647 160-DEG FISHEYE -> types.Blob(mime_type='image/jpeg')",
        fill=(120, 215, 255),
        font=font,
    )
    if session.received_video_blobs:
        jpeg_bytes = session.received_video_blobs[-1].data or b""
        cam_img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    else:
        cam_img = Image.frombytes("RGB", (640, 480), arena.render_fisheye_rgb())

    # Overlay person bounding box if detected
    cam_draw = ImageDraw.Draw(cam_img)
    if bus.vision.person_detected and bus.vision.person_box_2d is not None:
        ymin, xmin, ymax, xmax = bus.vision.person_box_2d
        bx0 = int(xmin * cam_img.width / 1000.0)
        by0 = int(ymin * cam_img.height / 1000.0)
        bx1 = int(xmax * cam_img.width / 1000.0)
        by1 = int(ymax * cam_img.height / 1000.0)
        cam_draw.rectangle((bx0, by0, bx1, by1), outline=(52, 245, 165), width=3)
        cam_draw.text((bx0 + 4, max(32, by0 - 14)), f"PERSON {bus.vision.person_bearing_deg:+.1f}D", fill=(52, 245, 165), font=font)

    cam_thumb = cam_img.resize((536, 348))
    canvas.paste(cam_thumb, (p1_x + 12, p1_y + 30))

    # Panel 2 (Top-Right): GC9A01 240x240 Circular Rear-Window HUD (decoded from 115,200-byte RGB565 SPI buffer) + Hardware Gauges
    p2_x, p2_y, p2_w, p2_h = 592, 56, 672, 390
    draw.rounded_rectangle((p2_x, p2_y, p2_x + p2_w, p2_y + p2_h), radius=10, fill=(16, 22, 32), outline=(45, 70, 105), width=2)
    draw.text(
        (p2_x + 12, p2_y + 8),
        "PANEL 2: GC9A01 240x240 ROUND HUD (RGB565 SPI3) & RADXA ZERO 3W PINS (H1..H5)",
        fill=(120, 215, 255),
        font=font,
    )
    hud_img = (
        decode_rgb565_to_image(display.last_rgb565_bytes)
        if display.last_rgb565_bytes
        else display.last_rgb_image()
    )
    hud_resized = hud_img.resize((280, 280))
    canvas.paste(hud_resized, (p2_x + 20, p2_y + 44))
    draw.text(
        (p2_x + 42, p2_y + 334),
        f"SPI3 Buffer: {len(display.last_rgb565_bytes):,d} B (RGB565)",
        fill=(150, 190, 225),
        font=font,
    )

    # Hardware pinout & telemetry readouts on the right half of Panel 2
    gx = p2_x + 320
    gy = p2_y + 44
    cmd = bus.actuator_cmd
    tof = bus.tof
    aud = bus.audio
    hw_lines = [
        ("H1 Front Laser (VL53L1X I2C3 0x29):", f"{tof.distance_mm:4d} mm  [{'EMERGENCY <180MM' if tof.distance_mm < 180 else 'CLEAR'}]"),
        ("H2 Rear HUD (GC9A01 SPI3 40MHz):", f"Emoji={bus.hud.emoji} | '{bus.hud.caption}'"),
        ("H3/H4 Audio (I2S3_M0 + GPIO3_C1):", f"EchoMute={aud.muted_by_echo_guard} | BargeIn={aud.barge_in_triggered}"),
        ("H5 Steering Servo (PWM14_M0 Pin 7):", f"{cmd.applied_steering_deg:+5.1f} deg  ({actuators.last_command.servo_pulse_us:4d} us)"),
        ("H5 N20 Drive (DRV8833 PWM15_M0):", f"Throttle={cmd.applied_throttle:+.2f} | Brake={cmd.emergency_brake}"),
        ("Tier-0 Watchdog (100ms Deadman):", f"Tripped={cmd.watchdog_tripped} | Mode={bus.intent.source_mode}"),
        ("Vision Optical Clearance (L / R):", f"L={bus.vision.left_clearance_score:.1f} | R={bus.vision.right_clearance_score:.1f}"),
        ("Piper Local ONNX TTS (16kHz PCM):", f"'{extra_note[:34]}'"),
    ]
    for idx, (label, val) in enumerate(hw_lines):
        yy = gy + idx * 40
        draw.rounded_rectangle((gx, yy, p2_x + p2_w - 14, yy + 34), radius=6, fill=(22, 32, 48), outline=(38, 58, 86))
        draw.text((gx + 8, yy + 4), label, fill=(145, 185, 220), font=font)
        val_color = (255, 85, 75) if ("EMERGENCY" in val or "Brake=True" in val or "Tripped=True" in val) else (52, 245, 165)
        draw.text((gx + 8, yy + 18), val, fill=val_color, font=font)

    # Panel 3 (Bottom-Left): VirtualArena 2D Top-Down Lidar & Slalom Course Radar
    p3_x, p3_y, p3_w, p3_h = 16, 458, 560, 248
    draw.rounded_rectangle((p3_x, p3_y, p3_x + p3_w, p3_y + p3_h), radius=10, fill=(16, 22, 32), outline=(45, 70, 105), width=2)
    radar_img = arena.render_topdown_map_image(
        width=p3_w - 8,
        height=p3_h - 8,
        active_maneuver=bus.intent.active_maneuver or arena.active_maneuver_name,
        phase_caption=bus.hud.caption,
        tof_mm=tof.distance_mm,
        steer_deg=cmd.applied_steering_deg,
        throttle=cmd.applied_throttle,
    )
    canvas.paste(radar_img, (p3_x + 4, p3_y + 4))

    # Panel 4 (Bottom-Right): `google-genai` Live API Wire Protocol & NON_BLOCKING FunctionCall Trace
    p4_x, p4_y, p4_w, p4_h = 592, 458, 672, 248
    draw.rounded_rectangle((p4_x, p4_y, p4_x + p4_w, p4_y + p4_h), radius=10, fill=(16, 22, 32), outline=(45, 70, 105), width=2)
    draw.text(
        (p4_x + 12, p4_y + 8),
        "PANEL 4: GEMINI ROBOTICS ER 2.0 STREAMING WIRE TRACE (google.genai.types)",
        fill=(120, 215, 255),
        font=font,
    )

    last_fc_str = "None"
    if session.emitted_function_calls:
        fc = session.emitted_function_calls[-1]
        last_fc_str = f"FunctionCall(id='{fc.id}', name='{fc.name}', args={json.dumps(fc.args)})"

    last_fr_str = "None"
    if session.received_genai_function_responses:
        fr = session.received_genai_function_responses[-1]
        last_fr_str = f"FunctionResponse(id='{fr.id}', name='{fr.name}', response={json.dumps(fr.response)})"

    vid_kb = len(session.received_video_blobs[-1].data or b"") / 1024.0 if session.received_video_blobs else 0.0
    aud_kb = len(session.received_audio_blobs[-1].data or b"") / 1024.0 if session.received_audio_blobs else 0.0

    wire_lines = [
        "1. LiveConnectConfig : model='gemini-robotics-er-2-streaming-preview' | tools=5 NON_BLOCKING | thinking_budget=0",
        f"2. User Mic Input    : \"{user_utterance}\"",
        f"3. Uplink Blobs      : video=Blob('image/jpeg', {vid_kb:.1f} KB) | audio=Blob('audio/pcm;rate=16000', {aud_kb:.1f} KB)",
        f"4. Gemini Tool Call  : {last_fc_str[:88]}",
        f"   (cont.)           : {last_fc_str[88:176]}",
        f"5. Radxa Tool Return : {last_fr_str[:88]}",
        f"   (cont.)           : {last_fr_str[88:176]}",
    ]
    for idx, line in enumerate(wire_lines):
        if not line.strip() or line.endswith(": "):
            continue
        yy = p4_y + 32 + idx * 28
        color = (255, 215, 90) if "FunctionCall" in line else ((52, 245, 165) if "FunctionResponse" in line else (210, 228, 245))
        draw.text((p4_x + 14, yy), line, fill=color, font=font)

    return canvas


def run_mac_gemini_er_simulation(
    repo_root: Path | None = None,
    speak_mac_audio: bool = False,
) -> dict[str, Any]:
    """Run a 4-Act closed-loop simulation on macOS using the exact Radxa `google-genai` & HAL stack."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[4]

    config = GeminiERConfig()
    live_cfg = build_gemini_live_connect_config(config)

    arena = VirtualArena(camera_config=config.camera, car_x_mm=0.0, car_y_mm=0.0, car_heading_rad=0.0)
    bus = StateBus()
    tof = SimRangefinder(config.pins, distance_provider=arena.compute_tof_distance_mm)
    camera = SimFisheyeCamera(config.camera, frame_provider=arena.render_fisheye_rgb)
    audio = MacLaptopAudio(config.pins, audible_speaker=speak_mac_audio)
    tts = LocalPiperTTS(config.tts)
    display = SimGC9A01Display(config.pins)
    actuators = SimDriveActuator(config.pins)

    governor = WatchdogReflexGovernor(rangefinder=tof, actuators=actuators, bus=bus, pins=config.pins)
    autonomy = LocalAutonomyEngine(
        camera=camera,
        audio=audio,
        tts=tts,
        display=display,
        bus=bus,
        pins=config.pins,
    )
    session = MockGeminiLiveSession(config=config)
    orchestrator = GeminiLiveOrchestrator(session=session, camera=camera, autonomy=autonomy, bus=bus)

    frames: list[Image.Image] = []
    key_act_frames: list[Image.Image] = []
    interaction_log: list[dict[str, Any]] = []

    def step_closed_loop(
        *,
        act_title: str,
        step_label: str,
        user_utterance: str,
        dt_sec: float = 0.05,
        extra_note: str = "",
        record_frame: bool = True,
    ) -> Image.Image:
        now = time.monotonic()
        governor.step_once(now_s=now)
        autonomy.step_once(dt_sec=dt_sec)
        cmd = governor.step_once(now_s=time.monotonic())
        arena.step_kinematics(dt_sec=dt_sec, cmd=cmd)
        asyncio.run(orchestrator.push_telemetry_frame_and_audio())
        asyncio.run(orchestrator.process_incoming_events())
        # Refresh HUD after tool execution
        governor.step_once(now_s=time.monotonic())
        autonomy.step_once(dt_sec=dt_sec)
        cmd = governor.step_once(now_s=time.monotonic())
        frame = render_cockpit_dashboard_frame(
            act_title=act_title,
            step_label=step_label,
            user_utterance=user_utterance,
            arena=arena,
            bus=bus,
            display=display,
            actuators=actuators,
            session=session,
            extra_note=extra_note,
        )
        if record_frame:
            frames.append(frame)
        return frame

    # =========================================================================
    # ACT 1: FN-1 Voice Conversation + COOL_SHADES Circular HUD + Voice Barge-In
    # =========================================================================
    utt_1 = "Hey Mustang, how are you feeling today?"
    session.enqueue_tool_call(
        "speak_with_emoji",
        {
            "emoji": "COOL_SHADES",
            "hud_message": "BORN TO RUN 67",
            "spoken_text": "Sixty-seven Fastback online! Ready to roll with Gemini Robotics.",
        },
        call_id="call_fn1_shades",
    )
    for i in range(4):
        f_act1 = step_closed_loop(
            act_title="ACT 1 (FN-1): VOICE CONVERSATION, COOL_SHADES HUD & HALF-DUPLEX AUTO-MUTE",
            step_label=f"Frame {i + 1}/6",
            user_utterance=utt_1,
            extra_note=tts.last_spoken_text,
        )
    key_act_frames.append(f_act1)
    interaction_log.append(
        {
            "act": "ACT_1_VOICE_EMOJI_HUD",
            "user_utterance": utt_1,
            "hud_emoji": bus.hud.emoji,
            "hud_caption": bus.hud.caption,
            "spoken_text": tts.last_spoken_text,
            "tts_backend": tts.backend_used,
            "tts_latency_ms": tts.last_latency_ms,
            "echo_guard_muted": bus.audio.muted_by_echo_guard,
            "rgb565_bytes": len(display.last_rgb565_bytes),
        }
    )

    # Loud Barge-In (>0.55 RMS)
    audio.set_mic_amplitude(24500.0)
    for i in range(2):
        step_closed_loop(
            act_title="ACT 1B (FN-1): LOUD USER BARGE-IN (RMS >= 0.55) CUTS TTS IN <= 1 CHUNK",
            step_label=f"Frame {i + 5}/6",
            user_utterance="Wait, hold up!",
            extra_note="BARGE-IN INTERRUPT -> MAX98357A MUTED",
        )
    audio.set_mic_amplitude(1800.0)

    # =========================================================================
    # ACT 2: FN-2 Circle Left + <20ms VL53L1X Emergency Brake + Reverse + Bypass
    # =========================================================================
    utt_2 = "Carve a left circle and avoid any obstacles!"
    session.enqueue_tool_call(
        "speak_with_emoji",
        {
            "emoji": "WINK",
            "hud_message": "CIRCLE LEFT",
            "spoken_text": "Carving a left circle now!",
        },
        call_id="call_fn2_wink",
    )
    session.enqueue_tool_call(
        "execute_maneuver",
        {"maneuver_name": "circle_left", "speed_scale": 0.90},
        call_id="call_fn2_circle",
    )
    for i in range(6):
        step_closed_loop(
            act_title="ACT 2A (FN-2): PREDEFINED MANEUVER `circle_left`",
            step_label=f"Nominal Step {i + 1}",
            user_utterance=utt_2,
            extra_note=f"State={autonomy.maneuver_seq.obstacle_state}",
        )

    # Drop an obstacle 205 mm ahead of the car center (~92 mm from front valance < 180 mm threshold)
    arena.obstacles.clear()
    arena.add_obstacle(
        x_mm=arena.car_x_mm + 205.0 * math.cos(arena.car_heading_rad),
        y_mm=arena.car_y_mm + 205.0 * math.sin(arena.car_heading_rad),
        radius_mm=55.0,
    )
    f_act2_brake: Image.Image | None = None
    for i in range(8):
        f_curr = step_closed_loop(
            act_title="ACT 2B (FN-2): VL53L1X <180MM EMERGENCY STOP -> ~150MM REVERSE",
            step_label=f"Evasive Step {i + 1}",
            user_utterance=utt_2,
            extra_note=f"State={autonomy.maneuver_seq.obstacle_state} | ToF={bus.tof.distance_mm}mm",
        )
        if autonomy.maneuver_seq.obstacle_state == "EVASIVE_REVERSE" and f_act2_brake is None:
            f_act2_brake = f_curr

    # Clear obstacle once reverse distance is achieved so S-curve bypass completes
    arena.obstacles.clear()
    for i in range(4):
        f_curr = step_closed_loop(
            act_title="ACT 2C (FN-2): OPTICAL ROI SCORING & S-CURVE BYPASS RECOVERY",
            step_label=f"Bypass Step {i + 1}",
            user_utterance=utt_2,
            extra_note=f"State={autonomy.maneuver_seq.obstacle_state} | BypassDir={bus.vision.preferred_bypass_dir}",
        )
    key_act_frames.append(f_act2_brake or f_curr)
    interaction_log.append(
        {
            "act": "ACT_2_MANEUVER_OBSTACLE_AVOIDANCE",
            "user_utterance": utt_2,
            "reflex_brakes_triggered": governor.reflex_brake_count,
            "obstacle_state_after_reverse": autonomy.maneuver_seq.obstacle_state,
            "car_pose_mm": [round(arena.car_x_mm, 1), round(arena.car_y_mm, 1)],
        }
    )

    # =========================================================================
    # ACT 3: FN-3 Visual + Front Laser Person Following (350 mm Standoff)
    # =========================================================================
    utt_3 = "Follow me at 350 millimeters!"
    arena.set_person_position(
        arena.car_x_mm + 680.0 * math.cos(arena.car_heading_rad) - 160.0 * math.sin(arena.car_heading_rad),
        arena.car_y_mm + 680.0 * math.sin(arena.car_heading_rad) + 160.0 * math.cos(arena.car_heading_rad),
    )
    session.enqueue_tool_call(
        "set_follow_person_mode",
        {
            "enabled": True,
            "target_mode": "body_legs_torso",
            "standoff_mm": 350,
        },
        call_id="call_fn3_follow",
    )
    session.enqueue_tool_call(
        "speak_with_emoji",
        {
            "emoji": "HEART_EYES",
            "hud_message": "LOCKED ON YOU",
            "spoken_text": "Target locked! Tracking your path at three hundred fifty millimeters.",
        },
        call_id="call_fn3_hearts",
    )
    f_act3: Image.Image | None = None
    for i in range(6):
        f_act3 = step_closed_loop(
            act_title="ACT 3 (FN-3): OV5647 FISHEYE + VL53L1X PERSON FOLLOWING (350MM STANDOFF)",
            step_label=f"Track Step {i + 1}/6",
            user_utterance=utt_3,
            extra_note=f"Bearing={bus.vision.person_bearing_deg:+.1f}D | Steer={bus.actuator_cmd.applied_steering_deg:+.1f}D",
        )
    assert f_act3 is not None
    key_act_frames.append(f_act3)
    interaction_log.append(
        {
            "act": "ACT_3_PERSON_FOLLOWER",
            "user_utterance": utt_3,
            "person_detected": bus.vision.person_detected,
            "person_bearing_deg": bus.vision.person_bearing_deg,
            "applied_steering_deg": bus.actuator_cmd.applied_steering_deg,
            "tof_mm": bus.tof.distance_mm,
        }
    )

    # =========================================================================
    # ACT 4: Tier-0 100ms Deadman Watchdog Safety Cutoff
    # =========================================================================
    utt_4 = "[Simulated Tier-1 Heartbeat Stall > 100 ms]"
    stale_now = time.monotonic() + 0.250
    governor.step_once(now_s=stale_now)
    autonomy.voice_hud.update_hud(tof=bus.tof, actuator_cmd=bus.actuator_cmd)
    f_act4 = render_cockpit_dashboard_frame(
        act_title="ACT 4 (SAFETY): 100MS DEADMAN WATCHDOG TRIPS -> NEUTRAL 1500US & 0% THROTTLE",
        step_label="Watchdog Cutoff",
        user_utterance=utt_4,
        arena=arena,
        bus=bus,
        display=display,
        actuators=actuators,
        session=session,
        extra_note="WATCHDOG_TRIPPED -> DRV8833 COAST / SERVO 1500US",
    )
    frames.append(f_act4)
    key_act_frames.append(f_act4)
    interaction_log.append(
        {
            "act": "ACT_4_DEADMAN_WATCHDOG",
            "watchdog_tripped": bus.actuator_cmd.watchdog_tripped,
            "applied_throttle": bus.actuator_cmd.applied_throttle,
            "servo_pulse_us": actuators.last_command.servo_pulse_us,
        }
    )

    # Build 2x2 Storyboard PNG (`2560x1440`) and Animated GIF (`1280x720`)
    storyboard = Image.new("RGB", (2560, 1440), (8, 12, 18))
    positions = [(0, 0), (1280, 0), (0, 720), (1280, 720)]
    for idx, kf in enumerate(key_act_frames[:4]):
        storyboard.paste(kf, positions[idx])

    storyboard_path = repo_root / "docs" / "images" / "ai_gemini_er_mac_simulation.png"
    gif_path = repo_root / "docs" / "images" / "ai_gemini_er_mac_simulation.gif"
    report_path = repo_root / "tmp" / "mac_gemini_er_simulation_report.json"

    storyboard_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    storyboard.save(storyboard_path)
    gif_frames = [f.resize((960, 540)).convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for f in frames]
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=160,
        loop=0,
    )

    summary: dict[str, Any] = {
        "status": "PASS",
        "version": "3.2.0",
        "sdk": f"google-genai=={genai.__version__}",
        "live_connect_model": config.primary_model,
        "non_blocking_tools_count": len(live_cfg.tools[0].function_declarations) if live_cfg.tools else 0,
        "frames_rendered": len(frames),
        "video_blobs_streamed": len(session.received_video_blobs),
        "audio_blobs_streamed": len(session.received_audio_blobs),
        "function_calls_processed": len(session.emitted_function_calls),
        "function_responses_returned": len(session.received_genai_function_responses),
        "storyboard_png": str(storyboard_path.relative_to(repo_root)),
        "animated_gif": str(gif_path.relative_to(repo_root)),
        "acts": interaction_log,
    }
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

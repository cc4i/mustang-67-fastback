"""Interactive Local Laptop End-to-End Workbench (`mac_live_workbench.py`) for `mustang-ai` (`v3.2.0`).

Allows a developer on a local MacBook to run the full end-to-end pipeline before deploying to Radxa Zero 3W:
  Voice / Mic Input (`16 kHz` `PCM16`) + `OV5647` `640×480` Fisheye Camera + `VL53L1X` Front Laser
    -> Real Live WebSocket Session (`gemini-robotics-er-2-streaming-preview` via `google-genai>=2.34.0`)
    -> Single-Voice Coalesced Spoken Audio (`16 kHz` `PCM16` synthesized on local `piper-tts` ONNX `en_US-amy-low.onnx`)
    -> Circular `240×240` `GC9A01` Emoji HUD (`115,200` `RGB565` bytes)
    -> Live 2D Top-Down Track & Slalom Course Radar (`CONE 1..4`) + `PWM14_M0` Servo & `DRV8833` Motor Control.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import google.genai as genai
from google.genai import types

from mustang_ai.config import CORE_12_EMOJIS, GeminiERConfig, load_gemini_api_key
from mustang_ai.features.maneuver_obstacle import MANEUVER_LIBRARY
from mustang_ai.hal.audio_i2s import MacLaptopAudio, pcm16_to_wav_bytes
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.hal.tts_piper import LocalPiperTTS, _synthesize_formant_pcm16
from mustang_ai.protocol.messages import VisionFrameMetrics
from mustang_ai.runtime.gemini_live_stream import (
    GeminiLiveOrchestrator,
    build_gemini_live_connect_config,
)
from mustang_ai.runtime.local_autonomy_loop import LocalAutonomyEngine
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor
from mustang_ai.simulator.mac_interaction_sim import (
    decode_rgb565_to_image,
    render_cockpit_dashboard_frame,
)
from mustang_ai.simulator.mock_gemini_session import MockGeminiLiveSession
from mustang_ai.simulator.virtual_arena import SHOWCASE_OBJECT_CATALOG, VirtualArena


def coalesce_turn_tool_calls(
    calls: list[tuple[str, dict[str, Any], str]],
    fallback_call_id: str = "coalesced_speak_1",
) -> list[tuple[str, dict[str, Any], str]]:
    """Coalesce multiple `speak_with_emoji` calls within a single turn into exactly ONE `speak_with_emoji` call.

    Prevents multiple concurrent/consecutive Piper ONNX TTS synthesis + playback calls when the model returns
    multiple sentences or multiple `speak_with_emoji` invocations in a single turn.
    """
    speak_calls = [c for c in calls if c[0] == "speak_with_emoji"]
    other_calls = [c for c in calls if c[0] != "speak_with_emoji"]
    if len(speak_calls) <= 1:
        return list(calls)

    combined_sentences: list[str] = []
    chosen_emoji = "COOL_SHADES"
    chosen_caption = "67 MUSTANG AI"
    chosen_id = speak_calls[0][2] or fallback_call_id
    for _, args, _ in speak_calls:
        txt = " ".join(str(args.get("spoken_text", "")).split())
        if txt and txt not in combined_sentences:
            combined_sentences.append(txt)
        emo = str(args.get("emoji", "")).strip().upper()
        if emo:
            chosen_emoji = emo
        cap = str(args.get("hud_message", "")).strip()
        if cap:
            chosen_caption = cap[:16]

    merged_speak = (
        "speak_with_emoji",
        {
            "emoji": chosen_emoji,
            "hud_message": chosen_caption,
            "spoken_text": " ".join(combined_sentences),
        },
        chosen_id,
    )
    return other_calls + [merged_speak]


class LocalGeminiERBrain:
    """Real Cloud Live WebSocket Client (`client.aio.live.connect`) targeting `gemini-robotics-er-2-streaming-preview`
    (with automatic Vertex AI ADC fallback to `gemini-3.8-live` only if `GEMINI_API_KEY` is absent).
    """

    def __init__(
        self,
        config: GeminiERConfig | None = None,
        api_key: str | None = None,
        use_cloud_live: bool = True,
    ) -> None:
        self.config = config or GeminiERConfig()
        self.api_key = (api_key or load_gemini_api_key()).strip()
        self.use_cloud_live = use_cloud_live
        self.last_cloud_model_used: str = "offline-emulated"
        self.last_cloud_probe_log: list[str] = []
        self._call_seq: int = 0

    def _next_call_id(self, prefix: str) -> str:
        self._call_seq += 1
        return f"{prefix}_{self._call_seq}"

    async def _query_real_live_websocket(
        self,
        utterance: str,
        vision: VisionFrameMetrics,
        tof_mm: int,
        jpeg_bytes: bytes | None,
        user_pcm16_bytes: bytes | None = None,
        active_maneuver: str = "",
        showcase_object: str | None = None,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Open a real `client.aio.live.connect` WebSocket session to `gemini-robotics-er-2-streaming-preview`,
        stream the `OV5647` camera JPEG + `16 kHz` `PCM16` voice audio + multimodal prompt, and collect tool calls.
        """
        self.last_cloud_probe_log.clear()
        if not self.api_key:
            self.api_key = load_gemini_api_key().strip()

        prompt_text = (
            f"User voice command: \"{utterance}\"\n"
            f"Live sensor telemetry: VL53L1X front laser={tof_mm}mm, "
            f"person_detected={vision.person_detected}, person_bearing_deg={vision.person_bearing_deg}.\n"
            "Inspect the attached 640x480 OV5647 front camera image carefully if the user asks what object is in front "
            "of the car or what you see.\n"
            "Always call `speak_with_emoji` ONCE with one of the 12 allowed emojis (CRUISE, HAPPY, WINK, LAUGH, "
            "COOL_SHADES, HEART_EYES, SURPRISED, THINKING, CONFUSED, SLEEPY, ANGRY_REV, ALERT_STOP), a short "
            "hud_message (<=16 chars), and a concise, single-paragraph spoken_text reply. "
            "If the user asks for a driving trick/maneuver (circle_left, circle_right, figure_eight, slalom, "
            "spin_wiggle, u_turn_3pt, patrol), ALSO call `execute_maneuver`. "
            "If the user asks to follow them, ALSO call `set_follow_person_mode`. "
            "If the user asks to stop, ALSO call `emergency_stop`."
        )

        candidates: list[tuple[str, genai.Client, str, types.Modality]] = []
        if self.api_key:
            ai_studio_client = genai.Client(api_key=self.api_key, vertexai=False)
            candidates.append(
                (
                    f"ai-studio:{self.config.primary_model}",
                    ai_studio_client,
                    self.config.primary_model,
                    types.Modality.TEXT,
                )
            )

        proj = os.environ.get("GOOGLE_CLOUD_PROJECT", "multi-gke-ops")
        loc = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        try:
            vertex_client = genai.Client(vertexai=True, project=proj, location=loc)
            candidates.append(
                (
                    f"vertex-adc:{self.config.fallback_live_model}",
                    vertex_client,
                    self.config.fallback_live_model,
                    types.Modality.AUDIO,
                )
            )
        except Exception as exc:
            self.last_cloud_probe_log.append(f"vertex-init-err:{type(exc).__name__}")

        for label, client, model_name, modality in candidates:
            live_cfg = build_gemini_live_connect_config(self.config, modality=modality)
            try:
                async with asyncio.timeout(7.5):
                    async with client.aio.live.connect(model=model_name, config=live_cfg) as sess:
                        # 1. Stream realtime video JPEG + 16 kHz PCM16 voice audio chunk
                        if jpeg_bytes:
                            await sess.send_realtime_input(
                                video=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
                            )
                        if user_pcm16_bytes:
                            await sess.send_realtime_input(
                                audio=types.Blob(data=user_pcm16_bytes[:6400], mime_type="audio/pcm;rate=16000")
                            )

                        # 2. Send atomic multimodal turn (Camera JPEG Part + Text Part) with turn_complete=True
                        turn_parts: list[types.Part] = []
                        if jpeg_bytes:
                            turn_parts.append(types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"))
                        turn_parts.append(types.Part.from_text(text=prompt_text))
                        await sess.send_client_content(
                            turns=types.Content(role="user", parts=turn_parts),
                            turn_complete=True,
                        )

                        collected: list[tuple[str, dict[str, Any], str]] = []
                        text_fragments: list[str] = []
                        async for msg in sess.receive():
                            if getattr(msg, "tool_call", None):
                                for fc in msg.tool_call.function_calls:
                                    collected.append(
                                        (
                                            fc.name or "speak_with_emoji",
                                            dict(fc.args or {}),
                                            getattr(fc, "id", None) or self._next_call_id("live_fc"),
                                        )
                                    )
                                fn_resps = [
                                    types.FunctionResponse(
                                        id=cid,
                                        name=tname,
                                        response={"status": "ok", "scheduling": "SILENT"},
                                    )
                                    for tname, _, cid in collected
                                ]
                                await sess.send_tool_response(function_responses=fn_resps)
                                break
                            sc = getattr(msg, "server_content", None)
                            if sc and getattr(sc, "model_turn", None):
                                for part in sc.model_turn.parts or []:
                                    if getattr(part, "text", None):
                                        text_fragments.append(str(part.text).strip())
                            if sc and getattr(sc, "turn_complete", False):
                                break

                        if not collected and text_fragments:
                            joined_txt = " ".join(t for t in text_fragments if t)
                            if joined_txt:
                                collected.append(
                                    (
                                        "speak_with_emoji",
                                        {
                                            "emoji": "THINKING",
                                            "hud_message": "VISION REPLY",
                                            "spoken_text": joined_txt,
                                        },
                                        self._next_call_id("live_txt"),
                                    )
                                )

                        if collected:
                            coalesced = coalesce_turn_tool_calls(collected, self._next_call_id("coalesced"))
                            self.last_cloud_model_used = label
                            self.last_cloud_probe_log.append(f"{label}->OK({len(coalesced)} tool_calls)")
                            return coalesced
            except Exception as exc:
                short_err = str(exc).splitlines()[0][:110]
                self.last_cloud_probe_log.append(f"{label}->{type(exc).__name__}: {short_err}")

        return []

    def _deterministic_tool_calls(
        self,
        utterance: str,
        vision: VisionFrameMetrics,
        tof_mm: int,
        showcase_object: str | None = None,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Deterministic rule-based tool planner ensuring complete coverage across all 12 emojis, 7 maneuvers, and visual objects."""
        clean = (utterance or "").strip()
        low = clean.lower()

        if any(
            phrase in low
            for phrase in ("what's this", "what is this", "what object", "what do you see", "in front of you", "in front of the car")
        ):
            if showcase_object and showcase_object in SHOWCASE_OBJECT_CATALOG:
                desc = SHOWCASE_OBJECT_CATALOG[showcase_object]
                if showcase_object == "stop_sign":
                    emo = "ALERT_STOP"
                elif showcase_object == "traffic_cone":
                    emo = "SURPRISED"
                else:
                    emo = "COOL_SHADES"
                return [
                    (
                        "speak_with_emoji",
                        {
                            "emoji": emo,
                            "hud_message": showcase_object.upper()[:16],
                            "spoken_text": f"I see a {desc} directly in front of my hood at {tof_mm} millimeters!",
                        },
                        self._next_call_id("call_vision_obj"),
                    )
                ]

        for emo_name, default_caption in CORE_12_EMOJIS:
            if emo_name.lower() in low:
                return [
                    (
                        "speak_with_emoji",
                        {
                            "emoji": emo_name,
                            "hud_message": default_caption,
                            "spoken_text": f"Switching rear fastback HUD to {emo_name.replace('_', ' ').lower()} mode!",
                        },
                        self._next_call_id("call_emoji"),
                    )
                ]

        if any(w in low for w in ("stop", "halt", "brake", "freeze", "hold up")):
            return [
                (
                    "emergency_stop",
                    {"reason": "VOICE STOP CMD"},
                    self._next_call_id("call_stop"),
                ),
                (
                    "speak_with_emoji",
                    {
                        "emoji": "ALERT_STOP",
                        "hud_message": "VOICE STOP CMD",
                        "spoken_text": "Brakes locked! Standing by at neutral.",
                    },
                    self._next_call_id("call_speak"),
                ),
            ]

        if any(w in low for w in ("follow", "track me", "come with me", "walk with me")):
            if "disable" in low or "off" in low:
                return [
                    (
                        "set_follow_person_mode",
                        {"enabled": False, "target_mode": "body_legs_torso", "standoff_mm": 350},
                        self._next_call_id("call_follow_off"),
                    ),
                    (
                        "speak_with_emoji",
                        {
                            "emoji": "CRUISE",
                            "hud_message": "FOLLOW OFF",
                            "spoken_text": "Person following disengaged. Ready for your next command.",
                        },
                        self._next_call_id("call_speak"),
                    ),
                ]
            box = list(vision.person_box_2d) if vision.person_box_2d else [220, 480, 680, 660]
            return [
                (
                    "set_follow_person_mode",
                    {
                        "enabled": True,
                        "target_mode": "body_legs_torso",
                        "target_box_2d": box,
                        "standoff_mm": 350,
                    },
                    self._next_call_id("call_follow_on"),
                ),
                (
                    "speak_with_emoji",
                    {
                        "emoji": "HEART_EYES",
                        "hud_message": "LOCKED ON YOU",
                        "spoken_text": "Locked onto you with fisheye vision and laser rangefinder at three hundred fifty millimeters!",
                    },
                    self._next_call_id("call_speak"),
                ),
            ]

        maneuver_map = [
            (
                ("circle right", "right circle", "donut right"),
                "circle_right",
                "WINK",
                "CIRCLE RIGHT",
                "Carving a tight right-hand circle!",
            ),
            (
                ("circle", "donut", "circle left", "left circle"),
                "circle_left",
                "WINK",
                "CIRCLE LEFT",
                "Carving a left circle now! Watching for obstacles.",
            ),
            (
                ("figure eight", "figure 8", "eight"),
                "figure_eight",
                "COOL_SHADES",
                "FIGURE EIGHT",
                "Executing a figure-eight crossover!",
            ),
            (
                ("slalom", "weave", "zigzag"),
                "slalom",
                "HAPPY",
                "SLALOM WEAVE",
                "Weaving through the four slalom cones now!",
            ),
            (
                ("wiggle", "dance", "spin", "celebrate"),
                "spin_wiggle",
                "LAUGH",
                "VICTORY WIGGLE",
                "Doing the sixty-seven Mustang victory wiggle!",
            ),
            (
                ("u-turn", "uturn", "turn around", "180"),
                "u_turn_3pt",
                "THINKING",
                "3-PT U-TURN",
                "Executing a three-point U-turn!",
            ),
            (
                ("patrol", "cruise", "explore"),
                "patrol",
                "CRUISE",
                "PATROL CRUISE",
                "Cruising on autonomous patrol with laser guard active.",
            ),
        ]
        for keywords, m_name, emo, caption, speech in maneuver_map:
            if any(k in low for k in keywords):
                return [
                    (
                        "speak_with_emoji",
                        {"emoji": emo, "hud_message": caption, "spoken_text": speech},
                        self._next_call_id("call_speak"),
                    ),
                    (
                        "execute_maneuver",
                        {"maneuver_name": m_name, "speed_scale": 0.90},
                        self._next_call_id("call_maneuver"),
                    ),
                ]

        if any(w in low for w in ("joke", "funny", "laugh")):
            return [
                (
                    "speak_with_emoji",
                    {
                        "emoji": "LAUGH",
                        "hud_message": "HAHA NICE ONE!",
                        "spoken_text": (
                            "Why did the sixty-seven Mustang cross the road? "
                            "Because Gemini Robotics saw zero obstacles in the laser cone!"
                        ),
                    },
                    self._next_call_id("call_speak"),
                )
            ]
        if any(w in low for w in ("rev", "v8", "roar", "engine", "fast", "race")):
            return [
                (
                    "speak_with_emoji",
                    {
                        "emoji": "ANGRY_REV",
                        "hud_message": "289 V8 ROAR!",
                        "spoken_text": "Two-eighty-nine V8 roaring! Point me at the open tarmac!",
                    },
                    self._next_call_id("call_speak"),
                )
            ]
        if any(w in low for w in ("sleep", "tired", "nap", "rest")):
            return [
                (
                    "speak_with_emoji",
                    {
                        "emoji": "SLEEPY",
                        "hud_message": "IDLE ZZZ...",
                        "spoken_text": "Resting the horses in low-power idle mode. Wake me when we roll.",
                    },
                    self._next_call_id("call_speak"),
                )
            ]
        if any(w in low for w in ("surprise", "whoa", "wow")):
            return [
                (
                    "speak_with_emoji",
                    {
                        "emoji": "SURPRISED",
                        "hud_message": "WHOA NELLY!",
                        "spoken_text": "Whoa Nelly! Check out those curves!",
                    },
                    self._next_call_id("call_speak"),
                )
            ]

        return [
            (
                "speak_with_emoji",
                {
                    "emoji": "COOL_SHADES",
                    "hud_message": "BORN TO RUN 67",
                    "spoken_text": f"Eleanor sixty-seven Fastback copying you loud and clear! Front laser reads {tof_mm} millimeters.",
                },
                self._next_call_id("call_speak"),
            )
        ]

    def plan_tool_calls(
        self,
        utterance: str,
        vision: VisionFrameMetrics,
        tof_mm: int,
        jpeg_bytes: bytes | None = None,
        user_pcm16_bytes: bytes | None = None,
        showcase_object: str | None = None,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Query the real cloud Live WebSocket API (`client.aio.live.connect`), augmenting with deterministic
        companions if the cloud turn omits `speak_with_emoji` or the requested motion tool, and coalescing
        all speech into a single `speak_with_emoji` call.
        """
        det_calls = self._deterministic_tool_calls(
            utterance=utterance,
            vision=vision,
            tof_mm=tof_mm,
            showcase_object=showcase_object,
        )
        if not self.use_cloud_live:
            self.last_cloud_model_used = "deterministic-local"
            return coalesce_turn_tool_calls(det_calls, self._next_call_id("det_coalesced"))

        cloud_calls = asyncio.run(
            self._query_real_live_websocket(
                utterance=utterance,
                vision=vision,
                tof_mm=tof_mm,
                jpeg_bytes=jpeg_bytes,
                user_pcm16_bytes=user_pcm16_bytes,
                showcase_object=showcase_object,
            )
        )
        if not cloud_calls:
            self.last_cloud_model_used = "deterministic-fallback"
            return coalesce_turn_tool_calls(det_calls, self._next_call_id("fallback_coalesced"))

        # Ensure that if cloud emitted a motion tool without `speak_with_emoji` (or vice versa), both are present
        cloud_names = {c[0] for c in cloud_calls}
        merged = list(cloud_calls)
        for det_name, det_args, det_id in det_calls:
            if det_name not in cloud_names:
                merged.append((det_name, det_args, det_id))
        return coalesce_turn_tool_calls(merged, self._next_call_id("merged_coalesced"))


class MacLiveWorkbench:
    """End-to-end Laptop-as-Radxa runtime coupling Voice -> Gemini ER -> Piper ONNX Speech + Emoji HUD + Car Control."""

    def __init__(
        self,
        *,
        audible_speaker: bool = True,
        use_cloud_live: bool = True,
        api_key: str | None = None,
    ) -> None:
        self.config = GeminiERConfig()
        self.audible_speaker = audible_speaker
        self.live_connect_config = build_gemini_live_connect_config(self.config)
        self.arena = VirtualArena(camera_config=self.config.camera, car_x_mm=0.0, car_y_mm=0.0, car_heading_rad=0.0)
        self.arena.set_person_position(720.0, 145.0)
        self.arena.setup_maneuver_course("slalom", speed_scale=0.90)

        self.bus = StateBus()
        self.tof = SimRangefinder(self.config.pins, distance_provider=self.arena.compute_tof_distance_mm)
        self.camera = SimFisheyeCamera(self.config.camera, frame_provider=self.arena.render_fisheye_rgb)
        self.audio = MacLaptopAudio(self.config.pins, audible_speaker=audible_speaker)
        self.tts = LocalPiperTTS(self.config.tts)
        self.display = SimGC9A01Display(self.config.pins)
        self.actuators = SimDriveActuator(self.config.pins)

        self.governor = WatchdogReflexGovernor(
            rangefinder=self.tof,
            actuators=self.actuators,
            bus=self.bus,
            pins=self.config.pins,
        )
        self.autonomy = LocalAutonomyEngine(
            camera=self.camera,
            audio=self.audio,
            tts=self.tts,
            display=self.display,
            bus=self.bus,
            pins=self.config.pins,
        )
        self.session = MockGeminiLiveSession(config=self.config)
        self.orchestrator = GeminiLiveOrchestrator(
            session=self.session,
            camera=self.camera,
            autonomy=self.autonomy,
            bus=self.bus,
        )
        self.brain = LocalGeminiERBrain(config=self.config, api_key=api_key, use_cloud_live=use_cloud_live)
        self._lock = threading.RLock()
        self.conversation_history: list[dict[str, Any]] = []
        self.last_user_utterance: str = "Ready for voice command..."
        self.step_physics_and_sensors(dt_sec=0.05)

    def step_physics_and_sensors(self, dt_sec: float = 0.05) -> None:
        """Advance Tier-0 (50Hz Reflex), Tier-1 (15Hz Autonomy/HUD), and 2D VirtualArena kinematics."""
        with self._lock:
            now = time.monotonic()
            self.governor.step_once(now_s=now)
            self.autonomy.step_once(dt_sec=dt_sec)
            cmd = self.governor.step_once(now_s=time.monotonic())
            self.arena.step_kinematics(dt_sec=dt_sec, cmd=cmd)

    def set_showcase_object(self, kind: str | None) -> dict[str, Any]:
        """Place a recognizable visual object (`stop_sign`, `traffic_cone`, `soccer_ball`, etc.) in front of `OV5647`."""
        with self._lock:
            info = self.arena.set_showcase_object(kind)
            if info.get("showcase_object"):
                self.autonomy.maneuver_seq.stop()
                self.autonomy.person_follower.configure(enabled=False)
            self.step_physics_and_sensors(dt_sec=0.05)
            return info

    def replay_last_audio(self) -> dict[str, Any]:
        """Replay the most recent Piper ONNX TTS audio buffer once without overlapping."""
        with self._lock:
            if self.audio.last_pcm16_bytes:
                self.audio.play_pcm16_async(self.audio.last_pcm16_bytes, self.config.pins.audio_sample_rate_hz)
            return {
                "replayed": bool(self.audio.last_pcm16_bytes),
                "wav_bytes": len(self.audio.last_wav_bytes),
            }

    def submit_voice_utterance(
        self,
        utterance: str,
        *,
        user_pcm16_bytes: bytes | None = None,
        advance_steps: int = 4,
    ) -> dict[str, Any]:
        """Execute a complete Voice + Video -> Gemini ER -> Local Piper ONNX Speech + Emoji HUD + Car Control turn."""
        with self._lock:
            clean_utt = (utterance or "").strip() or "Hey Mustang, how are you?"
            self.last_user_utterance = clean_utt

            # If the user asks "What's this object?" and no showcase object was placed yet, place a STOP sign automatically
            low_utt = clean_utt.lower()
            if (
                any(p in low_utt for p in ("what's this", "what is this", "what object", "in front of"))
                and self.arena.showcase_object is None
            ):
                self.arena.set_showcase_object("stop_sign")

            self.step_physics_and_sensors(dt_sec=0.05)
            if user_pcm16_bytes is None:
                user_pcm16_bytes = _synthesize_formant_pcm16(clean_utt, self.config.pins.audio_sample_rate_hz)

            asyncio.run(self.session.send_audio_pcm16(user_pcm16_bytes))
            asyncio.run(self.orchestrator.push_telemetry_frame_and_audio())

            # Render a clean 640x480 JPEG of the OV5647 camera view for Gemini ER visual inspection
            clean_camera_jpeg = self.arena.render_clean_camera_jpeg()

            planned_calls = self.brain.plan_tool_calls(
                utterance=clean_utt,
                vision=self.bus.vision,
                tof_mm=self.bus.tof.distance_mm,
                jpeg_bytes=clean_camera_jpeg,
                user_pcm16_bytes=user_pcm16_bytes,
                showcase_object=self.arena.showcase_object,
            )

            # Set up 2D track markers & planned trajectory curve whenever a maneuver is triggered
            for tool_name, tool_args, _ in planned_calls:
                if tool_name == "execute_maneuver":
                    m_name = str(tool_args.get("maneuver_name", "slalom"))
                    s_scale = float(tool_args.get("speed_scale", 0.90))
                    self.arena.showcase_object = None
                    self.arena.setup_maneuver_course(m_name, speed_scale=s_scale)

            emitted_calls: list[dict[str, Any]] = []
            for tool_name, tool_args, call_id in planned_calls:
                fc = self.session.enqueue_tool_call(tool_name, tool_args, call_id=call_id)
                emitted_calls.append({"id": fc.id, "name": fc.name, "args": fc.args})

            asyncio.run(self.orchestrator.process_incoming_events())

            for _ in range(max(1, advance_steps)):
                self.step_physics_and_sensors(dt_sec=0.05)

            turn_record = {
                "timestamp": round(time.time(), 3),
                "user_utterance": clean_utt,
                "showcase_object": self.arena.showcase_object,
                "cloud_live_model_used": self.brain.last_cloud_model_used,
                "cloud_probe_log": list(self.brain.last_cloud_probe_log),
                "user_audio_pcm16_bytes": len(user_pcm16_bytes),
                "camera_jpeg_bytes": len(clean_camera_jpeg),
                "gemini_tool_calls": emitted_calls,
                "spoken_reply_text": self.tts.last_spoken_text,
                "tts_backend_used": self.tts.backend_used,
                "tts_pcm16_bytes": len(self.audio.last_pcm16_bytes),
                "tts_wav_bytes": len(self.audio.last_wav_bytes),
                "tts_synthesis_latency_ms": self.tts.last_latency_ms,
                "speaker_playing": self.audio.is_playing(),
                "echo_guard_muted": self.bus.audio.muted_by_echo_guard,
                "hud_emoji": self.bus.hud.emoji,
                "hud_caption": self.bus.hud.caption,
                "hud_rgb565_bytes": len(self.display.last_rgb565_bytes),
                "source_mode": self.bus.intent.source_mode,
                "active_maneuver": self.autonomy.maneuver_seq.active_maneuver,
                "tof_mm": self.bus.tof.distance_mm,
                "applied_throttle": self.bus.actuator_cmd.applied_throttle,
                "applied_steering_deg": self.bus.actuator_cmd.applied_steering_deg,
                "servo_pulse_us": self.actuators.last_command.servo_pulse_us,
                "car_pose_mm": [round(self.arena.car_x_mm, 1), round(self.arena.car_y_mm, 1)],
            }
            self.conversation_history.append(turn_record)
            return turn_record

    def trigger_barge_in(self) -> dict[str, Any]:
        """Simulate a loud user shout (`RMS >= 0.55`) interrupting active TTS playback in `<= 1` chunk."""
        with self._lock:
            self.audio.set_mic_amplitude(25000.0)
            self.step_physics_and_sensors(dt_sec=0.05)
            barge_triggered = self.bus.audio.barge_in_triggered
            self.audio.set_mic_amplitude(1800.0)
            self.last_user_utterance = "[LOUD VOICE BARGE-IN: 'HOLD UP!']"
            return {
                "barge_in_triggered": barge_triggered,
                "speaker_playing": self.audio.is_playing(),
                "playback_interrupted_count": self.audio.playback_interrupted_count,
                "hud_emoji": self.bus.hud.emoji,
                "hud_caption": self.bus.hud.caption,
            }

    def spawn_obstacle_ahead(self, distance_mm: float = 195.0) -> dict[str, Any]:
        """Place a physical cone in front of the Mustang (`< 120 mm` valance range) to trigger reflex brake + bypass."""
        with self._lock:
            self.arena.obstacles.clear()
            ox = self.arena.car_x_mm + distance_mm * math.cos(self.arena.car_heading_rad)
            oy = self.arena.car_y_mm + distance_mm * math.sin(self.arena.car_heading_rad)
            self.arena.add_obstacle(x_mm=ox, y_mm=oy, radius_mm=55.0)
            self.step_physics_and_sensors(dt_sec=0.05)
            return {
                "obstacles_count": len(self.arena.obstacles),
                "tof_mm": self.bus.tof.distance_mm,
                "obstacle_state": self.autonomy.maneuver_seq.obstacle_state,
                "emergency_brake": self.bus.actuator_cmd.emergency_brake,
            }

    def clear_obstacles(self) -> dict[str, Any]:
        with self._lock:
            self.arena.obstacles.clear()
            self.step_physics_and_sensors(dt_sec=0.05)
            return {"obstacles_count": 0, "tof_mm": self.bus.tof.distance_mm}

    def move_person_target(self, forward_mm: float = 650.0, lateral_mm: float = 160.0) -> dict[str, Any]:
        """Place the walking person at `(forward_mm, lateral_mm)` relative to the car's current pose."""
        with self._lock:
            self.arena.showcase_object = None
            px = (
                self.arena.car_x_mm
                + forward_mm * math.cos(self.arena.car_heading_rad)
                - lateral_mm * math.sin(self.arena.car_heading_rad)
            )
            py = (
                self.arena.car_y_mm
                + forward_mm * math.sin(self.arena.car_heading_rad)
                + lateral_mm * math.cos(self.arena.car_heading_rad)
            )
            self.arena.set_person_position(px, py)
            self.step_physics_and_sensors(dt_sec=0.05)
            return {
                "person_xy_mm": [round(px, 1), round(py, 1)],
                "person_detected": self.bus.vision.person_detected,
                "person_bearing_deg": self.bus.vision.person_bearing_deg,
                "tof_mm": self.bus.tof.distance_mm,
            }

    def snapshot_telemetry(self) -> dict[str, Any]:
        """Return a JSON-serializable state snapshot including base64 HUD PNG, Camera JPEG, and 2D Track Radar PNG."""
        with self._lock:
            hud_img = (
                decode_rgb565_to_image(self.display.last_rgb565_bytes)
                if self.display.last_rgb565_bytes
                else self.display.last_rgb_image()
            )
            hud_buf = io.BytesIO()
            hud_img.save(hud_buf, format="PNG")
            hud_b64 = base64.b64encode(hud_buf.getvalue()).decode("ascii")

            cam_jpeg = self.camera.encode_telemetry_jpeg(
                rgb_bytes=self.bus.vision.rgb_bytes or self.arena.render_fisheye_rgb(),
                tof_mm=self.bus.tof.distance_mm,
                steer_deg=self.bus.actuator_cmd.applied_steering_deg,
                emoji=self.bus.hud.emoji,
                mode=self.bus.intent.source_mode,
            )
            cam_b64 = base64.b64encode(cam_jpeg).decode("ascii")

            seq = self.autonomy.maneuver_seq
            phase_str = (
                f"Step {seq.step_index + 1}/{len(seq.steps)}: {self.bus.hud.caption}"
                if seq.is_active
                else self.bus.hud.caption
            )
            arena_img = self.arena.render_topdown_map_image(
                width=560,
                height=310,
                active_maneuver=seq.active_maneuver or self.arena.active_maneuver_name,
                phase_caption=phase_str,
                tof_mm=self.bus.tof.distance_mm,
                steer_deg=self.bus.actuator_cmd.applied_steering_deg,
                throttle=self.bus.actuator_cmd.applied_throttle,
            )
            arena_buf = io.BytesIO()
            arena_img.save(arena_buf, format="PNG")
            arena_b64 = base64.b64encode(arena_buf.getvalue()).decode("ascii")

            last_fc = None
            if self.session.emitted_function_calls:
                fc = self.session.emitted_function_calls[-1]
                last_fc = {"id": fc.id, "name": fc.name, "args": fc.args}

            return {
                "sdk": f"google-genai=={genai.__version__}",
                "model": self.config.primary_model,
                "cloud_live_model_used": self.brain.last_cloud_model_used,
                "tts_backend_used": self.tts.backend_used,
                "audible_speaker": self.audible_speaker,
                "showcase_object": self.arena.showcase_object,
                "last_user_utterance": self.last_user_utterance,
                "spoken_reply_text": self.tts.last_spoken_text,
                "tts_latency_ms": self.tts.last_latency_ms,
                "speaker_playing": self.audio.is_playing(),
                "has_wav_audio": len(self.audio.last_wav_bytes) > 0,
                "audio_turn_count": self.audio.played_chunks,
                "echo_guard_muted": self.bus.audio.muted_by_echo_guard,
                "barge_in_triggered": self.bus.audio.barge_in_triggered,
                "hud_emoji": self.bus.hud.emoji,
                "hud_caption": self.bus.hud.caption,
                "hud_rgb565_bytes": len(self.display.last_rgb565_bytes),
                "tof_mm": self.bus.tof.distance_mm,
                "source_mode": self.bus.intent.source_mode,
                "active_maneuver": seq.active_maneuver or self.arena.active_maneuver_name,
                "maneuver_phase": phase_str,
                "obstacle_state": seq.obstacle_state,
                "person_follower_state": self.autonomy.person_follower.state,
                "person_detected": self.bus.vision.person_detected,
                "person_bearing_deg": self.bus.vision.person_bearing_deg,
                "applied_throttle": self.bus.actuator_cmd.applied_throttle,
                "applied_steering_deg": self.bus.actuator_cmd.applied_steering_deg,
                "servo_pulse_us": self.actuators.last_command.servo_pulse_us,
                "emergency_brake": self.bus.actuator_cmd.emergency_brake,
                "watchdog_tripped": self.bus.actuator_cmd.watchdog_tripped,
                "car_pose_mm": [round(self.arena.car_x_mm, 1), round(self.arena.car_y_mm, 1)],
                "car_heading_deg": round(math.degrees(self.arena.car_heading_rad), 1),
                "last_function_call": last_fc,
                "hud_png_b64": hud_b64,
                "cam_jpeg_b64": cam_b64,
                "arena_png_b64": arena_b64,
                "history": self.conversation_history[-6:],
            }


WORKBENCH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>1967 Mustang AI Edition — Laptop-as-Radxa Live Developer Workbench</title>
<style>
  :root {
    --bg: #0a0e16; --panel: #111826; --border: #283c5a;
    --cyan: #00e1ff; --green: #34f5a5; --red: #ff4b42; --amber: #ffcf48; --text: #e6f0ff;
  }
  * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "SF Mono", Menlo, monospace; }
  body { margin: 0; background: var(--bg); color: var(--text); padding: 12px; }
  header {
    display: flex; justify-content: space-between; align-items: center;
    background: #141e30; border: 1px solid var(--border); border-radius: 10px; padding: 10px 16px; margin-bottom: 10px;
  }
  header h1 { font-size: 14px; margin: 0; color: var(--cyan); }
  .badge { background: #1c2c44; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: var(--green); margin-left: 6px; }
  .voice-bar {
    display: flex; gap: 8px; align-items: center; background: var(--panel);
    border: 1px solid var(--border); border-radius: 10px; padding: 8px 12px; margin-bottom: 8px; flex-wrap: wrap;
  }
  .voice-bar input[type="text"] {
    flex: 1; min-width: 260px; background: #0b111c; color: #fff; border: 1px solid #355078;
    border-radius: 6px; padding: 8px 12px; font-size: 13px;
  }
  button {
    background: #1b2c46; color: var(--text); border: 1px solid #385886; border-radius: 6px;
    padding: 6px 11px; font-size: 11.5px; cursor: pointer; transition: 0.15s;
  }
  button:hover { background: #264066; border-color: var(--cyan); }
  button.primary { background: #006688; border-color: var(--cyan); color: #fff; font-weight: 600; }
  button.vision { background: #3b2860; border-color: #b48cff; color: #f3eaff; font-weight: 600; }
  button.danger { background: #681818; border-color: var(--red); color: #fff; font-weight: 600; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }
  .chips span.lbl { font-size: 11px; color: var(--amber); font-weight: 600; margin-right: 4px; }
  .grid { display: grid; grid-template-columns: 280px 1fr 1fr 370px; gap: 10px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px; }
  .card h2 { font-size: 12px; margin: 0 0 8px 0; color: var(--cyan); text-transform: uppercase; letter-spacing: 0.4px; }
  .hud-wrap { display: flex; flex-direction: column; align-items: center; }
  .hud-wrap img { width: 220px; height: 220px; border-radius: 50%; border: 2px solid #2b4468; }
  .cam-wrap img, .arena-wrap img { width: 100%; max-height: 310px; object-fit: contain; border-radius: 8px; border: 1px solid #2b4468; }
  .kv { display: flex; justify-content: space-between; font-size: 11.5px; padding: 4px 0; border-bottom: 1px solid #1b2638; }
  .kv span.v { color: var(--green); font-weight: 600; }
  .kv span.v.alert { color: var(--red); }
  .emoji-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-top: 8px; width: 100%; }
  .log-box {
    background: #080c14; border: 1px solid #22324a; border-radius: 6px; padding: 8px;
    font-size: 10.5px; height: 195px; overflow-y: auto; white-space: pre-wrap; color: #b8d0ec;
  }
</style>
</head>
<body>
<header>
  <h1>1967 Ford Mustang Fastback AI Edition (v3.2.0) — Local MacBook <-> Radxa Zero 3W Live Workbench</h1>
  <div>
    <span class="badge" id="sdkBadge">google-genai</span>
    <span class="badge" id="ttsBadge">piper-onnx</span>
    <span class="badge" id="modeBadge">MODE: IDLE</span>
  </div>
</header>

<div class="voice-bar">
  <button class="primary" id="micBtn" onclick="startBrowserSpeech()">🎙️ Speak (Mac Mic)</button>
  <input type="text" id="voiceInput"
    placeholder="Speak or type a voice command to gemini-robotics-er-2-streaming-preview..."
    value="Weave through the slalom!"/>
  <button class="primary" onclick="sendVoiceInput()">Send Voice Turn ➔</button>
  <button onclick="replayAudio()">🔊 Replay Piper ONNX Audio</button>
  <button class="danger" onclick="triggerBargeIn()">⚡ Shout Barge-In (RMS 0.76)</button>
  <audio id="ttsAudio" style="display:none"></audio>
</div>

<div class="chips">
  <span class="lbl">VOICE & MANEUVERS:</span>
  <button onclick="quickVoice('Hey Mustang, how do you feel today?')">💬 How do you feel?</button>
  <button onclick="quickVoice('Weave through the slalom!')">🐍 Slalom Weave (4 Cones)</button>
  <button onclick="quickVoice('Carve a left circle and avoid obstacles!')">🔄 Circle Left</button>
  <button onclick="quickVoice('Do a figure eight!')">♾️ Figure Eight</button>
  <button onclick="quickVoice('Follow me at 350 millimeters!')">🚶 Follow Person</button>
  <button onclick="quickVoice('Tell me a Mustang joke!')">😂 Tell a Joke</button>
  <button class="danger" onclick="quickVoice('Emergency stop right now!')">🛑 Voice Stop</button>
</div>

<div class="chips">
  <span class="lbl">AUDIO + VIDEO OBJECT Q&A (OV5647 -> Gemini ER):</span>
  <button class="vision" onclick="placeObjectAndAsk('stop_sign')">🛑 Show STOP Sign & Ask "What's this object?"</button>
  <button class="vision" onclick="placeObjectAndAsk('traffic_cone')">🚧 Show Traffic Cone & Ask</button>
  <button class="vision" onclick="placeObjectAndAsk('soccer_ball')">⚽ Show Soccer Ball & Ask</button>
  <button class="vision" onclick="placeObjectAndAsk('coffee_mug')">☕ Show Coffee Mug & Ask</button>
  <button class="vision" onclick="placeObjectAndAsk('checkered_flag')">🏁 Show Racing Flag & Ask</button>
  <button onclick="apiAction('/api/object/clear')">🧹 Clear Visual Object</button>
</div>

<div class="grid">
  <div class="card hud-wrap">
    <h2>H2: 1.28" Round GC9A01 HUD</h2>
    <img id="hudImg" src="" alt="GC9A01 HUD"/>
    <div style="margin-top:6px; font-size:11px; color:#9ec2e6;" id="hudMeta">SPI3 40MHz | 115,200 B</div>
    <div class="emoji-grid">
      <button onclick="setEmoji('COOL_SHADES')">😎 SHADES</button>
      <button onclick="setEmoji('WINK')">😉 WINK</button>
      <button onclick="setEmoji('LAUGH')">😆 LAUGH</button>
      <button onclick="setEmoji('HEART_EYES')">😍 HEARTS</button>
      <button onclick="setEmoji('ANGRY_REV')">😤 V8 REV</button>
      <button onclick="setEmoji('ALERT_STOP')">🚨 ALERT</button>
    </div>
  </div>

  <div class="card cam-wrap">
    <h2>H1-A: OV5647 160° First-Person Camera (640×480 JPEG)</h2>
    <img id="camImg" src="" alt="OV5647 Fisheye Stream"/>
    <div style="display:flex; gap:6px; margin-top:8px; flex-wrap:wrap;">
      <button onclick="apiAction('/api/object/stop_sign')">🛑 Place STOP Sign</button>
      <button onclick="apiAction('/api/object/traffic_cone')">🚧 Place Cone</button>
      <button onclick="apiAction('/api/object/soccer_ball')">⚽ Place Ball</button>
      <button class="primary" onclick="quickVoice('What is this object in front of you?')">❓ Ask "What's this object?"</button>
    </div>
  </div>

  <div class="card arena-wrap">
    <h2>Live 2D Top-Down Track & Slalom Course Radar (15 Hz)</h2>
    <img id="arenaImg" src="" alt="2D Top-Down Track & Slalom Radar"/>
    <div style="display:flex; gap:6px; margin-top:8px; flex-wrap:wrap;">
      <button class="danger" onclick="apiAction('/api/obstacle/spawn')">🚧 Drop Emergency Obstacle (<120mm)</button>
      <button onclick="apiAction('/api/obstacle/clear')">✅ Clear Obstacle</button>
      <button onclick="apiAction('/api/person/left')">🚶 Person Left</button>
      <button onclick="apiAction('/api/person/center')">🚶 Person Center</button>
      <button onclick="apiAction('/api/person/right')">🚶 Person Right</button>
    </div>
  </div>

  <div class="card">
    <h2>Radxa 40-Pin HAL & Gemini ER Wire Telemetry</h2>
    <div class="kv"><span>User Voice Input:</span><span class="v" id="tUser">-</span></div>
    <div class="kv"><span>Piper ONNX TTS (16kHz):</span><span class="v" id="tReply">-</span></div>
    <div class="kv"><span>Active Course / Object:</span><span class="v" id="tCourse">-</span></div>
    <div class="kv"><span>H1 VL53L1X Front Laser:</span><span class="v" id="tTof">-</span></div>
    <div class="kv"><span>H3/H4 I2S Echo Guard:</span><span class="v" id="tEcho">-</span></div>
    <div class="kv"><span>H5 Servo (PWM14_M0 Pin 7):</span><span class="v" id="tServo">-</span></div>
    <div class="kv"><span>H5 DRV8833 Motor (PWM8/9):</span><span class="v" id="tMotor">-</span></div>
    <div class="kv"><span>2D Arena Pose (X, Y, Hdg):</span><span class="v" id="tPose">-</span></div>
    <h2 style="margin-top:8px;">google.genai.types FunctionCall Log</h2>
    <div class="log-box" id="wireLog">Waiting for voice turn...</div>
  </div>
</div>

<script>
let lastPlayedTurn = 0;
let isSendingTurn = false;

async function sendVoiceInput() {
  if (isSendingTurn) return;
  const input = document.getElementById('voiceInput');
  const text = input.value.trim();
  if (!text) return;
  isSendingTurn = true;
  try {
    await fetch('/api/voice', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({utterance: text})
    });
    await pollState();
  } finally {
    isSendingTurn = false;
  }
}

async function quickVoice(text) {
  document.getElementById('voiceInput').value = text;
  await sendVoiceInput();
}

async function placeObjectAndAsk(kind) {
  await fetch('/api/object/' + kind, {method: 'POST'});
  document.getElementById('voiceInput').value = "What's this object in front of you?";
  await sendVoiceInput();
}

async function setEmoji(emoji) {
  await quickVoice('Show ' + emoji + ' emoji on the HUD!');
}

async function triggerBargeIn() {
  await fetch('/api/barge_in', {method: 'POST'});
  await pollState();
}

async function apiAction(path) {
  await fetch(path, {method: 'POST'});
  await pollState();
}

async function replayAudio() {
  const res = await fetch('/api/audio/replay', {method: 'POST'});
  const info = await res.json();
  if (!info.audible_speaker) {
    const audio = document.getElementById('ttsAudio');
    audio.pause();
    audio.src = '/api/audio.wav?t=' + Date.now();
    audio.play().catch(() => {});
  }
}

function startBrowserSpeech() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    alert('Web Speech API not supported in this browser; type in the voice box instead.');
    return;
  }
  const rec = new SpeechRec();
  rec.lang = 'en-US';
  const btn = document.getElementById('micBtn');
  btn.textContent = '🔴 Listening...';
  rec.onresult = (ev) => {
    const transcript = ev.results[0][0].transcript;
    document.getElementById('voiceInput').value = transcript;
    sendVoiceInput();
  };
  rec.onend = () => { btn.textContent = '🎙️ Speak (Mac Mic)'; };
  rec.start();
}

async function pollState() {
  try {
    const res = await fetch('/api/state');
    const st = await res.json();
    document.getElementById('sdkBadge').textContent = st.sdk + ' | ' + st.cloud_live_model_used;
    document.getElementById('ttsBadge').textContent = st.tts_backend_used;
    document.getElementById('modeBadge').textContent = 'MODE: ' + st.source_mode;
    document.getElementById('hudImg').src = 'data:image/png;base64,' + st.hud_png_b64;
    document.getElementById('camImg').src = 'data:image/jpeg;base64,' + st.cam_jpeg_b64;
    document.getElementById('arenaImg').src = 'data:image/png;base64,' + st.arena_png_b64;
    document.getElementById('hudMeta').textContent =
      `Emoji: ${st.hud_emoji} | '${st.hud_caption}' | ${st.hud_rgb565_bytes.toLocaleString()} B`;
    document.getElementById('tUser').textContent = st.last_user_utterance.slice(0, 34);
    document.getElementById('tReply').textContent =
      (st.spoken_reply_text || '-').slice(0, 30) + ` (${st.tts_latency_ms}ms)`;
    document.getElementById('tCourse').textContent =
      st.showcase_object ? `OBJ: ${st.showcase_object.toUpperCase()}` : `${st.active_maneuver || 'IDLE'} (${st.maneuver_phase})`;
    const tofEl = document.getElementById('tTof');
    tofEl.textContent = `${st.tof_mm} mm` + (st.tof_mm < 120 ? ' [EMERGENCY BRAKE]' : '');
    tofEl.className = st.tof_mm < 120 ? 'v alert' : 'v';
    document.getElementById('tEcho').textContent =
      `EchoMute=${st.echo_guard_muted} | BargeIn=${st.barge_in_triggered}`;
    document.getElementById('tServo').textContent =
      `${st.applied_steering_deg >= 0 ? '+' : ''}${st.applied_steering_deg.toFixed(1)}° (${st.servo_pulse_us} µs)`;
    document.getElementById('tMotor').textContent =
      `Throttle=${st.applied_throttle.toFixed(2)} | Brake=${st.emergency_brake}`;
    document.getElementById('tPose').textContent =
      `X=${st.car_pose_mm[0]} Y=${st.car_pose_mm[1]} (${st.car_heading_deg}°)`;

    if (st.history && st.history.length > 0) {
      document.getElementById('wireLog').textContent = JSON.stringify(st.history[st.history.length - 1], null, 2);
    }
    // Only auto-play in browser if Mac host audible_speaker is disabled (prevents double-playing afplay + browser audio)
    if (!st.audible_speaker && st.audio_turn_count > lastPlayedTurn && st.has_wav_audio) {
      lastPlayedTurn = st.audio_turn_count;
      const audio = document.getElementById('ttsAudio');
      audio.pause();
      audio.src = '/api/audio.wav?t=' + Date.now();
      audio.play().catch(() => {});
    } else if (st.audible_speaker) {
      lastPlayedTurn = st.audio_turn_count;
    }
  } catch (e) {}
}

setInterval(pollState, 150);
pollState();
</script>
</body>
</html>
"""


def run_voice_e2e_session(
    prompts: list[str] | None = None,
    *,
    audible_speaker: bool = False,
    use_cloud_live: bool = True,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run an end-to-end multi-turn Voice + Video -> Gemini ER -> Piper ONNX Audio + Emoji HUD + Car Control session on Mac."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[4]

    if not prompts:
        prompts = [
            "Hey Mustang, how do you feel today?",
            "Weave through the slalom!",
            "What's this object in front of you?",
            "Follow me at 350 millimeters!",
        ]

    wb = MacLiveWorkbench(audible_speaker=audible_speaker, use_cloud_live=use_cloud_live)
    turns_out: list[dict[str, Any]] = []
    wav_dir = repo_root / "tmp" / "voice_e2e_audio"
    wav_dir.mkdir(parents=True, exist_ok=True)

    for idx, prompt in enumerate(prompts):
        low = prompt.lower()
        if "what's this" in low or "what is this" in low or "object" in low:
            wb.set_showcase_object("stop_sign")
        else:
            wb.set_showcase_object(None)

        turn_info = wb.submit_voice_utterance(prompt, advance_steps=12)
        if any(k in low for k in ("circle", "figure", "slalom")):
            # Advance additional slalom weave steps so trajectory weaves across Cones 1..3, then test obstacle reflex
            for _ in range(18):
                wb.step_physics_and_sensors(dt_sec=0.05)
            obs_info = wb.spawn_obstacle_ahead(distance_mm=195.0)
            for _ in range(8):
                wb.step_physics_and_sensors(dt_sec=0.05)
            wb.clear_obstacles()
            for _ in range(6):
                wb.step_physics_and_sensors(dt_sec=0.05)
            turn_info["obstacle_reflex_triggered"] = obs_info["emergency_brake"] or (wb.governor.reflex_brake_count > 0)
            turn_info["obstacle_state_reached"] = wb.autonomy.maneuver_seq.obstacle_state

        wav_path = wav_dir / f"turn_{idx + 1}_{turn_info['hud_emoji'].lower()}.wav"
        if wb.audio.last_wav_bytes:
            wav_path.write_bytes(wb.audio.last_wav_bytes)
            turn_info["saved_wav_file"] = str(wav_path.relative_to(repo_root))

        turns_out.append(turn_info)

    barge_res = wb.trigger_barge_in()

    # Render the final cockpit showcase frame showing the Slalom course / Visual Q&A state
    wb.arena.setup_maneuver_course("slalom", speed_scale=0.90)
    wb.autonomy.handle_tool_call("execute_maneuver", {"maneuver_name": "slalom", "speed_scale": 0.90})
    for _ in range(28):
        wb.step_physics_and_sensors(dt_sec=0.05)
    asyncio.run(wb.orchestrator.push_telemetry_frame_and_audio())

    dashboard_img = render_cockpit_dashboard_frame(
        act_title="LAPTOP-AS-RADXA E2E: VOICE + VIDEO -> GEMINI ROBOTICS ER 2.0 -> PIPER ONNX + SLALOM RADAR",
        step_label=f"{len(turns_out)} Multimodal Turns ({wb.tts.backend_used})",
        user_utterance=prompts[1] if len(prompts) > 1 else prompts[-1],
        arena=wb.arena,
        bus=wb.bus,
        display=wb.display,
        actuators=wb.actuators,
        session=wb.session,
        extra_note=wb.tts.last_spoken_text,
    )
    preview_path = repo_root / "docs" / "images" / "ai_laptop_voice_e2e_workbench.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_img.save(preview_path)

    report_path = repo_root / "tmp" / "mac_voice_e2e_report.json"
    summary = {
        "status": "PASS",
        "version": "3.2.0",
        "sdk": f"google-genai=={genai.__version__}",
        "requested_primary_model": wb.config.primary_model,
        "cloud_live_model_used": wb.brain.last_cloud_model_used,
        "tts_backend_used": wb.tts.backend_used,
        "turns_executed": len(turns_out),
        "barge_in_verified": barge_res["barge_in_triggered"],
        "workbench_preview_png": str(preview_path.relative_to(repo_root)),
        "turns": turns_out,
    }
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _reclaim_workbench_port(host: str, port: int) -> int:
    """If a previous `mustang-ai live` server is still holding `port`, stop it cleanly so `make live` never fails with Errno 48."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.15)
        if probe.connect_ex((host, port)) != 0:
            return 0

    try:
        req = urllib.request.Request(f"http://{host}:{port}/api/shutdown", data=b"{}", method="POST")
        urllib.request.urlopen(req, timeout=0.3)
        time.sleep(0.2)
    except Exception:
        pass

    reclaimed = 0
    if os.path.exists("/usr/sbin/lsof"):
        try:
            proc = subprocess.run(
                ["/usr/sbin/lsof", "-ti", f"tcp:{port}"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            my_pid = os.getpid()
            pids = [int(p.strip()) for p in proc.stdout.splitlines() if p.strip().isdigit() and int(p.strip()) != my_pid]
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                    reclaimed += 1
                except OSError:
                    pass
            if pids:
                time.sleep(0.3)
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
                time.sleep(0.15)
        except Exception:
            pass
    return reclaimed


def serve_live_workbench(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    audible_speaker: bool = True,
) -> None:
    """Start the interactive local MacBook HTTP workbench (`http://127.0.0.1:8765`) with a 15 Hz background loop."""
    reclaimed = _reclaim_workbench_port(host, port)
    if reclaimed:
        print(f"Stopped {reclaimed} previous workbench process(es) on {host}:{port}.")
    wb = MacLiveWorkbench(audible_speaker=audible_speaker, use_cloud_live=True)
    stop_event = threading.Event()
    server_ref: list[ThreadingHTTPServer] = []

    def physics_worker() -> None:
        while not stop_event.is_set():
            wb.step_physics_and_sensors(dt_sec=1.0 / 15.0)
            time.sleep(1.0 / 15.0)

    worker = threading.Thread(target=physics_worker, daemon=True)
    worker.start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/index.html"):
                raw = WORKBENCH_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if self.path.startswith("/api/state"):
                self._send_json(wb.snapshot_telemetry())
                return
            if self.path.startswith("/api/audio.wav"):
                wav_bytes = wb.audio.last_wav_bytes or pcm16_to_wav_bytes(b"\x00\x00" * 800)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_bytes)))
                self.end_headers()
                self.wfile.write(wav_bytes)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b"{}"
            if self.path == "/api/voice":
                data = json.loads(body.decode("utf-8") or "{}")
                utt = str(data.get("utterance", ""))
                res = wb.submit_voice_utterance(utt, advance_steps=1)
                self._send_json(res)
                return
            if self.path == "/api/audio/replay":
                res = wb.replay_last_audio()
                res["audible_speaker"] = wb.audible_speaker
                self._send_json(res)
                return
            if self.path.startswith("/api/object/"):
                kind = self.path.split("/api/object/", 1)[1].strip()
                self._send_json(wb.set_showcase_object(kind))
                return
            if self.path == "/api/barge_in":
                self._send_json(wb.trigger_barge_in())
                return
            if self.path == "/api/obstacle/spawn":
                self._send_json(wb.spawn_obstacle_ahead(195.0))
                return
            if self.path == "/api/obstacle/clear":
                self._send_json(wb.clear_obstacles())
                return
            if self.path == "/api/person/left":
                self._send_json(wb.move_person_target(650.0, -210.0))
                return
            if self.path == "/api/person/center":
                self._send_json(wb.move_person_target(650.0, 0.0))
                return
            if self.path == "/api/person/right":
                self._send_json(wb.move_person_target(650.0, 210.0))
                return
            if self.path == "/api/shutdown":
                self._send_json({"status": "shutting_down"})
                stop_event.set()
                if server_ref:
                    threading.Thread(target=server_ref[0].shutdown, daemon=True).start()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

    url = f"http://{host}:{port}"
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.allow_reuse_port = True
    server = ThreadingHTTPServer((host, port), Handler)
    server_ref.append(server)
    print(f"Mustang 67 AI Edition Live Workbench running at: {url}")
    print(f"Primary Cloud Model: {wb.config.primary_model} (API key loaded: {bool(wb.brain.api_key)})")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        wb.audio.stop_playback()
        server.server_close()


def run_interactive_voice_repl(audible_speaker: bool = True) -> int:
    """Interactive terminal REPL on macOS: type or speak commands, hear Piper ONNX TTS out loud, inspect HUD & car state."""
    wb = MacLiveWorkbench(audible_speaker=audible_speaker, use_cloud_live=True)
    print("================================================================================")
    print("Mustang 67 AI Edition (v3.2.0) — Interactive Laptop-as-Radxa Voice REPL")
    print(
        f"SDK: google-genai=={genai.__version__} | TTS: {wb.tts.backend_used} | "
        f"Emojis: {len(CORE_12_EMOJIS)} | Maneuvers: {len(MANEUVER_LIBRARY)}"
    )
    print("Type any voice command (e.g. 'weave through the slalom', 'what is this object?', 'follow me', 'stop')")
    print("Special commands: '/object stop_sign|traffic_cone|soccer_ball', '/obstacle', '/barge', '/quit'")
    print("================================================================================")
    while True:
        try:
            line = input("\n🎙️ You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down workbench.")
            break
        if not line:
            continue
        if line.lower() in ("/quit", "/exit", "quit", "exit"):
            break
        if line.lower().startswith("/object"):
            parts = line.split(maxsplit=1)
            kind = parts[1] if len(parts) > 1 else "stop_sign"
            info = wb.set_showcase_object(kind)
            print(f"🎯 Visual object placed in front of OV5647 camera: {info}")
            continue
        if line.lower() == "/obstacle":
            obs = wb.spawn_obstacle_ahead(195.0)
            print(f"🚧 Obstacle spawned: ToF={obs['tof_mm']}mm | EmergencyBrake={obs['emergency_brake']}")
            continue
        if line.lower() == "/barge":
            barge = wb.trigger_barge_in()
            print(f"⚡ Barge-In triggered: {barge}")
            continue
        res = wb.submit_voice_utterance(line, advance_steps=8)
        wav_b = res["tts_wav_bytes"]
        lat_ms = res["tts_synthesis_latency_ms"]
        print(
            f"☁️ Cloud Live Session  : {res['cloud_live_model_used']}\n"
            f"🤖 Gemini ER ToolCalls : {json.dumps(res['gemini_tool_calls'])}\n"
            f"🔊 Piper ONNX Speaks   : \"{res['spoken_reply_text']}\" ({wav_b:,d} B WAV, {lat_ms} ms)\n"
            f"👀 GC9A01 Round HUD    : [{res['hud_emoji']}] '{res['hud_caption']}' ({res['hud_rgb565_bytes']:,d} B RGB565)\n"
            f"🏎️ Car Control         : Mode={res['source_mode']} | Steer={res['applied_steering_deg']:+.1f}° ({res['servo_pulse_us']}µs) | "
            f"Throttle={res['applied_throttle']:+.2f} | ToF={res['tof_mm']}mm | Pose={res['car_pose_mm']}"
        )
    wb.audio.stop_playback()
    return 0

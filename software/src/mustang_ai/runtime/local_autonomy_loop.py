"""Tier 1 (`local_autonomy_loop.py`): `15 Hz` (`66.7 ms`) Local Autonomy Sequencer,
Person-Follower, Voice/Emoji HUD Compositor, and `NON_BLOCKING` Tool Dispatcher (`v3.2.0`).
"""

from __future__ import annotations

import time
from typing import Any

from mustang_ai.config import RadxaPinConfig
from mustang_ai.features.maneuver_obstacle import ManeuverObstacleSequencer
from mustang_ai.features.person_follower import PersonFollowerController
from mustang_ai.features.voice_emoji_hud import VoiceEmojiHUDController
from mustang_ai.protocol.hal_contracts import (
    AudioStreamProtocol,
    CameraProtocol,
    DisplayHUDProtocol,
    TTSProtocol,
)
from mustang_ai.protocol.messages import ControlIntent
from mustang_ai.runtime.state_bus import StateBus


class LocalAutonomyEngine:
    """Tier 1 `15 Hz` (`66.7 ms`) coordinator integrating all 3 Major Functions over pure HAL protocols."""

    def __init__(
        self,
        camera: CameraProtocol,
        audio: AudioStreamProtocol,
        tts: TTSProtocol,
        display: DisplayHUDProtocol,
        bus: StateBus,
        pins: RadxaPinConfig | None = None,
    ) -> None:
        self.camera = camera
        self.audio = audio
        self.tts = tts
        self.display = display
        self.bus = bus
        self.pins = pins or RadxaPinConfig()

        self.voice_hud = VoiceEmojiHUDController(
            audio=self.audio,
            tts=self.tts,
            display=self.display,
            pins=self.pins,
        )
        self.maneuver_seq = ManeuverObstacleSequencer(pins=self.pins)
        self.person_follower = PersonFollowerController(pins=self.pins)

        self._manual_throttle: float = 0.0
        self._manual_steering_deg: float = 0.0
        self._manual_active: bool = False
        self._last_speak_emoji_ts: float = 0.0
        self.tool_call_history: list[dict[str, Any]] = []

    def handle_tool_call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a `NON_BLOCKING` tool call from `gemini-robotics-er-2-streaming`."""
        result: dict[str, Any]
        if name == "speak_with_emoji":
            self._last_speak_emoji_ts = time.monotonic()
            result = self.voice_hud.speak_with_emoji(
                emoji=str(args.get("emoji", "CRUISE")),
                hud_message=str(args.get("hud_message", "CRUISE READY")),
                spoken_text=str(args.get("spoken_text", "")),
            )
            result["status"] = "ok"

        elif name == "execute_maneuver":
            maneuver_name = str(args.get("maneuver_name", "circle_left"))
            speed_scale = float(args.get("speed_scale", 1.0))
            self.person_follower.configure(enabled=False)
            self._manual_active = False
            ok = self.maneuver_seq.start(maneuver_name, speed_scale=speed_scale)
            result = {
                "status": "started" if ok else "invalid_maneuver",
                "maneuver_name": maneuver_name,
                "speed_scale": speed_scale,
            }

        elif name == "set_follow_person_mode":
            enabled = bool(args.get("enabled", True))
            target_mode = str(args.get("target_mode", "body_legs_torso"))
            raw_box = args.get("target_box_2d")
            box_2d: tuple[int, int, int, int] | None = None
            if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
                box_2d = (int(raw_box[0]), int(raw_box[1]), int(raw_box[2]), int(raw_box[3]))
            standoff_mm = int(args.get("standoff_mm", self.pins.follow_standoff_mm))
            if enabled:
                self.maneuver_seq.stop()
                self._manual_active = False
            self.person_follower.configure(
                enabled=enabled,
                target_mode=target_mode,
                target_box_2d=box_2d,
                standoff_mm=standoff_mm,
            )
            result = {
                "status": "follow_enabled" if enabled else "follow_disabled",
                "target_mode": target_mode,
                "standoff_mm": self.person_follower.standoff_mm,
            }

        elif name == "set_drive_command":
            self.maneuver_seq.stop()
            self.person_follower.configure(enabled=False)
            self._manual_throttle = float(args.get("throttle", 0.0))
            self._manual_steering_deg = float(args.get("steering_deg", 0.0))
            self._manual_active = True
            emo = str(args.get("hud_emoji", "CRUISE"))
            msg = str(args.get("hud_message", "MANUAL DRIVE"))
            self.voice_hud.current_emoji = emo
            self.voice_hud.current_caption = msg
            result = {
                "status": "ok",
                "throttle": self._manual_throttle,
                "steering_deg": self._manual_steering_deg,
            }

        elif name == "emergency_stop":
            reason = str(args.get("reason", "EMERGENCY STOP"))[:16]
            self.maneuver_seq.stop()
            self.person_follower.configure(enabled=False)
            self._manual_active = False
            self._manual_throttle = 0.0
            self._manual_steering_deg = 0.0
            self.audio.stop_playback()
            self.voice_hud.current_emoji = "ALERT_STOP"
            self.voice_hud.current_caption = reason
            now = time.monotonic()
            self.bus.publish_intent(
                ControlIntent(
                    timestamp_s=now,
                    source_mode="IDLE",
                    desired_throttle=0.0,
                    desired_steering_deg=0.0,
                    hud_emoji="ALERT_STOP",
                    hud_caption=reason,
                )
            )
            result = {"status": "stopped", "reason": reason}
        else:
            result = {"status": "unknown_tool", "tool": name}

        self.tool_call_history.append({"tool": name, "args": args, "result": result})
        return result

    def step_once(self, dt_sec: float = 1.0 / 15.0) -> ControlIntent:
        """Run one `15 Hz` (`66.7 ms`) local autonomy tick: capture vision, poll mic, step active mode, update HUD."""
        now = time.monotonic()
        rgb = self.camera.capture_frame()
        vision = self.camera.extract_vision_metrics(
            rgb_bytes=rgb,
            target_box_2d=self.person_follower.hint_box_2d,
            target_mode=self.person_follower.target_mode,
        )
        self.bus.publish_vision(vision)

        audio_chunk = self.voice_hud.poll_mic_with_barge_in()
        self.bus.publish_audio(audio_chunk)
        if audio_chunk.barge_in_triggered:
            self.handle_tool_call("emergency_stop", {"reason": "VOICE BARGE-IN"})

        tof = self.bus.tof
        if self.maneuver_seq.is_active:
            intent = self.maneuver_seq.step(dt_sec=dt_sec, tof=tof, vision=vision)
            self.voice_hud.current_emoji = intent.hud_emoji
            self.voice_hud.current_caption = intent.hud_caption
        elif self.person_follower.enabled:
            intent = self.person_follower.step(dt_sec=dt_sec, tof=tof, vision=vision)
            if (now - self._last_speak_emoji_ts) > 1.0 or intent.hud_emoji in ("SURPRISED", "CONFUSED"):
                self.voice_hud.current_emoji = intent.hud_emoji
                self.voice_hud.current_caption = intent.hud_caption
        elif self._manual_active:
            intent = ControlIntent(
                timestamp_s=now,
                source_mode="MANUAL_TOOL",
                desired_throttle=self._manual_throttle,
                desired_steering_deg=self._manual_steering_deg,
                hud_emoji=self.voice_hud.current_emoji,
                hud_caption=self.voice_hud.current_caption,
            )
        else:
            intent = ControlIntent(
                timestamp_s=now,
                source_mode="IDLE",
                desired_throttle=0.0,
                desired_steering_deg=0.0,
                hud_emoji=self.voice_hud.current_emoji,
                hud_caption=self.voice_hud.current_caption,
            )

        self.bus.publish_intent(intent)
        hud_state = self.voice_hud.update_hud(tof=tof, actuator_cmd=self.bus.actuator_cmd)
        self.bus.publish_hud(hud_state)
        return intent

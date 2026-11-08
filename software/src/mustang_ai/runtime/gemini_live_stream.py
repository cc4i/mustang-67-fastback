"""Tier 2 (`gemini_live_stream.py`): `gemini-robotics-er-2-streaming-preview` WebSocket session &
`NON_BLOCKING` tool router (`v3.3.0`).
"""

from __future__ import annotations

import os
import sys
import time
import types as py_types
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

from mustang_ai.config import GeminiERConfig, load_gemini_api_key
from mustang_ai.protocol.hal_contracts import CameraProtocol, GeminiLiveSessionProtocol
from mustang_ai.protocol.messages import GeminiStreamEvent
from mustang_ai.runtime.local_autonomy_loop import LocalAutonomyEngine
from mustang_ai.runtime.state_bus import StateBus

try:
    import google.genai as genai  # type: ignore[import-not-found]
    from google.genai import types  # type: ignore[import-not-found]

    HAS_GOOGLE_GENAI = True
except Exception:  # pragma: no cover
    HAS_GOOGLE_GENAI = False

    class _Behavior(str, Enum):
        NON_BLOCKING = "NON_BLOCKING"
        BLOCKING = "BLOCKING"

    class _Modality(str, Enum):
        TEXT = "TEXT"
        AUDIO = "AUDIO"

    @dataclass
    class _FunctionDeclaration:
        name: str = ""
        description: str = ""
        behavior: Any = _Behavior.NON_BLOCKING
        parameters: dict[str, Any] = field(default_factory=dict)

        def __post_init__(self) -> None:
            if self.behavior == "NON_BLOCKING":
                self.behavior = _Behavior.NON_BLOCKING

    @dataclass
    class _Tool:
        function_declarations: list[_FunctionDeclaration] = field(default_factory=list)

    @dataclass
    class _Part:
        text: str | None = None
        inline_data: Any = None

        @classmethod
        def from_bytes(cls, *, data: bytes, mime_type: str) -> _Part:
            return cls(inline_data={"data": data, "mime_type": mime_type})

    @dataclass
    class _Content:
        role: str | None = None
        parts: list[_Part] = field(default_factory=list)

    @dataclass
    class _ThinkingConfig:
        thinking_budget: int = 0

    @dataclass
    class _AudioTranscriptionConfig:
        pass

    @dataclass
    class _GenerateContentConfig:
        system_instruction: Any = None
        tools: list[_Tool] = field(default_factory=list)
        temperature: float = 0.35
        thinking_config: _ThinkingConfig | None = None

    @dataclass
    class _LiveConnectConfig:
        response_modalities: list[Any] = field(default_factory=list)
        system_instruction: _Content | None = None
        tools: list[_Tool] = field(default_factory=list)
        thinking_config: _ThinkingConfig | None = None
        output_audio_transcription: _AudioTranscriptionConfig | None = None

    @dataclass
    class _Blob:
        data: bytes = b""
        mime_type: str = ""

    @dataclass
    class _FunctionCall:
        id: str = ""
        name: str = ""
        args: dict[str, Any] = field(default_factory=dict)

    @dataclass
    class _FunctionResponse:
        id: str = ""
        name: str = ""
        response: dict[str, Any] = field(default_factory=dict)

    types_mod = py_types.ModuleType("google.genai.types")
    types_mod.Behavior = _Behavior  # type: ignore[attr-defined]
    types_mod.Modality = _Modality  # type: ignore[attr-defined]
    types_mod.FunctionDeclaration = _FunctionDeclaration  # type: ignore[attr-defined]
    types_mod.Tool = _Tool  # type: ignore[attr-defined]
    types_mod.Part = _Part  # type: ignore[attr-defined]
    types_mod.Content = _Content  # type: ignore[attr-defined]
    types_mod.ThinkingConfig = _ThinkingConfig  # type: ignore[attr-defined]
    types_mod.AudioTranscriptionConfig = _AudioTranscriptionConfig  # type: ignore[attr-defined]
    types_mod.GenerateContentConfig = _GenerateContentConfig  # type: ignore[attr-defined]
    types_mod.LiveConnectConfig = _LiveConnectConfig  # type: ignore[attr-defined]
    types_mod.Blob = _Blob  # type: ignore[attr-defined]
    types_mod.FunctionCall = _FunctionCall  # type: ignore[attr-defined]
    types_mod.FunctionResponse = _FunctionResponse  # type: ignore[attr-defined]

    class _FallbackClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    genai_mod = py_types.ModuleType("google.genai")
    genai_mod.__version__ = "2.34.0"  # type: ignore[attr-defined]
    genai_mod.types = types_mod  # type: ignore[attr-defined]
    genai_mod.Client = _FallbackClient  # type: ignore[attr-defined]

    google_mod = sys.modules.get("google") or py_types.ModuleType("google")
    google_mod.genai = genai_mod  # type: ignore[attr-defined]
    sys.modules.setdefault("google", google_mod)
    sys.modules.setdefault("google.genai", genai_mod)
    sys.modules.setdefault("google.genai.types", types_mod)
    genai = genai_mod
    types = types_mod


def build_gemini_tool_declarations() -> list[dict[str, Any]]:
    """Function declarations exposed to `gemini-robotics-er-2-streaming-preview`."""
    return [
        {
            "name": "speak_with_emoji",
            "description": (
                "Synthesize `spoken_text` locally on Radxa Zero 3W via Piper ONNX TTS "
                "(`MAX98357A` speaker) while displaying one of the 12 fun emojis and a short "
                "caption on the 1.28-inch round GC9A01 rear fastback window HUD."
            ),
            "behavior": "NON_BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "emoji": {
                        "type": "STRING",
                        "description": (
                            "Fun emoji ID: CRUISE, HAPPY, WINK, LAUGH, COOL_SHADES, HEART_EYES, "
                            "SURPRISED, THINKING, CONFUSED, SLEEPY, ANGRY_REV, or ALERT_STOP."
                        ),
                    },
                    "hud_message": {
                        "type": "STRING",
                        "description": "Short caption (<=16 chars) rendered on the 240x240 circular GC9A01 screen.",
                    },
                    "spoken_text": {
                        "type": "STRING",
                        "description": "Spoken reply synthesized locally into 16 kHz PCM via Piper ONNX TTS.",
                    },
                },
                "required": ["emoji", "hud_message", "spoken_text"],
            },
        },
        {
            "name": "execute_maneuver",
            "description": (
                "Trigger a driving action (`move_forward`, `reverse_back`, `keep_going`, `turn_left`, `turn_right`) "
                "or one of the 7 predefined trick maneuvers (`circle_left`, `circle_right`, `figure_eight`, "
                "`slalom`, `spin_wiggle`, `u_turn_3pt`, `patrol`) with automatic <20 ms VL53L1X obstacle braking, "
                "~150 mm reverse, and S-curve bypass recovery."
            ),
            "behavior": "NON_BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "maneuver_name": {"type": "STRING"},
                    "speed_scale": {"type": "NUMBER"},
                },
                "required": ["maneuver_name"],
            },
        },
        {
            "name": "set_follow_person_mode",
            "description": (
                "Enable or disable coupled visual-laser person-following (`350 mm` standoff) "
                "using the 160-degree OV5647 fisheye camera and VL53L1X front laser."
            ),
            "behavior": "NON_BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "enabled": {"type": "BOOLEAN"},
                    "target_mode": {"type": "STRING"},
                    "target_box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                    "standoff_mm": {"type": "INTEGER"},
                },
                "required": ["enabled"],
            },
        },
        {
            "name": "set_drive_command",
            "description": "Set manual throttle (-1.0..+1.0) and steering angle (-15.0..+15.0 deg).",
            "behavior": "NON_BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "throttle": {"type": "NUMBER"},
                    "steering_deg": {"type": "NUMBER"},
                    "hud_emoji": {"type": "STRING"},
                    "hud_message": {"type": "STRING"},
                },
                "required": ["throttle", "steering_deg"],
            },
        },
        {
            "name": "emergency_stop",
            "description": "Immediately short-brake the DRV8833 H-bridge and flash ALERT_STOP on the HUD.",
            "behavior": "NON_BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {"reason": {"type": "STRING"}},
                "required": ["reason"],
            },
        },
    ]


def build_gemini_genai_tools() -> list[types.Tool]:
    """Construct validated `google.genai.types.Tool` declarations (`google-genai>=2.34.0`)."""
    raw_decls = build_gemini_tool_declarations()
    fn_decls = [types.FunctionDeclaration(**decl) for decl in raw_decls]
    return [types.Tool(function_declarations=fn_decls)]


def build_gemini_live_connect_config(
    config: GeminiERConfig | None = None,
    *,
    modality: types.Modality = types.Modality.TEXT,
) -> types.LiveConnectConfig:
    """Build the production `google.genai.types.LiveConnectConfig` used on Radxa Zero 3W and Mac simulation."""
    cfg = config or GeminiERConfig()
    kwargs: dict[str, Any] = {
        "response_modalities": [modality],
        "system_instruction": types.Content(parts=[types.Part(text=cfg.system_instruction)]),
        "tools": build_gemini_genai_tools(),
    }
    if modality == types.Modality.AUDIO:
        kwargs["output_audio_transcription"] = types.AudioTranscriptionConfig()
    else:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=cfg.thinking_budget)
    return types.LiveConnectConfig(**kwargs)


class RadxaGeminiLiveSession:
    """Production `google-genai` (`>=2.34.0`) Live API session adapter satisfying `GeminiLiveSessionProtocol`."""

    def __init__(self, session: Any = None, config: GeminiERConfig | None = None) -> None:
        self._session = session
        self.config = config or GeminiERConfig()
        self.live_connect_config: types.LiveConnectConfig = build_gemini_live_connect_config(self.config)
        self.sent_video_frames: int = 0
        self.sent_audio_chunks: int = 0
        self.last_video_blob: types.Blob | None = None
        self.last_audio_blob: types.Blob | None = None
        self.sent_tool_responses: list[dict[str, Any]] = []
        self.sent_genai_function_responses: list[types.FunctionResponse] = []

    @classmethod
    def create_genai_client(
        cls,
        api_key: str | None = None,
        *,
        vertexai: bool | None = None,
        project: str | None = None,
        location: str | None = None,
    ) -> genai.Client:
        """Instantiate an official `google.genai.Client` for AI Studio (`gemini-robotics-er-2-streaming-preview`) or Vertex AI."""
        resolved_key = (api_key or load_gemini_api_key()).strip()
        if resolved_key and vertexai is not True:
            return genai.Client(api_key=resolved_key, vertexai=False)
        resolved_proj = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        resolved_loc = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        return genai.Client(vertexai=True, project=resolved_proj, location=resolved_loc)

    async def send_video_jpeg(self, jpeg_bytes: bytes) -> None:
        self.sent_video_frames += 1
        blob = types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
        self.last_video_blob = blob
        if self._session is not None:
            await self._session.send_realtime_input(video=blob)

    async def send_audio_pcm16(self, pcm16_bytes: bytes) -> None:
        self.sent_audio_chunks += 1
        blob = types.Blob(data=pcm16_bytes, mime_type="audio/pcm;rate=16000")
        self.last_audio_blob = blob
        if self._session is not None:
            await self._session.send_realtime_input(audio=blob)

    async def receive_events(self) -> AsyncIterator[GeminiStreamEvent]:
        if self._session is None:
            return
        try:
            async for response in self._session.receive():
                sc = getattr(response, "server_content", None)
                if sc is not None and getattr(sc, "model_turn", None) is not None:
                    for part in getattr(sc.model_turn, "parts", None) or []:
                        part_text = getattr(part, "text", None)
                        if part_text:
                            yield GeminiStreamEvent(
                                timestamp_s=time.monotonic(),
                                event_type="text",
                                text=str(part_text),
                            )
                if getattr(response, "tool_call", None):
                    for fc in response.tool_call.function_calls:
                        yield GeminiStreamEvent(
                            timestamp_s=time.monotonic(),
                            event_type="tool_call",
                            tool_name=fc.name or "",
                            tool_call_id=getattr(fc, "id", None) or (fc.name or "call"),
                            tool_args=dict(fc.args or {}),
                        )
        except Exception as exc:
            yield GeminiStreamEvent(
                timestamp_s=time.monotonic(),
                event_type="disconnect",
                text=f"{type(exc).__name__}: {exc}",
            )

    async def send_tool_response(self, call_id: str, tool_name: str, result: dict[str, object]) -> None:
        fn_resp = types.FunctionResponse(
            id=call_id,
            name=tool_name,
            response={**result, "scheduling": "SILENT"},
        )
        self.sent_genai_function_responses.append(fn_resp)
        self.sent_tool_responses.append({"id": call_id, "name": tool_name, "result": result})
        if self._session is not None:
            await self._session.send_tool_response(function_responses=[fn_resp])


class GeminiLiveOrchestrator:
    """Tier 2 AsyncIO bridge streaming `5 Hz` JPEG + telemetry and `16 kHz` PCM audio to `GeminiLiveSessionProtocol`."""

    def __init__(
        self,
        session: GeminiLiveSessionProtocol,
        camera: CameraProtocol,
        autonomy: LocalAutonomyEngine,
        bus: StateBus,
    ) -> None:
        self.session = session
        self.camera = camera
        self.autonomy = autonomy
        self.bus = bus
        self.wifi_disconnected: bool = False
        self._last_sent_vision_seq: int = -1
        self._last_sent_audio_ts: float = -1.0

    async def push_telemetry_frame_and_audio(self) -> None:
        """Encode current `OV5647` RGB frame with telemetry banner and send alongside unmuted `INMP441` PCM16."""
        vision = self.bus.vision
        if vision.rgb_bytes and vision.frame_seq != self._last_sent_vision_seq:
            self._last_sent_vision_seq = vision.frame_seq
            jpeg_bytes = self.camera.encode_telemetry_jpeg(
                rgb_bytes=vision.rgb_bytes,
                tof_mm=self.bus.tof.distance_mm,
                steer_deg=self.bus.actuator_cmd.applied_steering_deg,
                emoji=self.bus.hud.emoji,
                mode=self.bus.intent.source_mode,
            )
            await self.session.send_video_jpeg(jpeg_bytes)

        audio = self.bus.audio
        if audio.pcm16_bytes and not audio.muted_by_echo_guard and audio.timestamp_s != self._last_sent_audio_ts:
            self._last_sent_audio_ts = audio.timestamp_s
            await self.session.send_audio_pcm16(audio.pcm16_bytes)

    async def process_incoming_events(self) -> int:
        """Consume queued events from `session.receive_events()` and dispatch tool calls to Tier 1.

        If multiple `speak_with_emoji` calls arrive in the same batch, coalesce their `spoken_text`
        into a single local Piper ONNX synthesis & playback call so sentences never overlap.
        """
        events: list[GeminiStreamEvent] = []
        async for ev in self.session.receive_events():
            events.append(ev)

        if not events:
            return 0

        speak_events = [e for e in events if e.event_type == "tool_call" and e.tool_name == "speak_with_emoji"]
        merged_spoken_text = " ".join(
            str(e.tool_args.get("spoken_text", "")).strip()
            for e in speak_events
            if str(e.tool_args.get("spoken_text", "")).strip()
        )
        speak_dispatched = False

        processed = 0
        for ev in events:
            processed += 1
            if ev.event_type == "disconnect":
                self.wifi_disconnected = True
                if not self.autonomy.maneuver_seq.is_active:
                    self.autonomy.voice_hud.current_emoji = "CONFUSED"
                    self.autonomy.voice_hud.current_caption = "WIFI RETRY..."
            elif ev.event_type == "tool_call":
                self.wifi_disconnected = False
                if ev.tool_name == "speak_with_emoji":
                    if not speak_dispatched:
                        speak_dispatched = True
                        last_speak_args = dict(speak_events[-1].tool_args)
                        if merged_spoken_text:
                            last_speak_args["spoken_text"] = merged_spoken_text
                        res = self.autonomy.handle_tool_call("speak_with_emoji", last_speak_args)
                    else:
                        res = {"status": "coalesced_into_single_utterance"}
                else:
                    res = self.autonomy.handle_tool_call(ev.tool_name, ev.tool_args)
                await self.session.send_tool_response(ev.tool_call_id, ev.tool_name, res)
        return processed

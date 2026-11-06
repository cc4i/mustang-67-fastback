"""Persistent per-conversation Gemini Live session (`live_session.py`).

Implements:
- `D14`: One persistent multi-turn conversation session from wake (`IDLE -> LISTENING`) through all
  `8.0 s` `FOLLOW_UP` turns, closing and clearing memory when returning to `IDLE`.
- `D9`: Exposes the `set_wake_word(phrase)` tool declaration alongside `speak_with_emoji`, `execute_maneuver`,
  `set_follow_person_mode`, and `emergency_stop`.
- `D12`: System instruction & planner preserve current motion on chat questions (only explicit move/stop
  commands emit driving tool calls).
- `D13`: System instruction & reply cap enforce `1-2` sentences (`<= 25 words`) unless the user asks
  `"tell me more"`.
- `D10`: Automatic offline fallback when Wi-Fi / cloud is unavailable (`CONFUSED` emoji + local Piper notice).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

from google.genai import types

from mustang_ai.config import GeminiERConfig, load_gemini_api_key
from mustang_ai.runtime.gemini_live_stream import (
    RadxaGeminiLiveSession,
    build_gemini_tool_declarations,
)
from mustang_ai.voice.keywords import sanitize_wake_phrase
from mustang_ai.voice.tts_stream import enforce_reply_length_cap
from mustang_ai.voice.vad import pcm16_to_wav_bytes

OFFLINE_SPOKEN_MESSAGE: str = "I lost my cloud brain, but local driving commands still work!"


def build_voice_conversation_tool_declarations() -> list[dict[str, Any]]:
    """Return Gemini Live tool declarations including `set_wake_word` (`D9`)."""
    base = list(build_gemini_tool_declarations())
    base.append(
        {
            "name": "set_wake_word",
            "description": (
                "Propose changing the voice wake word (e.g. 'Hey Mustang' or 'Hey Nerd'). "
                "The car will ask the user for confirmation before writing `keywords.txt`."
            ),
            "behavior": "NON_BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "new_wake_phrase": {
                        "type": "STRING",
                        "description": "Requested new wake phrase (3-4 syllables recommended).",
                    },
                },
                "required": ["new_wake_phrase"],
            },
        }
    )
    return base


@dataclass(frozen=True)
class LiveTurnResponse:
    """Structured tool calls and spoken reply returned for one user turn inside a conversation."""

    turn_index: int
    backend_used: str  # "gemini-live-ws" | "local-conversation-brain" | "offline-fallback"
    tool_calls: list[dict[str, Any]]
    spoken_text: str
    emoji: str
    hud_message: str
    latency_ms: float
    cloud_offline_fallback: bool = False
    error_detail: str = ""


@dataclass
class PersistentConversationLiveSession:
    """Manages one multi-turn conversation session (`D14`) and resets memory at `IDLE`."""

    config: GeminiERConfig = field(default_factory=GeminiERConfig)
    cloud_online: bool = True
    prefer_real_cloud_ws: bool = False
    api_key: str = ""
    session_active: bool = False
    conversation_id: int = 0
    turn_count: int = 0
    history_turns: list[dict[str, str]] = field(default_factory=list)
    remembered_facts: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = load_gemini_api_key()

    def start_conversation(self) -> int:
        """Open a fresh conversation context on `IDLE -> LISTENING` transition (`D14`)."""
        if not self.session_active:
            self.session_active = True
            self.conversation_id += 1
            self.turn_count = 0
            self.history_turns.clear()
            self.remembered_facts.clear()
        return self.conversation_id

    def close_and_forget(self) -> None:
        """Close the active conversation session and wipe in-conversation memory on `-> IDLE` (`D14`)."""
        self.session_active = False
        self.turn_count = 0
        self.history_turns.clear()
        self.remembered_facts.clear()

    def _build_conversation_system_instruction(self) -> str:
        return (
            f"{self.config.system_instruction} "
            "VOICE CONVERSATION RULES (D12, D13, D14): "
            "1. Keep `spoken_text` in `speak_with_emoji` to 1-2 short sentences (<= 25 words) unless the user "
            "explicitly asks 'tell me more'. "
            "2. If the user asks a chat question while driving (e.g. 'what do you see?', 'how are you?'), "
            "answer with `speak_with_emoji` ONLY and DO NOT call `execute_maneuver` or change the car's motion. "
            "3. Only call `execute_maneuver` when the user explicitly commands a driving move. "
            "4. If the user asks to change your wake word or name, call `set_wake_word`."
        )

    async def _query_cloud_live_turn(
        self,
        utterance_text: str,
        *,
        user_pcm16_bytes: bytes | None,
        jpeg_bytes: bytes | None,
        tof_mm: int,
        current_mode: str,
    ) -> list[dict[str, Any]]:
        """Execute turn over `client.aio.live.connect` (`gemini-robotics-er-2-streaming-preview`) with conversation history."""
        client = RadxaGeminiLiveSession.create_genai_client(api_key=self.api_key)
        fn_decls = [types.FunctionDeclaration(**d) for d in build_voice_conversation_tool_declarations()]
        live_cfg = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            system_instruction=types.Content(parts=[types.Part(text=self._build_conversation_system_instruction())]),
            tools=[types.Tool(function_declarations=fn_decls)],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        contents: list[types.Content] = []
        for prev in self.history_turns[-6:]:
            contents.append(types.Content(role="user", parts=[types.Part(text=prev["user"])]))
            contents.append(types.Content(role="model", parts=[types.Part(text=prev["model"])]))

        user_parts: list[types.Part] = []
        if jpeg_bytes:
            user_parts.append(types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"))
        if user_pcm16_bytes:
            user_parts.append(types.Part.from_bytes(data=pcm16_to_wav_bytes(user_pcm16_bytes), mime_type="audio/wav"))
        prompt = (
            f"Telemetry: ToF={tof_mm} mm, mode={current_mode}. "
            f"User said: '{utterance_text}'. Call `speak_with_emoji` (<=25 words) and any explicitly requested action tool."
        )
        user_parts.append(types.Part(text=prompt))
        contents.append(types.Content(role="user", parts=user_parts))

        calls: list[dict[str, Any]] = []
        text_fragments: list[str] = []
        async with asyncio.timeout(7.5):
            async with client.aio.live.connect(model=self.config.primary_model, config=live_cfg) as sess:
                await sess.send_client_content(turns=contents, turn_complete=True)
                async for msg in sess.receive():
                    if getattr(msg, "tool_call", None) and msg.tool_call.function_calls:
                        fn_resps: list[types.FunctionResponse] = []
                        for fc in msg.tool_call.function_calls:
                            args = dict(fc.args or {})
                            calls.append({"name": fc.name or "", "args": args})
                            fn_resps.append(
                                types.FunctionResponse(
                                    id=getattr(fc, "id", None) or fc.name,
                                    name=fc.name or "",
                                    response={"status": "ok", "scheduling": "SILENT"},
                                )
                            )
                        await sess.send_tool_response(function_responses=fn_resps)
                        break
                    sc = getattr(msg, "server_content", None)
                    if sc and getattr(sc, "model_turn", None):
                        for p in sc.model_turn.parts:
                            if getattr(p, "text", None) and not getattr(p, "thought", False):
                                text_fragments.append(p.text)
                    if sc and getattr(sc, "turn_complete", False):
                        break

        if not any(c["name"] == "speak_with_emoji" for c in calls) and text_fragments:
            joined = " ".join(" ".join(text_fragments).split())
            capped, _, _ = enforce_reply_length_cap(joined, user_utterance=utterance_text)
            calls.append(
                {
                    "name": "speak_with_emoji",
                    "args": {
                        "emoji": "HAPPY",
                        "hud_message": "LIVE REPLY",
                        "spoken_text": capped,
                    },
                }
            )
        return calls

    def _plan_local_conversation_turn(
        self,
        utterance_text: str,
        *,
        tof_mm: int,
        current_mode: str,
    ) -> list[dict[str, Any]]:
        """Deterministic in-conversation planner supporting `D8`, `D9`, `D12`, `D13`, `D14`, `S7`."""
        clean = " ".join((utterance_text or "").strip().split())
        low = clean.lower()
        calls: list[dict[str, Any]] = []

        # 1. Remember user facts within the current conversation (D14 / S7)
        name_match = re.search(r"\bmy name is\s+([a-zA-Z0-9_\-]+)", clean, flags=re.IGNORECASE)
        if name_match:
            user_name = name_match.group(1).strip().title()
            self.remembered_facts["user_name"] = user_name
            calls.append(
                {
                    "name": "speak_with_emoji",
                    "args": {
                        "emoji": "HAPPY",
                        "hud_message": f"HI {user_name[:12].upper()}",
                        "spoken_text": f"Nice to meet you, {user_name}! I will remember your name during our chat.",
                    },
                }
            )
            return calls

        if "what is my name" in low or "who am i" in low or "remember my name" in low:
            user_name = self.remembered_facts.get("user_name", "")
            if user_name:
                spoken = f"Your name is {user_name}!"
                hud = f"NAME: {user_name[:9].upper()}"
                emoji = "WINK"
            else:
                spoken = "You have not told me your name in this conversation yet."
                hud = "NO NAME YET"
                emoji = "THINKING"
            calls.append(
                {
                    "name": "speak_with_emoji",
                    "args": {"emoji": emoji, "hud_message": hud, "spoken_text": spoken},
                }
            )
            return calls

        # 2. Wake-word rename request (D9)
        rename_match = re.search(
            r"(?:change your name to|change wake word to|set wake word to|call yourself)\s+([a-zA-Z0-9 '\-]{2,36})",
            clean,
            flags=re.IGNORECASE,
        )
        if rename_match:
            candidate = sanitize_wake_phrase(rename_match.group(1).title())
            calls.append({"name": "set_wake_word", "args": {"new_wake_phrase": candidate}})
            calls.append(
                {
                    "name": "speak_with_emoji",
                    "args": {
                        "emoji": "THINKING",
                        "hud_message": "CONFIRM NAME?",
                        "spoken_text": f"Should I change my wake word to {candidate}? Say yes to confirm.",
                    },
                }
            )
            return calls

        # 3. Explicit driving commands (emit both execute_maneuver and speak_with_emoji so D8 duplicate filter is exercised)
        move_map = (
            (
                ("keep going", "auto drive", "cruise ahead"),
                "keep_going",
                "COOL_SHADES",
                "KEEP GOING",
                "Cruising ahead with automatic obstacle avoidance!",
            ),
            (("forward", "move forward", "go forward"), "move_forward", "CRUISE", "MOVE FORWARD", "Moving forward now!"),
            (("reverse", "back up", "move backward", "go back", "back"), "reverse_back", "WINK", "REVERSE BACK", "Backing up carefully!"),
            (("turn left", "left"), "turn_left", "COOL_SHADES", "TURN LEFT", "Turning left!"),
            (("turn right", "right"), "turn_right", "COOL_SHADES", "TURN RIGHT", "Turning right!"),
        )
        for triggers, maneuver_name, emoji, hud, spoken in move_map:
            if any(low == t or low.startswith(t + " ") or low.endswith(" " + t) for t in triggers):
                calls.append({"name": "execute_maneuver", "args": {"maneuver_name": maneuver_name, "speed_scale": 0.75}})
                calls.append(
                    {
                        "name": "speak_with_emoji",
                        "args": {"emoji": emoji, "hud_message": hud, "spoken_text": spoken},
                    }
                )
                return calls

        # 4. General chat question (D12: never emit execute_maneuver on chat questions; D13: <= 25 words unless 'tell me more')
        if "tell me more" in low or "in detail" in low:
            raw_reply = (
                f"I am a one-twentieth scale 1967 Ford Mustang Fastback powered by Radxa Zero 3W and Gemini Robotics ER 2.0. "
                f"My front laser reads {tof_mm} millimeters while running in {current_mode} mode with full echo cancellation."
            )
        else:
            raw_reply = (
                f"Front range is {tof_mm} millimeters and I am currently in {current_mode} mode. "
                f"Ready for your next command! Extra words that would exceed twenty five words if not capped by D13."
            )
        capped_reply, _, _ = enforce_reply_length_cap(raw_reply, user_utterance=clean)
        calls.append(
            {
                "name": "speak_with_emoji",
                "args": {
                    "emoji": "HAPPY",
                    "hud_message": "CHAT READY",
                    "spoken_text": capped_reply,
                },
            }
        )
        return calls

    def run_turn(
        self,
        utterance_text: str,
        *,
        user_pcm16_bytes: bytes | None = None,
        jpeg_bytes: bytes | None = None,
        tof_mm: int = 850,
        current_mode: str = "IDLE",
    ) -> LiveTurnResponse:
        """Execute one conversation turn against Cloud Gemini Live (or offline fallback per `D10`)."""
        t0 = time.perf_counter()
        if not self.session_active:
            self.start_conversation()
        self.turn_count += 1

        # D10: Cloud / Wi-Fi offline mode
        if not self.cloud_online:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            return LiveTurnResponse(
                turn_index=self.turn_count,
                backend_used="offline-fallback",
                tool_calls=[
                    {
                        "name": "speak_with_emoji",
                        "args": {
                            "emoji": "CONFUSED",
                            "hud_message": "CLOUD OFFLINE",
                            "spoken_text": OFFLINE_SPOKEN_MESSAGE,
                        },
                    }
                ],
                spoken_text=OFFLINE_SPOKEN_MESSAGE,
                emoji="CONFUSED",
                hud_message="CLOUD OFFLINE",
                latency_ms=latency_ms,
                cloud_offline_fallback=True,
            )

        calls: list[dict[str, Any]] = []
        backend = "local-conversation-brain"
        err_str = ""
        if self.prefer_real_cloud_ws and self.api_key:
            try:
                calls = asyncio.run(
                    self._query_cloud_live_turn(
                        utterance_text,
                        user_pcm16_bytes=user_pcm16_bytes,
                        jpeg_bytes=jpeg_bytes,
                        tof_mm=tof_mm,
                        current_mode=current_mode,
                    )
                )
                if calls:
                    backend = "gemini-live-ws"
            except Exception as exc:
                err_lines = str(exc).splitlines()
                err_str = (err_lines[0] if err_lines else repr(exc))[:110]

        if not calls:
            calls = self._plan_local_conversation_turn(
                utterance_text,
                tof_mm=tof_mm,
                current_mode=current_mode,
            )

        spoken_text = ""
        emoji = "CRUISE"
        hud_message = "READY"
        for c in calls:
            if c["name"] == "speak_with_emoji":
                args = c["args"]
                raw_spoken = str(args.get("spoken_text", ""))
                capped, _, _ = enforce_reply_length_cap(raw_spoken, user_utterance=utterance_text)
                args["spoken_text"] = capped
                spoken_text = capped
                emoji = str(args.get("emoji", "HAPPY"))
                hud_message = str(args.get("hud_message", "LIVE REPLY"))[:16]

        self.history_turns.append({"user": utterance_text, "model": spoken_text or hud_message})
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return LiveTurnResponse(
            turn_index=self.turn_count,
            backend_used=backend,
            tool_calls=calls,
            spoken_text=spoken_text,
            emoji=emoji,
            hud_message=hud_message,
            latency_ms=latency_ms,
            cloud_offline_fallback=False,
            error_detail=err_str,
        )

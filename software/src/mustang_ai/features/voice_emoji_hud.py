"""Function 1 (`voice_emoji_hud.py`): Voice conversation (`LocalPiperTTS`), Half-Duplex Echo Guard,
`>= 0.55` RMS Barge-In, and 12-Emoji `GC9A01` Rear Window HUD controller (`v3.2.0`).
"""

from __future__ import annotations

import time
from typing import Any

from mustang_ai.config import ALLOWED_EMOJIS, RadxaPinConfig
from mustang_ai.protocol.hal_contracts import (
    AudioStreamProtocol,
    DisplayHUDProtocol,
    TTSProtocol,
)
from mustang_ai.protocol.messages import (
    AudioChunkMetrics,
    CompiledActuatorCommand,
    HUDFrameState,
    ToFReading,
)


class VoiceEmojiHUDController:
    """Orchestrates `LocalPiperTTS` speech playback, half-duplex mic guard, barge-in, and the 12-Emoji `GC9A01` HUD."""

    def __init__(
        self,
        audio: AudioStreamProtocol,
        tts: TTSProtocol,
        display: DisplayHUDProtocol,
        pins: RadxaPinConfig | None = None,
    ) -> None:
        self.audio = audio
        self.tts = tts
        self.display = display
        self.pins = pins or RadxaPinConfig()
        self.current_emoji: str = "CRUISE"
        self.current_caption: str = "CRUISE READY"
        self.last_voice_rms: float = 0.0
        self.last_tts_latency_ms: float = 0.0
        self.last_spoken_text: str = ""
        self.barge_in_count: int = 0

    def speak_with_emoji(
        self,
        emoji: str,
        hud_message: str,
        spoken_text: str = "",
    ) -> dict[str, Any]:
        """Handle `speak_with_emoji` tool call from `gemini-robotics-er-2-streaming`."""
        clean_emoji = (emoji or "CRUISE").strip().upper()
        if clean_emoji not in ALLOWED_EMOJIS:
            clean_emoji = "CRUISE"
        clean_caption = (hud_message or clean_emoji).strip().upper()[:16]
        self.current_emoji = clean_emoji
        self.current_caption = clean_caption

        pcm_bytes = b""
        synth_ms = 0.0
        rms = 0.0
        if spoken_text and spoken_text.strip():
            self.last_spoken_text = spoken_text.strip()
            pcm_bytes, synth_ms = self.tts.synthesize_to_pcm16(self.last_spoken_text)
            rms = self.audio.play_pcm16_async(pcm_bytes)
            self.last_tts_latency_ms = synth_ms
            self.last_voice_rms = rms

        return {
            "emoji": self.current_emoji,
            "hud_message": self.current_caption,
            "spoken_text": self.last_spoken_text,
            "pcm_bytes": len(pcm_bytes),
            "synthesis_latency_ms": round(synth_ms, 3),
            "voice_rms": round(rms, 4),
            "half_duplex_guard_active": self.audio.is_playing(),
        }

    def poll_mic_with_barge_in(self) -> AudioChunkMetrics:
        """Capture one `40 ms` mic chunk; if `barge_in_triggered` is True, update HUD to `ALERT_STOP`."""
        chunk = self.audio.read_mic_chunk()
        if chunk.barge_in_triggered:
            self.barge_in_count += 1
            self.current_emoji = "ALERT_STOP"
            self.current_caption = "VOICE BARGE-IN"
            self.last_voice_rms = chunk.rms_level
        elif not self.audio.is_playing():
            self.last_voice_rms = chunk.rms_level
        return chunk

    def update_hud(
        self,
        tof: ToFReading,
        actuator_cmd: CompiledActuatorCommand,
        override_emoji: str | None = None,
        override_caption: str | None = None,
    ) -> HUDFrameState:
        """Compose and push the `15 Hz` `240×240` `RGB565` frame to the `GC9A01` rear window HUD."""
        emoji = (override_emoji or self.current_emoji).strip().upper()
        if emoji not in ALLOWED_EMOJIS:
            emoji = "CRUISE"
        caption = (override_caption or self.current_caption).strip().upper()[:16]

        alert_override = False
        if actuator_cmd.watchdog_tripped:
            emoji = "ALERT_STOP"
            caption = "WATCHDOG BRAKE"
            alert_override = True
        elif not tof.valid:
            emoji = "ALERT_STOP"
            caption = "TOF FAULT STOP"
            alert_override = True
        elif tof.distance_mm < self.pins.emergency_stop_mm:
            emoji = "ALERT_STOP"
            caption = f"BRAKE {tof.distance_mm}MM"
            alert_override = True

        state = HUDFrameState(
            timestamp_s=time.monotonic(),
            emoji=emoji,
            caption=caption[:16],
            tof_mm=tof.distance_mm,
            steering_deg=actuator_cmd.applied_steering_deg,
            throttle=actuator_cmd.applied_throttle,
            voice_rms=self.last_voice_rms,
            alert_override=alert_override,
        )
        self.display.render_and_push(state)
        return state

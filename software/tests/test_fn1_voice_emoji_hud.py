"""Verify FN-1: Voice Conversation, LocalPiperTTS, Half-Duplex Mute, Barge-In, and 12 GC9A01 Emojis."""

from __future__ import annotations

from pathlib import Path

from mustang_ai.config import CORE_12_EMOJIS, RadxaPinConfig
from mustang_ai.features.voice_emoji_hud import VoiceEmojiHUDController
from mustang_ai.hal.audio_i2s import SimAudioStream
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.tts_piper import SimPiperTTS
from mustang_ai.protocol.messages import CompiledActuatorCommand, HUDFrameState, ToFReading


def test_all_12_gc9a01_emojis_render_and_export_contact_sheet(
    tmp_path: Path,
    sim_display: SimGC9A01Display,
) -> None:
    assert len(CORE_12_EMOJIS) == 12
    for idx, (emoji_name, caption) in enumerate(CORE_12_EMOJIS):
        state = HUDFrameState(
            timestamp_s=1.0 + idx * 0.1,
            emoji=emoji_name,
            caption=caption,
            tof_mm=700 - idx * 40,
            steering_deg=float((idx % 3 - 1) * 6),
            throttle=0.30,
            voice_rms=0.40,
        )
        byte_count = sim_display.render_and_push(state)
        assert byte_count == 240 * 240 * 2
        assert len(sim_display.last_rgb565_bytes) == 240 * 240 * 2

    sheet_file = tmp_path / "emoji_sheet.png"
    out = sim_display.render_emoji_contact_sheet(sheet_file)
    assert out.exists()
    assert out.stat().st_size > 10_000


def test_unknown_emoji_falls_back_cleanly(
    pins: RadxaPinConfig,
    sim_display: SimGC9A01Display,
    sim_tts: SimPiperTTS,
    sim_audio: SimAudioStream,
) -> None:
    ctrl = VoiceEmojiHUDController(audio=sim_audio, tts=sim_tts, display=sim_display, pins=pins)
    res = ctrl.speak_with_emoji(emoji="non_existent_emoji_xyz", hud_message="Fallback", spoken_text="")
    assert res["emoji"] == "CRUISE"


def test_voice_hud_controller_tts_half_duplex_and_barge_in(
    pins: RadxaPinConfig,
    sim_display: SimGC9A01Display,
    sim_tts: SimPiperTTS,
    sim_audio: SimAudioStream,
) -> None:
    ctrl = VoiceEmojiHUDController(audio=sim_audio, tts=sim_tts, display=sim_display, pins=pins)
    res = ctrl.speak_with_emoji(
        emoji="ANGRY_REV",
        hud_message="289 V8 ROAR!",
        spoken_text="Punching the twenty-eighty-nine V8 right now!",
    )
    assert res["emoji"] == "ANGRY_REV"
    assert res["pcm_bytes"] > 1000
    assert res["half_duplex_guard_active"] is True

    # Normal ambient mic input during playback is muted by the half-duplex echo guard
    sim_audio.set_mic_amplitude(1800.0)
    quiet_chunk = ctrl.poll_mic_with_barge_in()
    assert quiet_chunk.muted_by_echo_guard is True
    assert quiet_chunk.barge_in_triggered is False

    # Loud user shout ("Stop!") exceeds >= 0.55 RMS -> triggers barge-in and stops playback
    sim_audio.set_mic_amplitude(24000.0)
    loud_chunk = ctrl.poll_mic_with_barge_in()
    assert loud_chunk.barge_in_triggered is True
    assert sim_audio.is_playing() is False
    assert ctrl.current_emoji == "ALERT_STOP"

    tof = ToFReading(timestamp_s=1.0, distance_mm=640, valid=True, zone="CLEAR")
    cmd = CompiledActuatorCommand(
        timestamp_s=1.0,
        applied_throttle=0.0,
        applied_steering_deg=0.0,
        motor_in1_duty=0.0,
        motor_in2_duty=0.0,
        servo_pulse_us=1500,
        emergency_brake=False,
        watchdog_tripped=False,
    )
    hud_state = ctrl.update_hud(tof=tof, actuator_cmd=cmd)
    assert hud_state.emoji == "ALERT_STOP"

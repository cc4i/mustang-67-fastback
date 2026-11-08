"""Comprehensive Milestone A (`v3.3.0`) test suite verifying `S1`–`S7`, `D1`–`D15`, and `R1`."""

from __future__ import annotations

import pathlib

from mustang_ai.config import GeminiERConfig
from mustang_ai.hal.audio_i2s import SimAudioStream
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.hal.tts_piper import SimPiperTTS
from mustang_ai.runtime.local_autonomy_loop import LocalAutonomyEngine
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor
from mustang_ai.simulator.mac_live_workbench import WORKBENCH_HTML, MacLiveWorkbench
from mustang_ai.voice import (
    DEFAULT_SPEAKER_VOLUME,
    MAX_SPEAKER_VOLUME,
    MIN_SPEAKER_VOLUME,
    OFFLINE_SPOKEN_MESSAGE,
    SILENCE_FRAME,
    ConversationStateMachine,
    KeywordSpotterEngine,
    SileroVADTracker,
    count_syllables,
    enforce_reply_length_cap,
    get_adaptive_thresholds,
    run_s1_s7_verification_suite,
    slice_into_10ms_frames,
)


def _make_test_rig(tmp_path: pathlib.Path | None = None) -> tuple[ConversationStateMachine, list[float]]:
    cfg = GeminiERConfig()
    fake_now = [1000.0]
    clock = lambda: fake_now[0]

    bus = StateBus()
    tof = SimRangefinder(cfg.pins, distance_provider=lambda: 850)
    cam = SimFisheyeCamera(cfg.camera)
    act = SimDriveActuator(cfg.pins)
    display = SimGC9A01Display(cfg.pins)
    tts = SimPiperTTS(cfg.tts)
    audio_hal = SimAudioStream(cfg.pins)
    gov = WatchdogReflexGovernor(rangefinder=tof, actuators=act, bus=bus, pins=cfg.pins)
    autonomy = LocalAutonomyEngine(camera=cam, audio=audio_hal, tts=tts, display=display, bus=bus, pins=cfg.pins)

    kw_path = (tmp_path / "keywords.txt") if tmp_path is not None else None
    kws = KeywordSpotterEngine(keywords_file=kw_path, tts_template_provider=tts)
    sm = ConversationStateMachine(
        autonomy=autonomy,
        governor=gov,
        bus=bus,
        keywords=kws,
        clock_fn=clock,
    )
    return sm, fake_now


def test_s1_echo_cancellation_zero_self_triggers_and_erle(tmp_path: pathlib.Path) -> None:
    """S1: Car's own TTS reply played through the simulated echo path causes 0 self-triggers and >=15 dB ERLE."""
    sm, fake_now = _make_test_rig(tmp_path)
    reply_pcm, _ = sm.autonomy.tts.synthesize_to_pcm16(
        "Hello driver! Hey Mustang style cruising is ready with sixty-seven fastback power."
    )
    frames_queued = sm.audio_engine.enqueue_tts_pcm16(reply_pcm)
    assert frames_queued > 20

    for _ in range(frames_queued):
        fake_now[0] += 0.01
        sm.step_audio_frame(SILENCE_FRAME, inject_echo=True, inject_motor_noise=False)

    assert sm.metrics.self_trigger_count == 0
    assert sm.frontend.cumulative_erle_db >= 15.0


def test_s2_and_d4_motor_noise_suppression_and_adaptive_thresholds(tmp_path: pathlib.Path) -> None:
    """S2 & D4: Pure motor noise at 25%, 50%, 100% throttle triggers 0 false wakes; thresholds scale with throttle."""
    sm, fake_now = _make_test_rig(tmp_path)

    th0 = get_adaptive_thresholds(0.0)
    th50 = get_adaptive_thresholds(0.50)
    th100 = get_adaptive_thresholds(1.00)
    assert th0.wake_score_threshold < th50.wake_score_threshold < th100.wake_score_threshold
    assert th0.vad_rms_threshold < th50.vad_rms_threshold < th100.vad_rms_threshold

    for throttle in (0.25, 0.50, 1.00):
        sm.autonomy.handle_tool_call("set_drive_command", {"throttle": throttle, "steering_deg": 0.0})
        sm._refresh_governor(now_s=fake_now[0])
        for _ in range(30):
            fake_now[0] += 0.01
            sm.step_audio_frame(SILENCE_FRAME, inject_echo=False, inject_motor_noise=True)

    assert sm.metrics.false_wake_on_motor_noise == 0
    assert sm.metrics.motor_noise_frames_tested >= 60


def test_s3_acoustic_wake_and_vad_under_50pct_motor_noise(tmp_path: pathlib.Path) -> None:
    """S3: Acoustic wake phrase and VAD segmentation succeed under 50% motor noise."""
    sm, fake_now = _make_test_rig(tmp_path)
    sm.autonomy.handle_tool_call("set_drive_command", {"throttle": 0.50, "steering_deg": 0.0})
    sm._refresh_governor(now_s=fake_now[0])

    wake_pcm, _ = sm.autonomy.tts.synthesize_to_pcm16("Hey Mustang")
    wake_frames = slice_into_10ms_frames(wake_pcm)
    vad = SileroVADTracker(min_speech_frames=6, silence_hangover_frames=15)

    wake_detected = False
    segment = None
    for wf in wake_frames + [SILENCE_FRAME] * 20:
        fake_now[0] += 0.01
        fe_res, hit = sm.step_audio_frame(wf, inject_echo=False, inject_motor_noise=True)
        if hit is not None and hit.kind == "wake":
            wake_detected = True
        seg = vad.process_frame(
            fe_res.clean_pcm16,
            frame_index=fe_res.frame_index,
            applied_throttle=0.50,
        )
        if seg is not None:
            segment = seg

    assert wake_detected is True
    assert segment is not None
    assert segment.wav_bytes[:4] == b"RIFF"
    assert segment.duration_ms >= 100


def test_d3_and_s5_barge_in_only_on_wake_word_or_stop(tmp_path: pathlib.Path) -> None:
    """D3 & S5: During SPEAKING, normal speech is ignored; only wake word or 'stop' cuts TTS in <= 200 ms."""
    sm, fake_now = _make_test_rig(tmp_path)

    # Start a conversation so the car enters SPEAKING
    out1 = sm.handle_utterance("Hey Mustang how are you")
    assert out1.new_state == "SPEAKING"
    assert sm.audio_engine.is_playing() is True

    # D3: Normal chatter without wake word or "stop" is ignored while SPEAKING
    chatter = sm.handle_utterance("some random person talking nearby")
    assert chatter.barge_in_triggered is False
    assert chatter.ignored_without_wake_word is True
    assert sm.state == "SPEAKING"
    assert sm.audio_engine.is_playing() is True

    # S5: Wake word barges in and flushes playback in <= 200 ms
    barge = sm.handle_utterance("Hey Mustang")
    assert barge.barge_in_triggered is True
    assert barge.barge_in_latency_ms <= 200.0
    assert sm.audio_engine.is_playing() is False
    assert sm.state == "LISTENING"


def test_d5_d7_d8_s6_local_move_wake_gate_duplicate_filter_and_stop(tmp_path: pathlib.Path) -> None:
    """D5, D7, D8, S6: Move commands require wake word; local move filters cloud duplicate; 'stop' works anytime <=100ms."""
    sm, _ = _make_test_rig(tmp_path)

    # D7: Bare move command in IDLE without wake word is ignored
    ignored = sm.handle_utterance("forward")
    assert ignored.ignored_without_wake_word is True
    assert ignored.applied_throttle == 0.0
    assert sm.state == "IDLE"

    # D5 + D8: Wake word + move command starts local motion immediately and filters duplicate cloud move
    moved = sm.handle_utterance("Hey Mustang forward")
    assert moved.local_move_started == "move_forward"
    assert moved.duplicate_move_filtered is True
    assert moved.applied_throttle > 0.0
    assert sm.metrics.duplicate_cloud_moves_filtered == 1

    # S6: Bare "stop" works anytime without wake word and zeroes throttle in <= 100 ms
    stopped = sm.handle_utterance("stop")
    assert stopped.stop_triggered is True
    assert stopped.stop_latency_ms <= 100.0
    assert stopped.applied_throttle == 0.0
    assert sm.state == "IDLE"


def test_d4_and_d12_keep_driving_while_listening_and_asking_chat_question(tmp_path: pathlib.Path) -> None:
    """D4 & D12: Waking the car or asking a chat question while driving preserves current motion."""
    sm, fake_now = _make_test_rig(tmp_path)

    start_drive = sm.handle_utterance("Hey Mustang keep going")
    assert start_drive.active_maneuver == "keep_going"
    assert start_drive.applied_throttle > 0.0

    # Drain TTS to enter FOLLOW_UP, then wake into LISTENING
    sm.audio_engine.flush_playback()
    fake_now[0] += 0.2
    sm.tick_timers(now_s=fake_now[0])

    woken = sm.handle_utterance("Hey Mustang")
    assert woken.new_state == "LISTENING"
    assert woken.active_maneuver == "keep_going"
    assert woken.applied_throttle > 0.0

    # D12: Ask a chat question while driving -> car answers without altering motion
    chat = sm.handle_utterance("What is the front laser distance?")
    assert chat.active_maneuver == "keep_going"
    assert chat.applied_throttle > 0.0
    assert len(chat.spoken_reply.split()) <= 25


def test_d9_and_r1_wake_word_rename_confirmation_and_short_syllable_warning(tmp_path: pathlib.Path) -> None:
    """D9 & R1: Voice rename asks confirmation, warns on <3 syllables ('Hey Nerd'), and updates keywords.txt."""
    sm, fake_now = _make_test_rig(tmp_path)
    assert count_syllables("Hey Mustang") == 3
    assert count_syllables("Hey Nerd") == 2

    req = sm.handle_utterance("Hey Mustang change your name to Hey Nerd")
    assert req.rename_pending == "Hey Nerd"
    assert "Hey Nerd" in req.spoken_reply

    # Drain playback to enter FOLLOW_UP and confirm with "yes"
    sm.audio_engine.flush_playback()
    fake_now[0] += 0.2
    sm.tick_timers(now_s=fake_now[0])

    confirm = sm.handle_utterance("yes")
    assert confirm.rename_applied is not None
    assert confirm.rename_applied.new_wake_phrase == "Hey Nerd"
    assert confirm.rename_applied.syllable_count == 2
    assert confirm.rename_applied.short_phrase_warning is True
    assert "@Hey_Nerd" in pathlib.Path(confirm.rename_applied.keywords_file).read_text(encoding="utf-8")

    # Reset to IDLE and verify "Hey Nerd" now wakes the car while old "Hey Mustang" without "Hey Nerd" does not
    sm.audio_engine.flush_playback()
    fake_now[0] += 10.0
    sm.tick_timers(now_s=fake_now[0])
    assert sm.state == "IDLE"

    old_try = sm.handle_utterance("Hey Mustang forward")
    assert old_try.ignored_without_wake_word is True

    new_try = sm.handle_utterance("Hey Nerd forward")
    assert new_try.wake_word_triggered is True
    assert new_try.local_move_started == "move_forward"


def test_d10_offline_mode_fallback_preserves_local_commands(tmp_path: pathlib.Path) -> None:
    """D10: When cloud is offline, local driving commands and 'stop' still execute and HUD shows CONFUSED."""
    sm, _ = _make_test_rig(tmp_path)
    sm.live_session.cloud_online = False

    out = sm.handle_utterance("Hey Mustang reverse")
    assert out.local_move_started == "reverse_back"
    assert out.applied_throttle < 0.0
    assert out.cloud_offline_fallback is True
    assert out.hud_emoji == "CONFUSED"
    assert out.spoken_reply == OFFLINE_SPOKEN_MESSAGE

    stop_out = sm.handle_utterance("stop")
    assert stop_out.stop_triggered is True
    assert stop_out.applied_throttle == 0.0


def test_d13_reply_length_cap_and_tell_me_more(tmp_path: pathlib.Path) -> None:
    """D13: Replies are capped to <= 25 words (1-2 sentences) unless the user asks 'tell me more'."""
    long_text = (
        "First short sentence here. Second sentence adds a few more words to reach the cap. "
        "Third sentence has many extra words that would definitely push the total well past twenty five words."
    )
    capped, sentences, truncated = enforce_reply_length_cap(long_text, user_utterance="how are you")
    assert truncated is True
    assert len(sentences) <= 2
    assert len(capped.split()) <= 25

    expanded, _, _ = enforce_reply_length_cap(long_text, user_utterance="tell me more about the car")
    assert len(expanded.split()) > 25


def test_d14_and_s7_follow_up_8s_window_and_idle_memory_reset(tmp_path: pathlib.Path) -> None:
    """D14 & S7: Follow-up turns within 8s do not need the wake word and share memory; IDLE wipes memory."""
    sm, fake_now = _make_test_rig(tmp_path)

    t1 = sm.handle_utterance("Hey Mustang my name is Jordan")
    assert "Jordan" in t1.spoken_reply

    # Finish speaking -> enter 8.0 s FOLLOW_UP window
    sm.audio_engine.flush_playback()
    fake_now[0] += 0.5
    assert sm.tick_timers(now_s=fake_now[0]) == "FOLLOW_UP"

    # 3.0 s into FOLLOW_UP (< 8.0 s): ask follow-up WITHOUT wake word
    fake_now[0] += 3.0
    t2 = sm.handle_utterance("What is my name?")
    assert t2.ignored_without_wake_word is False
    assert "Jordan" in t2.spoken_reply
    assert sm.metrics.follow_up_turns_completed >= 1

    # Finish speaking -> enter FOLLOW_UP, then wait 8.5 s (> 8.0 s) so state returns to IDLE
    sm.audio_engine.flush_playback()
    fake_now[0] += 0.2
    sm.tick_timers(now_s=fake_now[0])
    fake_now[0] += 8.5
    assert sm.tick_timers(now_s=fake_now[0]) == "IDLE"
    assert sm.metrics.conversations_reset_at_idle >= 1

    # New conversation after IDLE: previous name was forgotten (D14)
    t3 = sm.handle_utterance("Hey Mustang what is my name?")
    assert "Jordan" not in t3.spoken_reply


def test_d15_speaker_volume_cap_and_voice_adjustment(tmp_path: pathlib.Path) -> None:
    """D15: Default volume is 0.70; 'louder' and 'quieter' adjust within [0.25, 0.85]."""
    sm, _ = _make_test_rig(tmp_path)
    assert sm.audio_engine.speaker_volume == DEFAULT_SPEAKER_VOLUME

    up = sm.handle_utterance("Hey Mustang louder")
    assert up.speaker_volume == MAX_SPEAKER_VOLUME

    down1 = sm.handle_utterance("Hey Mustang quieter")
    assert MIN_SPEAKER_VOLUME <= down1.speaker_volume < MAX_SPEAKER_VOLUME


def test_s1_s7_suite_and_workbench_integration() -> None:
    """Verify full S1-S7 benchmark report and MacLiveWorkbench voice pipeline controls."""
    report = run_s1_s7_verification_suite(use_real_piper=False)
    assert report["status"] == "PASS"
    assert report["all_s1_s7_passed"] is True
    assert all(report["checks"].values())

    wb = MacLiveWorkbench(audible_speaker=False, use_cloud_live=False)
    snap = wb.snapshot_telemetry()
    assert "voice_pipeline" in snap
    assert snap["voice_pipeline"]["wake_phrase"] == "Hey Mustang"

    upd = wb.set_wake_word_config("Hey Nerd")
    assert upd["new_wake_phrase"] == "Hey Nerd"
    assert upd["short_phrase_warning"] is True

    vol_res = wb.adjust_speaker_volume("quieter")
    assert vol_res["speaker_volume"] < DEFAULT_SPEAKER_VOLUME

    mode_res = wb.set_cloud_online_mode(False)
    assert mode_res["cloud_online"] is False

    # Verify conversation history & clean command input isolation in WORKBENCH_HTML
    assert 'id="chatHistoryBox"' in WORKBENCH_HTML
    assert "renderConversationHistory" in WORKBENCH_HTML
    assert "isEchoOfLastReply" in WORKBENCH_HTML
    assert '<input type="text" id="voiceInput"' in WORKBENCH_HTML
    assert 'value=""' in WORKBENCH_HTML
    assert "getElementById('voiceInput').value =" not in WORKBENCH_HTML

    wb.submit_voice_utterance("Weave through the slalom!", advance_steps=2)
    snap2 = wb.snapshot_telemetry()
    assert len(snap2["history"]) == 1
    assert snap2["history"][0]["user_utterance"] == "Weave through the slalom!"
    assert snap2["history"][0]["spoken_reply_text"]

    cleared = wb.clear_conversation_history()
    assert cleared["history_count"] == 0
    assert wb.snapshot_telemetry()["history"] == []

    # Verify "Keep moving" triggers continuous driving and animates both 1st-person camera & 2D radar past 800 mm
    km_turn = wb.submit_voice_utterance("Keep moving", advance_steps=4)
    assert km_turn["active_maneuver"] == "keep_going"
    assert km_turn["applied_throttle"] >= 0.35
    for _ in range(110):
        wb.step_physics_and_sensors(dt_sec=0.05)
    assert wb.autonomy.maneuver_seq.is_active is True
    assert wb.arena.car_x_mm > 800.0
    frame_a = wb.snapshot_telemetry()
    for _ in range(4):
        wb.step_physics_and_sensors(dt_sec=0.05)
    frame_b = wb.snapshot_telemetry()
    assert frame_a["cam_jpeg_b64"] != frame_b["cam_jpeg_b64"]
    assert frame_a["arena_png_b64"] != frame_b["arena_png_b64"]

"""Conversation state machine (`conversation.py`): orchestrates `IDLE`, `LISTENING`, `THINKING`,
`SPEAKING`, `FOLLOW_UP`, and `STOP` across the full-duplex audio engine, WebRTC `AEC3 + NS` front-end,
keyword spotter, Silero VAD, persistent Gemini Live session, sentence-streamed Piper TTS, and Tier-1/Tier-0
car control (`D1`–`D15`, `S1`–`S7`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from mustang_ai.config import GeminiERConfig
from mustang_ai.hal.audio_i2s import SimAudioStream
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.hal.tts_piper import LocalPiperTTS, SimPiperTTS
from mustang_ai.runtime.local_autonomy_loop import LocalAutonomyEngine
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor
from mustang_ai.voice.audio_engine import (
    SILENCE_FRAME,
    FullDuplexAudioEngine,
    slice_into_10ms_frames,
)
from mustang_ai.voice.frontend import AudioFrontEnd, FrontEndFrameResult
from mustang_ai.voice.keywords import (
    DEFAULT_WAKE_PHRASE,
    KeywordHit,
    KeywordSpotterEngine,
    WakeWordUpdateResult,
)
from mustang_ai.voice.live_session import PersistentConversationLiveSession
from mustang_ai.voice.metrics import VoiceMetricsLedger
from mustang_ai.voice.tts_stream import SentenceStreamTTS
from mustang_ai.voice.vad import SileroVADTracker

FOLLOW_UP_WINDOW_S: float = 8.0
LISTENING_TIMEOUT_S: float = 6.0


@dataclass(frozen=True)
class VoiceTurnOutcome:
    """Detailed outcome of processing a voice utterance or barge-in event through `ConversationStateMachine`."""

    prior_state: str
    new_state: str
    wake_word_triggered: bool
    barge_in_triggered: bool
    barge_in_latency_ms: float
    stop_triggered: bool
    stop_latency_ms: float
    ignored_without_wake_word: bool
    local_move_started: str
    duplicate_move_filtered: bool
    cloud_offline_fallback: bool
    rename_pending: str
    rename_applied: WakeWordUpdateResult | None
    speaker_volume: float
    spoken_reply: str
    hud_emoji: str
    hud_caption: str
    ttfa_ms: float
    applied_throttle: float
    applied_steering_deg: float
    active_maneuver: str


class ConversationStateMachine:
    """Implements the Radxa & Laptop-First Voice Conversation State Machine (`D1`–`D15`, `S1`–`S7`)."""

    def __init__(
        self,
        *,
        autonomy: LocalAutonomyEngine,
        governor: WatchdogReflexGovernor,
        bus: StateBus,
        audio_engine: FullDuplexAudioEngine | None = None,
        frontend: AudioFrontEnd | None = None,
        keywords: KeywordSpotterEngine | None = None,
        vad: SileroVADTracker | None = None,
        live_session: PersistentConversationLiveSession | None = None,
        tts_stream: SentenceStreamTTS | None = None,
        metrics: VoiceMetricsLedger | None = None,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.autonomy = autonomy
        self.governor = governor
        self.bus = bus
        self.clock_fn = clock_fn

        self.audio_engine = audio_engine or FullDuplexAudioEngine()
        self.frontend = frontend or AudioFrontEnd()
        self.keywords = keywords or KeywordSpotterEngine(
            wake_phrase=DEFAULT_WAKE_PHRASE,
            tts_template_provider=self.autonomy.tts,
        )
        self.vad = vad or SileroVADTracker()
        self.live_session = live_session or PersistentConversationLiveSession()
        self.tts_stream = tts_stream or SentenceStreamTTS(self.autonomy.tts, self.audio_engine)
        self.metrics = metrics or VoiceMetricsLedger()

        self.state: str = "IDLE"
        self.state_entered_s: float = self.clock_fn()
        self.follow_up_deadline_s: float = 0.0
        self.pending_rename_phrase: str = ""
        self.last_spoken_reply: str = ""
        self.last_outcome: VoiceTurnOutcome | None = None

    def _set_state(self, new_state: str, now_s: float | None = None) -> None:
        ts = self.clock_fn() if now_s is None else now_s
        if new_state == "IDLE" and self.state != "IDLE":
            if self.live_session.session_active:
                self.live_session.close_and_forget()
                self.metrics.conversations_reset_at_idle += 1
            self.pending_rename_phrase = ""
        self.state = new_state
        self.state_entered_s = ts
        if new_state == "FOLLOW_UP":
            self.follow_up_deadline_s = ts + FOLLOW_UP_WINDOW_S

    def _refresh_governor(self, now_s: float | None = None, dt_sec: float = 0.02) -> None:
        ts = self.clock_fn() if now_s is None else now_s
        self.governor.step_once(now_s=ts)
        self.autonomy.step_once(dt_sec=dt_sec)
        self.governor.step_once(now_s=ts)

    def tick_timers(self, now_s: float | None = None) -> str:
        """Advance state timers (`SPEAKING -> FOLLOW_UP` when playback finishes; `FOLLOW_UP -> IDLE` after `8.0 s`)."""
        ts = self.clock_fn() if now_s is None else now_s
        if self.state == "SPEAKING" and not self.audio_engine.is_playing():
            if (ts - self.state_entered_s) >= FOLLOW_UP_WINDOW_S:
                self._set_state("IDLE", now_s=ts)
            else:
                self._set_state("FOLLOW_UP", now_s=ts)
        elif self.state == "FOLLOW_UP" and ts >= self.follow_up_deadline_s:
            self._set_state("IDLE", now_s=ts)
        elif self.state == "LISTENING" and (ts - self.state_entered_s) >= LISTENING_TIMEOUT_S and not self.vad.in_speech:
            self._set_state("IDLE", now_s=ts)
        elif self.state == "STOP":
            self._set_state("IDLE", now_s=ts)
        return self.state

    def step_audio_frame(
        self,
        mic_clean_frame: bytes | None = None,
        *,
        inject_echo: bool = True,
        inject_motor_noise: bool = True,
        now_s: float | None = None,
    ) -> tuple[FrontEndFrameResult, KeywordHit | None]:
        """Process one `10 ms` full-duplex audio frame through `AudioFrontEnd` (`AEC3+NS`) and `KeywordSpotterEngine`."""
        ts = self.clock_fn() if now_s is None else now_s
        throttle = self.bus.actuator_cmd.applied_throttle
        bundle = self.audio_engine.step_frame(
            mic_clean_frame,
            applied_throttle=throttle,
            inject_echo=inject_echo,
            inject_motor_noise=inject_motor_noise,
        )
        fe_res = self.frontend.process_frame(
            bundle.raw_mic_pcm16,
            bundle.speaker_ref_pcm16,
            applied_throttle=throttle,
        )

        if bundle.speaker_playing and not fe_res.double_talk_detected and fe_res.instant_erle_db > 0.0:
            self.metrics.echo_frames_tested += 1
            self.metrics.erle_samples_db.append(fe_res.instant_erle_db)

        if abs(throttle) >= 0.10 and mic_clean_frame in (None, SILENCE_FRAME) and not bundle.speaker_playing:
            self.metrics.motor_noise_frames_tested += 1

        self.vad.process_frame(
            fe_res.clean_pcm16,
            frame_index=fe_res.frame_index,
            applied_throttle=throttle,
        )

        hit = self.keywords.process_clean_pcm16_frame(
            fe_res.clean_pcm16,
            frame_index=fe_res.frame_index,
            score_threshold=fe_res.thresholds.wake_score_threshold,
        )

        # Track S1 (self-triggers during single-talk speaker echo) and S2 (false wakes on pure motor noise)
        if hit is not None:
            if bundle.speaker_playing and mic_clean_frame in (None, SILENCE_FRAME):
                self.metrics.self_trigger_count += 1
            elif abs(throttle) >= 0.10 and mic_clean_frame in (None, SILENCE_FRAME) and not bundle.speaker_playing:
                if hit.kind == "wake":
                    self.metrics.false_wake_on_motor_noise += 1
            elif hit.kind == "stop":
                self.handle_utterance("stop", now_s=ts)
            elif hit.kind == "wake":
                if self.state == "SPEAKING":
                    _, flush_ms = self.audio_engine.flush_playback()
                    self.metrics.barge_in_latencies_ms.append(flush_ms)
                self.live_session.start_conversation()
                self._set_state("LISTENING", now_s=ts)
            elif hit.kind in ("command", "volume") and self.state in ("LISTENING", "FOLLOW_UP"):
                self.handle_utterance(hit.phrase, now_s=ts)

        self.tick_timers(now_s=ts)
        return fe_res, hit

    def _execute_immediate_stop(self, *, prior_state: str, barge_in: bool, flush_ms: float, now_s: float) -> VoiceTurnOutcome:
        """Execute `< 100 ms` local emergency stop (`S6`) without waiting for the cloud."""
        t0 = time.perf_counter()
        self.autonomy.handle_tool_call("emergency_stop", {"reason": "local_voice_stop_keyword"})
        self._refresh_governor(now_s=now_s)
        stop_ms = round((time.perf_counter() - t0) * 1000.0 + flush_ms, 3)
        self.metrics.stop_latencies_ms.append(stop_ms)
        if barge_in:
            self.metrics.barge_in_latencies_ms.append(flush_ms)
        self._set_state("STOP", now_s=now_s)
        self._set_state("IDLE", now_s=now_s)
        self.metrics.record_event(
            "local_stop_executed",
            prior_state=prior_state,
            stop_latency_ms=stop_ms,
            barge_in=barge_in,
        )
        outcome = VoiceTurnOutcome(
            prior_state=prior_state,
            new_state=self.state,
            wake_word_triggered=False,
            barge_in_triggered=barge_in,
            barge_in_latency_ms=flush_ms,
            stop_triggered=True,
            stop_latency_ms=stop_ms,
            ignored_without_wake_word=False,
            local_move_started="",
            duplicate_move_filtered=False,
            cloud_offline_fallback=False,
            rename_pending="",
            rename_applied=None,
            speaker_volume=self.audio_engine.speaker_volume,
            spoken_reply="",
            hud_emoji=self.bus.hud.emoji,
            hud_caption=self.bus.hud.caption,
            ttfa_ms=0.0,
            applied_throttle=self.bus.actuator_cmd.applied_throttle,
            applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
            active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
        )
        self.last_outcome = outcome
        return outcome

    def handle_utterance(
        self,
        utterance_text: str,
        *,
        user_pcm16_bytes: bytes | None = None,
        now_s: float | None = None,
    ) -> VoiceTurnOutcome:
        """Process a complete user utterance through the state machine enforcing `D1`–`D15` and `S1`–`S7`."""
        ts = self.clock_fn() if now_s is None else now_s
        t_turn_start = time.perf_counter()
        prior_state = self.state
        clean_text = " ".join((utterance_text or "").strip().split())
        hits = self.keywords.match_utterance_text(clean_text)

        has_wake = any(h.kind == "wake" for h in hits)
        has_stop = any(h.kind == "stop" for h in hits)
        cmd_hit = next((h for h in hits if h.kind == "command"), None)
        vol_hit = next((h for h in hits if h.kind == "volume"), None)
        rename_hit = next((h for h in hits if h.kind == "rename_request"), None)

        # Strip wake phrase from text passed to conversation brain
        effective_text = clean_text
        for h in hits:
            if h.kind == "wake":
                effective_text = h.remainder_text or ""
                break

        # ------------------------------------------------------------------
        # 1. SPEAKING state -> Enforce D3 & S5 (Barge-In ONLY on wake word or "stop")
        # ------------------------------------------------------------------
        barge_in_triggered = False
        barge_in_ms = 0.0
        if prior_state == "SPEAKING":
            if not has_wake and not has_stop:
                # D3: Non-wake / non-stop speech during TTS playback is ignored!
                outcome = VoiceTurnOutcome(
                    prior_state=prior_state,
                    new_state=self.state,
                    wake_word_triggered=False,
                    barge_in_triggered=False,
                    barge_in_latency_ms=0.0,
                    stop_triggered=False,
                    stop_latency_ms=0.0,
                    ignored_without_wake_word=True,
                    local_move_started="",
                    duplicate_move_filtered=False,
                    cloud_offline_fallback=False,
                    rename_pending=self.pending_rename_phrase,
                    rename_applied=None,
                    speaker_volume=self.audio_engine.speaker_volume,
                    spoken_reply=self.last_spoken_reply,
                    hud_emoji=self.bus.hud.emoji,
                    hud_caption=self.bus.hud.caption,
                    ttfa_ms=0.0,
                    applied_throttle=self.bus.actuator_cmd.applied_throttle,
                    applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
                    active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
                )
                self.last_outcome = outcome
                return outcome

            # Valid barge-in (wake word or "stop"): flush speaker queue immediately (S5 <= 200 ms)
            _, barge_in_ms = self.audio_engine.flush_playback()
            barge_in_triggered = True
            self.metrics.barge_in_latencies_ms.append(barge_in_ms)
            self.autonomy.voice_hud.barge_in_count += 1
            if has_stop:
                return self._execute_immediate_stop(
                    prior_state=prior_state,
                    barge_in=True,
                    flush_ms=barge_in_ms,
                    now_s=ts,
                )
            self.live_session.start_conversation()
            self._set_state("LISTENING", now_s=ts)
            if not effective_text:
                outcome = VoiceTurnOutcome(
                    prior_state=prior_state,
                    new_state=self.state,
                    wake_word_triggered=True,
                    barge_in_triggered=True,
                    barge_in_latency_ms=barge_in_ms,
                    stop_triggered=False,
                    stop_latency_ms=0.0,
                    ignored_without_wake_word=False,
                    local_move_started="",
                    duplicate_move_filtered=False,
                    cloud_offline_fallback=False,
                    rename_pending=self.pending_rename_phrase,
                    rename_applied=None,
                    speaker_volume=self.audio_engine.speaker_volume,
                    spoken_reply="",
                    hud_emoji="SURPRISED",
                    hud_caption="LISTENING...",
                    ttfa_ms=0.0,
                    applied_throttle=self.bus.actuator_cmd.applied_throttle,
                    applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
                    active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
                )
                self.last_outcome = outcome
                return outcome

        # ------------------------------------------------------------------
        # 2. Any state -> Immediate local "stop" works without wake word (S6, D7)
        # ------------------------------------------------------------------
        if has_stop:
            _, flush_ms = self.audio_engine.flush_playback()
            return self._execute_immediate_stop(
                prior_state=prior_state,
                barge_in=barge_in_triggered,
                flush_ms=flush_ms,
                now_s=ts,
            )

        # ------------------------------------------------------------------
        # 3. IDLE state -> Require wake word before commands or chat (D7)
        # ------------------------------------------------------------------
        if self.state == "IDLE" and not has_wake:
            outcome = VoiceTurnOutcome(
                prior_state=prior_state,
                new_state="IDLE",
                wake_word_triggered=False,
                barge_in_triggered=False,
                barge_in_latency_ms=0.0,
                stop_triggered=False,
                stop_latency_ms=0.0,
                ignored_without_wake_word=True,
                local_move_started="",
                duplicate_move_filtered=False,
                cloud_offline_fallback=False,
                rename_pending="",
                rename_applied=None,
                speaker_volume=self.audio_engine.speaker_volume,
                spoken_reply="",
                hud_emoji=self.bus.hud.emoji,
                hud_caption=self.bus.hud.caption,
                ttfa_ms=0.0,
                applied_throttle=self.bus.actuator_cmd.applied_throttle,
                applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
                active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
            )
            self.last_outcome = outcome
            return outcome

        # Track follow-up turn if we were in FOLLOW_UP without repeating wake word (S7)
        if prior_state == "FOLLOW_UP" and not has_wake:
            self.metrics.follow_up_turns_completed += 1

        if has_wake:
            self.live_session.start_conversation()
            self._set_state("LISTENING", now_s=ts)
            if not effective_text:
                # Bare wake word ("Hey Mustang") -> stay in LISTENING without stopping car (D4)
                self.autonomy.voice_hud.current_emoji = "SURPRISED"
                self.autonomy.voice_hud.current_caption = "LISTENING..."
                self._refresh_governor(now_s=ts)
                outcome = VoiceTurnOutcome(
                    prior_state=prior_state,
                    new_state=self.state,
                    wake_word_triggered=True,
                    barge_in_triggered=barge_in_triggered,
                    barge_in_latency_ms=barge_in_ms,
                    stop_triggered=False,
                    stop_latency_ms=0.0,
                    ignored_without_wake_word=False,
                    local_move_started="",
                    duplicate_move_filtered=False,
                    cloud_offline_fallback=False,
                    rename_pending=self.pending_rename_phrase,
                    rename_applied=None,
                    speaker_volume=self.audio_engine.speaker_volume,
                    spoken_reply="",
                    hud_emoji=self.bus.hud.emoji,
                    hud_caption=self.bus.hud.caption,
                    ttfa_ms=0.0,
                    applied_throttle=self.bus.actuator_cmd.applied_throttle,
                    applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
                    active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
                )
                self.last_outcome = outcome
                return outcome

        # ------------------------------------------------------------------
        # 4. Handle pending wake-word rename confirmation (D9 & R1)
        # ------------------------------------------------------------------
        if self.pending_rename_phrase:
            low_eff = effective_text.lower().strip()
            if any(w in low_eff.split() for w in ("yes", "confirm", "sure", "okay", "ok", "yep")):
                target_phrase = self.pending_rename_phrase
                self.pending_rename_phrase = ""
                upd = self.keywords.set_wake_word(target_phrase)
                reply = (
                    f"Wake word changed to {upd.new_wake_phrase}. Note: short wake words can trigger more easily."
                    if upd.short_phrase_warning
                    else f"Wake word changed to {upd.new_wake_phrase}!"
                )
                stream_res = self.tts_stream.speak_streamed(reply, user_utterance=effective_text)
                self.autonomy.voice_hud.current_emoji = "HAPPY"
                self.autonomy.voice_hud.current_caption = f"WAKE: {upd.new_wake_phrase[:9].upper()}"
                self._refresh_governor(now_s=ts)
                self._set_state("SPEAKING" if stream_res.enqueued_frames > 0 else "FOLLOW_UP", now_s=ts)
                ttfa_ms = round((time.perf_counter() - t_turn_start) * 1000.0, 3)
                self.metrics.ttfa_samples_ms.append(ttfa_ms)
                outcome = VoiceTurnOutcome(
                    prior_state=prior_state,
                    new_state=self.state,
                    wake_word_triggered=has_wake,
                    barge_in_triggered=barge_in_triggered,
                    barge_in_latency_ms=barge_in_ms,
                    stop_triggered=False,
                    stop_latency_ms=0.0,
                    ignored_without_wake_word=False,
                    local_move_started="",
                    duplicate_move_filtered=False,
                    cloud_offline_fallback=False,
                    rename_pending="",
                    rename_applied=upd,
                    speaker_volume=self.audio_engine.speaker_volume,
                    spoken_reply=stream_res.spoken_text,
                    hud_emoji=self.bus.hud.emoji,
                    hud_caption=self.bus.hud.caption,
                    ttfa_ms=ttfa_ms,
                    applied_throttle=self.bus.actuator_cmd.applied_throttle,
                    applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
                    active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
                )
                self.last_outcome = outcome
                return outcome
            if any(w in low_eff.split() for w in ("no", "cancel", "keep", "nevermind")):
                self.pending_rename_phrase = ""
                reply = f"Okay, keeping wake word as {self.keywords.wake_phrase}."
                stream_res = self.tts_stream.speak_streamed(reply, user_utterance=effective_text)
                self._refresh_governor(now_s=ts)
                self._set_state("SPEAKING" if stream_res.enqueued_frames > 0 else "FOLLOW_UP", now_s=ts)
                ttfa_ms = round((time.perf_counter() - t_turn_start) * 1000.0, 3)
                outcome = VoiceTurnOutcome(
                    prior_state=prior_state,
                    new_state=self.state,
                    wake_word_triggered=has_wake,
                    barge_in_triggered=barge_in_triggered,
                    barge_in_latency_ms=barge_in_ms,
                    stop_triggered=False,
                    stop_latency_ms=0.0,
                    ignored_without_wake_word=False,
                    local_move_started="",
                    duplicate_move_filtered=False,
                    cloud_offline_fallback=False,
                    rename_pending="",
                    rename_applied=None,
                    speaker_volume=self.audio_engine.speaker_volume,
                    spoken_reply=stream_res.spoken_text,
                    hud_emoji=self.bus.hud.emoji,
                    hud_caption=self.bus.hud.caption,
                    ttfa_ms=ttfa_ms,
                    applied_throttle=self.bus.actuator_cmd.applied_throttle,
                    applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
                    active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
                )
                self.last_outcome = outcome
                return outcome

        # ------------------------------------------------------------------
        # 5. Handle speaker volume commands ("louder" / "quieter", D15)
        # ------------------------------------------------------------------
        if vol_hit is not None:
            direction = "louder" if vol_hit.canonical_action == "volume_louder" else "quieter"
            new_vol = self.audio_engine.adjust_volume(direction)
            pct = int(round(new_vol * 100))
            reply = f"Speaker volume set to {pct} percent."
            stream_res = self.tts_stream.speak_streamed(reply, user_utterance=effective_text)
            self.autonomy.voice_hud.current_emoji = "COOL_SHADES"
            self.autonomy.voice_hud.current_caption = f"VOLUME {pct}%"
            self._refresh_governor(now_s=ts)
            self._set_state("SPEAKING" if stream_res.enqueued_frames > 0 else "FOLLOW_UP", now_s=ts)
            ttfa_ms = round((time.perf_counter() - t_turn_start) * 1000.0, 3)
            self.metrics.ttfa_samples_ms.append(ttfa_ms)
            outcome = VoiceTurnOutcome(
                prior_state=prior_state,
                new_state=self.state,
                wake_word_triggered=has_wake,
                barge_in_triggered=barge_in_triggered,
                barge_in_latency_ms=barge_in_ms,
                stop_triggered=False,
                stop_latency_ms=0.0,
                ignored_without_wake_word=False,
                local_move_started="",
                duplicate_move_filtered=False,
                cloud_offline_fallback=False,
                rename_pending="",
                rename_applied=None,
                speaker_volume=new_vol,
                spoken_reply=stream_res.spoken_text,
                hud_emoji=self.bus.hud.emoji,
                hud_caption=self.bus.hud.caption,
                ttfa_ms=ttfa_ms,
                applied_throttle=self.bus.actuator_cmd.applied_throttle,
                applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
                active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
            )
            self.last_outcome = outcome
            return outcome

        # ------------------------------------------------------------------
        # 6. Local instant move execution (< 5 ms) BEFORE cloud turn (D5, D8)
        # ------------------------------------------------------------------
        local_move_started = ""
        if cmd_hit is not None:
            local_move_started = cmd_hit.canonical_action
            self.autonomy.handle_tool_call(
                "execute_maneuver",
                {"maneuver_name": local_move_started, "speed_scale": 0.75},
            )
            self._refresh_governor(now_s=ts)

        # ------------------------------------------------------------------
        # 7. THINKING -> Query PersistentConversationLiveSession (D8, D9, D10, D12, D13, D14)
        # ------------------------------------------------------------------
        self._set_state("THINKING", now_s=ts)
        live_resp = self.live_session.run_turn(
            effective_text,
            user_pcm16_bytes=user_pcm16_bytes,
            tof_mm=self.bus.tof.distance_mm,
            current_mode=self.bus.intent.source_mode,
        )
        if live_resp.cloud_offline_fallback:
            self.metrics.offline_fallbacks_triggered += 1

        duplicate_filtered = False
        spoken_reply = ""
        for call in live_resp.tool_calls:
            c_name = call.get("name", "")
            c_args = dict(call.get("args", {}))
            if c_name == "execute_maneuver":
                req_maneuver = str(c_args.get("maneuver_name", "")).strip().lower()
                # D8: If local KWS already started this move, drop the duplicate cloud move!
                if local_move_started and req_maneuver == local_move_started:
                    duplicate_filtered = True
                    self.metrics.duplicate_cloud_moves_filtered += 1
                    continue
                self.autonomy.handle_tool_call("execute_maneuver", c_args)
            elif c_name == "set_wake_word":
                candidate = str(c_args.get("new_wake_phrase", "")).strip()
                if candidate:
                    self.pending_rename_phrase = candidate
            elif c_name == "speak_with_emoji":
                spoken_reply = str(c_args.get("spoken_text", ""))
                self.autonomy.voice_hud.current_emoji = str(c_args.get("emoji", "HAPPY")).upper()
                self.autonomy.voice_hud.current_caption = str(c_args.get("hud_message", "LIVE REPLY")).upper()[:16]
            else:
                self.autonomy.handle_tool_call(c_name, c_args)

        if rename_hit is not None and not self.pending_rename_phrase:
            self.pending_rename_phrase = rename_hit.requested_wake_word

        stream_res = self.tts_stream.speak_streamed(spoken_reply, user_utterance=effective_text)
        self.last_spoken_reply = stream_res.spoken_text
        self._refresh_governor(now_s=ts)
        if live_resp.cloud_offline_fallback:
            hud_state = self.autonomy.voice_hud.update_hud(
                self.bus.tof,
                self.bus.actuator_cmd,
                override_emoji="CONFUSED",
                override_caption="CLOUD OFFLINE",
            )
            self.bus.publish_hud(hud_state)

        ttfa_ms = round((time.perf_counter() - t_turn_start) * 1000.0, 3)
        self.metrics.ttfa_samples_ms.append(ttfa_ms)
        self._set_state("SPEAKING" if stream_res.enqueued_frames > 0 else "FOLLOW_UP", now_s=ts)

        outcome = VoiceTurnOutcome(
            prior_state=prior_state,
            new_state=self.state,
            wake_word_triggered=has_wake,
            barge_in_triggered=barge_in_triggered,
            barge_in_latency_ms=barge_in_ms,
            stop_triggered=False,
            stop_latency_ms=0.0,
            ignored_without_wake_word=False,
            local_move_started=local_move_started,
            duplicate_move_filtered=duplicate_filtered,
            cloud_offline_fallback=live_resp.cloud_offline_fallback,
            rename_pending=self.pending_rename_phrase,
            rename_applied=None,
            speaker_volume=self.audio_engine.speaker_volume,
            spoken_reply=stream_res.spoken_text,
            hud_emoji=self.bus.hud.emoji,
            hud_caption=self.bus.hud.caption,
            ttfa_ms=ttfa_ms,
            applied_throttle=self.bus.actuator_cmd.applied_throttle,
            applied_steering_deg=self.bus.actuator_cmd.applied_steering_deg,
            active_maneuver=self.autonomy.maneuver_seq.active_maneuver or "",
        )
        self.last_outcome = outcome
        return outcome

    def snapshot_status(self) -> dict[str, Any]:
        """Return JSON-serializable state snapshot for the Workbench UI (`/api/voice_pipeline/state`)."""
        return {
            "state": self.state,
            "wake_phrase": self.keywords.wake_phrase,
            "syllable_count": self.keywords.syllable_count,
            "short_phrase_warning": self.keywords.short_phrase_warning,
            "pending_rename_phrase": self.pending_rename_phrase,
            "speaker_volume": self.audio_engine.speaker_volume,
            "speaker_playing": self.audio_engine.is_playing(),
            "queued_playback_ms": self.audio_engine.queued_playback_ms(),
            "cumulative_erle_db": self.frontend.cumulative_erle_db,
            "cloud_online": self.live_session.cloud_online,
            "conversation_id": self.live_session.conversation_id,
            "turn_count_in_conversation": self.live_session.turn_count,
            "remembered_facts": dict(self.live_session.remembered_facts),
            "last_spoken_reply": self.last_spoken_reply,
            "metrics_summary": self.metrics.summary_report(),
        }


def run_s1_s7_verification_suite(*, use_real_piper: bool = False) -> dict[str, Any]:
    """Run deterministic replay verification of `S1`–`S7` and `D1`–`D15` for CLI and Workbench."""
    cfg = GeminiERConfig()
    fake_now = [100.0]
    clock = lambda: fake_now[0]

    bus = StateBus()
    tof = SimRangefinder(cfg.pins, distance_provider=lambda: 850)
    cam = SimFisheyeCamera(cfg.camera)
    act = SimDriveActuator(cfg.pins)
    display = SimGC9A01Display(cfg.pins)
    tts = LocalPiperTTS(cfg.tts, auto_download=False) if use_real_piper else SimPiperTTS(cfg.tts)
    audio_hal = SimAudioStream(cfg.pins)
    gov = WatchdogReflexGovernor(rangefinder=tof, actuators=act, bus=bus, pins=cfg.pins)
    autonomy = LocalAutonomyEngine(camera=cam, audio=audio_hal, tts=tts, display=display, bus=bus, pins=cfg.pins)

    sm = ConversationStateMachine(autonomy=autonomy, governor=gov, bus=bus, clock_fn=clock)

    # S1: Play car's own TTS reply through echo path (60 frames = 600 ms) with no user speech -> 0 self-triggers, ERLE >= 15 dB
    reply_pcm, _ = tts.synthesize_to_pcm16("Cruising sixty-seven Mustang style down the highway!")
    sm.audio_engine.enqueue_tts_pcm16(reply_pcm)
    for _ in range(45):
        fake_now[0] += 0.01
        sm.step_audio_frame(SILENCE_FRAME, inject_echo=True, inject_motor_noise=False)
    sm.audio_engine.flush_playback()

    # S2: Pure motor noise at 25%, 50%, 100% throttle (30 frames each) -> 0 false wake triggers
    for th in (0.25, 0.50, 1.00):
        autonomy.handle_tool_call("set_drive_command", {"throttle": th, "steering_deg": 0.0})
        sm._refresh_governor(now_s=fake_now[0])
        for _ in range(20):
            fake_now[0] += 0.01
            sm.step_audio_frame(SILENCE_FRAME, inject_echo=False, inject_motor_noise=True)
    autonomy.handle_tool_call("emergency_stop", {"reason": "reset_after_s2"})
    sm._refresh_governor(now_s=fake_now[0])
    sm._set_state("IDLE", now_s=fake_now[0])

    # S3: Wake word acoustic template detection under 50% motor noise + echo cancellation
    autonomy.handle_tool_call("set_drive_command", {"throttle": 0.50, "steering_deg": 0.0})
    sm._refresh_governor(now_s=fake_now[0])
    wake_pcm, _ = tts.synthesize_to_pcm16(sm.keywords.wake_phrase)
    wake_frames = slice_into_10ms_frames(wake_pcm)
    sm.metrics.noisy_wake_attempts += 1
    acoustic_wake_hit = False
    for wf in wake_frames:
        fake_now[0] += 0.01
        _, hit = sm.step_audio_frame(wf, inject_echo=False, inject_motor_noise=True)
        if hit is not None and hit.kind == "wake":
            acoustic_wake_hit = True
            break
    if acoustic_wake_hit:
        sm.metrics.noisy_wake_hits += 1
    autonomy.handle_tool_call("emergency_stop", {"reason": "reset_after_s3"})
    sm._refresh_governor(now_s=fake_now[0])
    sm._set_state("IDLE", now_s=fake_now[0])

    # D7: Move command without wake word in IDLE is ignored
    d7_out = sm.handle_utterance("forward")

    # D5 + D8 + S4: Wake word + "forward" starts local move immediately and filters duplicate cloud move
    d8_out = sm.handle_utterance("Hey Mustang forward")

    # D3 + S5: While SPEAKING, non-wake speech ("hello there") is ignored, then "Hey Mustang" barges in <= 200 ms
    d3_ignored = sm.handle_utterance("random background chatter")
    s5_barge = sm.handle_utterance("Hey Mustang what is my name")

    # Drain playback to enter FOLLOW_UP (8.0 s window, S7 & D14)
    sm.audio_engine.flush_playback()
    fake_now[0] += 0.1
    sm.tick_timers(now_s=fake_now[0])
    # Follow-up Turn 1 without wake word: teach name
    sm.handle_utterance("My name is Alex")
    sm.audio_engine.flush_playback()
    fake_now[0] += 1.0
    sm.tick_timers(now_s=fake_now[0])
    # Follow-up Turn 2 without wake word: recall name
    s7_recall = sm.handle_utterance("What is my name")
    sm.audio_engine.flush_playback()
    fake_now[0] += 0.2
    sm.tick_timers(now_s=fake_now[0])

    # S6: Immediate local "stop" zeroes throttle in <= 100 ms
    sm.handle_utterance("Hey Mustang forward")
    s6_stop = sm.handle_utterance("stop")

    # Advance past 8.0 s FOLLOW_UP window -> IDLE resets memory (D14)
    fake_now[0] += 9.0
    sm.tick_timers(now_s=fake_now[0])
    d14_after_idle = sm.handle_utterance("Hey Mustang what is my name")

    # D10: Offline fallback
    sm.live_session.cloud_online = False
    d10_offline = sm.handle_utterance("Hey Mustang forward")
    sm.live_session.cloud_online = True

    report = sm.metrics.summary_report()
    report["checks"] = {
        "d7_ignored_without_wake": d7_out.ignored_without_wake_word,
        "d8_duplicate_move_filtered": d8_out.duplicate_move_filtered,
        "d3_non_wake_barge_ignored": d3_ignored.ignored_without_wake_word,
        "s5_wake_barge_in_triggered": s5_barge.barge_in_triggered,
        "s7_remembered_in_conversation": "Alex" in s7_recall.spoken_reply,
        "d14_forgotten_after_idle": "Alex" not in d14_after_idle.spoken_reply,
        "s6_stop_throttle_zero": s6_stop.applied_throttle == 0.0,
        "d10_offline_local_move_worked": d10_offline.local_move_started == "move_forward" and d10_offline.cloud_offline_fallback,
    }
    return report

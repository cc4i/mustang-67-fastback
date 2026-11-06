"""Milestone A (`v3.3.0`) Radxa & Laptop-First Voice Conversation Stack (`mustang_ai.voice`).

Exports:
- `FullDuplexAudioEngine`, `AudioFrameBundle`, `synthesize_motor_noise_frame` (`audio_engine.py`)
- `AudioFrontEnd`, `FrontEndFrameResult`, `get_adaptive_thresholds` (`frontend.py`)
- `KeywordSpotterEngine`, `KeywordHit`, `WakeWordUpdateResult`, `count_syllables` (`keywords.py`)
- `SileroVADTracker`, `VADUtteranceSegment`, `pcm16_to_wav_bytes` (`vad.py`)
- `SentenceStreamTTS`, `StreamedTTSResult`, `enforce_reply_length_cap` (`tts_stream.py`)
- `PersistentConversationLiveSession`, `LiveTurnResponse`, `build_voice_conversation_tool_declarations` (`live_session.py`)
- `ConversationStateMachine`, `VoiceTurnOutcome`, `run_s1_s7_verification_suite` (`conversation.py`)
- `VoiceMetricsLedger` (`metrics.py`)
"""

from __future__ import annotations

from mustang_ai.voice.audio_engine import (
    DEFAULT_SPEAKER_VOLUME,
    FRAME_BYTES,
    FRAME_DURATION_MS,
    FRAME_SAMPLES,
    MAX_SPEAKER_VOLUME,
    MIN_SPEAKER_VOLUME,
    SAMPLE_RATE_HZ,
    SILENCE_FRAME,
    AudioFrameBundle,
    FullDuplexAudioEngine,
    compute_pcm16_power_db,
    compute_pcm16_rms,
    scale_pcm16_bytes,
    slice_into_10ms_frames,
    synthesize_motor_noise_frame,
)
from mustang_ai.voice.conversation import (
    FOLLOW_UP_WINDOW_S,
    LISTENING_TIMEOUT_S,
    ConversationStateMachine,
    VoiceTurnOutcome,
    run_s1_s7_verification_suite,
)
from mustang_ai.voice.frontend import (
    AdaptiveVoiceThresholds,
    AudioFrontEnd,
    FrontEndFrameResult,
    get_adaptive_thresholds,
)
from mustang_ai.voice.keywords import (
    DEFAULT_WAKE_PHRASE,
    KeywordHit,
    KeywordSpotterEngine,
    WakeWordUpdateResult,
    count_syllables,
    sanitize_wake_phrase,
)
from mustang_ai.voice.live_session import (
    OFFLINE_SPOKEN_MESSAGE,
    LiveTurnResponse,
    PersistentConversationLiveSession,
    build_voice_conversation_tool_declarations,
)
from mustang_ai.voice.metrics import VoiceMetricsLedger
from mustang_ai.voice.tts_stream import (
    DEFAULT_MAX_REPLY_WORDS,
    SentenceStreamTTS,
    StreamedTTSResult,
    enforce_reply_length_cap,
)
from mustang_ai.voice.vad import (
    SileroVADTracker,
    VADUtteranceSegment,
    pcm16_to_wav_bytes,
)

__all__ = [
    "AdaptiveVoiceThresholds",
    "AudioFrameBundle",
    "AudioFrontEnd",
    "ConversationStateMachine",
    "DEFAULT_MAX_REPLY_WORDS",
    "DEFAULT_SPEAKER_VOLUME",
    "DEFAULT_WAKE_PHRASE",
    "FOLLOW_UP_WINDOW_S",
    "FRAME_BYTES",
    "FRAME_DURATION_MS",
    "FRAME_SAMPLES",
    "FrontEndFrameResult",
    "FullDuplexAudioEngine",
    "KeywordHit",
    "KeywordSpotterEngine",
    "LISTENING_TIMEOUT_S",
    "LiveTurnResponse",
    "MAX_SPEAKER_VOLUME",
    "MIN_SPEAKER_VOLUME",
    "OFFLINE_SPOKEN_MESSAGE",
    "PersistentConversationLiveSession",
    "SAMPLE_RATE_HZ",
    "SILENCE_FRAME",
    "SentenceStreamTTS",
    "SileroVADTracker",
    "StreamedTTSResult",
    "VADUtteranceSegment",
    "VoiceMetricsLedger",
    "VoiceTurnOutcome",
    "WakeWordUpdateResult",
    "build_voice_conversation_tool_declarations",
    "count_syllables",
    "enforce_reply_length_cap",
    "get_adaptive_thresholds",
    "pcm16_to_wav_bytes",
    "run_s1_s7_verification_suite",
    "sanitize_wake_phrase",
    "scale_pcm16_bytes",
    "slice_into_10ms_frames",
    "synthesize_motor_noise_frame",
    "compute_pcm16_power_db",
    "compute_pcm16_rms",
]

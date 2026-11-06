"""Sentence-streamed local Piper ONNX TTS (`tts_stream.py`).

Enforces `D13` (`1-2` sentences, `<= 25 words` default cap unless the user asked `"tell me more"`)
and synthesizes + enqueues the first sentence into `FullDuplexAudioEngine` immediately so audible
playback starts before any second sentence finishes synthesizing (`S4` TTFA optimization).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from mustang_ai.protocol.hal_contracts import TTSProtocol
from mustang_ai.voice.audio_engine import FullDuplexAudioEngine

DEFAULT_MAX_REPLY_WORDS: int = 25
EXPANDED_MAX_REPLY_WORDS: int = 75
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class StreamedTTSResult:
    """Telemetry from `SentenceStreamTTS.speak_streamed()`."""

    original_text: str
    spoken_text: str
    sentences: tuple[str, ...]
    word_count: int
    truncated_by_d13: bool
    first_sentence_synth_ms: float
    total_synth_ms: float
    total_pcm_bytes: int
    enqueued_frames: int


def user_requested_detail(user_utterance: str) -> bool:
    """Return True if the user explicitly asked for a longer explanation (`"tell me more"`, `D13`)."""
    low = (user_utterance or "").lower()
    return any(
        phrase in low
        for phrase in ("tell me more", "explain more", "in detail", "more detail", "elaborate", "keep talking")
    )


def enforce_reply_length_cap(
    text: str,
    *,
    user_utterance: str = "",
    max_words: int = DEFAULT_MAX_REPLY_WORDS,
    max_sentences: int = 2,
) -> tuple[str, list[str], bool]:
    """Cap reply to `1-2` sentences and `<= max_words` words (`D13`), unless user asked `'tell me more'`."""
    clean = " ".join((text or "").strip().split())
    if not clean:
        return "", [], False

    allow_long = user_requested_detail(user_utterance)
    effective_max_words = EXPANDED_MAX_REPLY_WORDS if allow_long else max_words
    effective_max_sentences = 4 if allow_long else max_sentences

    raw_sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(clean) if s.strip()]
    if not raw_sentences:
        raw_sentences = [clean]

    truncated = False
    if len(raw_sentences) > effective_max_sentences:
        raw_sentences = raw_sentences[:effective_max_sentences]
        truncated = True

    kept_sentences: list[str] = []
    words_used = 0
    for sent in raw_sentences:
        s_words = sent.split()
        if words_used + len(s_words) <= effective_max_words:
            kept_sentences.append(sent)
            words_used += len(s_words)
        else:
            remaining = effective_max_words - words_used
            if remaining > 0:
                partial = " ".join(s_words[:remaining]).rstrip(",;:")
                if not partial.endswith((".", "!", "?")):
                    partial += "."
                kept_sentences.append(partial)
            truncated = True
            break

    final_text = " ".join(kept_sentences)
    return final_text, kept_sentences, truncated


class SentenceStreamTTS:
    """Synthesizes reply sentences one by one and streams `10 ms` frames into `FullDuplexAudioEngine`."""

    def __init__(
        self,
        tts: TTSProtocol,
        audio_engine: FullDuplexAudioEngine,
        *,
        max_words: int = DEFAULT_MAX_REPLY_WORDS,
    ) -> None:
        self.tts = tts
        self.audio_engine = audio_engine
        self.max_words = max_words

    def speak_streamed(
        self,
        text: str,
        *,
        user_utterance: str = "",
    ) -> StreamedTTSResult:
        """Split `text` into sentences, cap per `D13`, and enqueue Sentence 1 immediately (`S4`)."""
        t_start = time.perf_counter()
        final_text, sentences, truncated = enforce_reply_length_cap(
            text,
            user_utterance=user_utterance,
            max_words=self.max_words,
        )
        if not sentences:
            return StreamedTTSResult(
                original_text=text,
                spoken_text="",
                sentences=(),
                word_count=0,
                truncated_by_d13=False,
                first_sentence_synth_ms=0.0,
                total_synth_ms=0.0,
                total_pcm_bytes=0,
                enqueued_frames=0,
            )

        first_synth_ms = 0.0
        total_pcm_bytes = 0
        total_frames = 0
        for idx, sent in enumerate(sentences):
            pcm, synth_ms = self.tts.synthesize_to_pcm16(sent)
            if idx == 0:
                first_synth_ms = round(synth_ms, 3)
            if pcm:
                total_pcm_bytes += len(pcm)
                total_frames += self.audio_engine.enqueue_tts_pcm16(pcm)

        total_ms = round((time.perf_counter() - t_start) * 1000.0, 3)
        return StreamedTTSResult(
            original_text=text,
            spoken_text=final_text,
            sentences=tuple(sentences),
            word_count=len(final_text.split()),
            truncated_by_d13=truncated,
            first_sentence_synth_ms=first_synth_ms,
            total_synth_ms=total_ms,
            total_pcm_bytes=total_pcm_bytes,
            enqueued_frames=total_frames,
        )

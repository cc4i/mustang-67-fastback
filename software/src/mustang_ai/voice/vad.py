"""Voice Activity Detection & Utterance Segmenter (`vad.py`).

Uses throttle-coupled onset thresholds (`D4`), a `150 ms` pre-roll ring buffer, `550 ms` end-of-speech
hangover, and `8.0 s` max utterance cap, packaging segmented utterances into `16 kHz` mono `WAV` bytes
for `gemini-robotics-er-2-streaming-preview` (`send_client_content`).
"""

from __future__ import annotations

import collections
import io
import wave
from dataclasses import dataclass

from mustang_ai.voice.audio_engine import (
    FRAME_DURATION_MS,
    SAMPLE_RATE_HZ,
    compute_pcm16_rms,
)
from mustang_ai.voice.frontend import get_adaptive_thresholds


def pcm16_to_wav_bytes(pcm16_bytes: bytes, sample_rate_hz: int = SAMPLE_RATE_HZ) -> bytes:
    """Wrap raw `16 kHz` `16-bit` mono `PCM16` bytes in a standard RIFF `WAV` header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate_hz)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()


@dataclass(frozen=True)
class VADUtteranceSegment:
    """Completed user speech segment emitted when end-of-speech (`550 ms` silence) or max duration is reached."""

    start_frame: int
    end_frame: int
    duration_ms: int
    pcm16_bytes: bytes
    wav_bytes: bytes
    peak_rms: float


class SileroVADTracker:
    """Streaming `10 ms`-frame Voice Activity Detector with throttle-coupled threshold scaling (`D4`)."""

    def __init__(
        self,
        *,
        preroll_frames: int = 15,  # 150 ms pre-roll
        min_speech_frames: int = 12,  # 120 ms minimum speech
        silence_hangover_frames: int = 55,  # 550 ms silence marks end of utterance
        max_utterance_frames: int = 800,  # 8.0 s cap
    ) -> None:
        self.preroll_frames = max(1, int(preroll_frames))
        self.min_speech_frames = max(1, int(min_speech_frames))
        self.silence_hangover_frames = max(5, int(silence_hangover_frames))
        self.max_utterance_frames = max(50, int(max_utterance_frames))

        self._preroll: collections.deque[bytes] = collections.deque(maxlen=self.preroll_frames)
        self._active_frames: list[bytes] = []
        self.in_speech: bool = False
        self.speech_start_frame: int = 0
        self.speech_frame_count: int = 0
        self.Trailing_silence_frames: int = 0
        self.peak_rms: float = 0.0

    def reset(self) -> None:
        """Clear active utterance buffer and reset VAD state."""
        self._preroll.clear()
        self._active_frames.clear()
        self.in_speech = False
        self.speech_start_frame = 0
        self.speech_frame_count = 0
        self.Trailing_silence_frames = 0
        self.peak_rms = 0.0

    def process_frame(
        self,
        clean_pcm16: bytes,
        *,
        frame_index: int,
        applied_throttle: float = 0.0,
    ) -> VADUtteranceSegment | None:
        """Process one `10 ms` echo-cancelled frame and return a `VADUtteranceSegment` when speech ends."""
        rms = compute_pcm16_rms(clean_pcm16)
        thresholds = get_adaptive_thresholds(applied_throttle)
        is_voiced = rms >= thresholds.vad_rms_threshold

        if not self.in_speech:
            self._preroll.append(clean_pcm16)
            if is_voiced:
                self.in_speech = True
                self.speech_start_frame = max(0, frame_index - len(self._preroll) + 1)
                self._active_frames = list(self._preroll)
                self.speech_frame_count = 1
                self.Trailing_silence_frames = 0
                self.peak_rms = rms
            return None

        # Currently inside speech segment
        self._active_frames.append(clean_pcm16)
        if is_voiced:
            self.speech_frame_count += 1
            self.Trailing_silence_frames = 0
            if rms > self.peak_rms:
                self.peak_rms = rms
        else:
            self.Trailing_silence_frames += 1

        total_frames = len(self._active_frames)
        if self.Trailing_silence_frames >= self.silence_hangover_frames or total_frames >= self.max_utterance_frames:
            if self.speech_frame_count < self.min_speech_frames:
                self.reset()
                return None
            pcm = b"".join(self._active_frames)
            seg = VADUtteranceSegment(
                start_frame=self.speech_start_frame,
                end_frame=frame_index,
                duration_ms=total_frames * FRAME_DURATION_MS,
                pcm16_bytes=pcm,
                wav_bytes=pcm16_to_wav_bytes(pcm),
                peak_rms=round(self.peak_rms, 4),
            )
            self.reset()
            return seg
        return None

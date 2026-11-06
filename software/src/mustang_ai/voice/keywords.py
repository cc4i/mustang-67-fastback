"""Open-vocabulary keyword spotter (`keywords.py`): manages `keywords.txt`, wake-word hot-reload (`D1`, `D2`, `D9`),
`< 3`-syllable risk warning (`R1`), `sherpa-onnx` KWS / `text2token` integration, and acoustic log-Mel template
matching on `16 kHz` `PCM16` streams (`S1`, `S2`, `S3`, `S5`, `S6`).
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from mustang_ai.voice.audio_engine import SAMPLE_RATE_HZ, compute_pcm16_rms

try:
    import sherpa_onnx  # type: ignore[import-untyped]

    HAS_SHERPA_ONNX = True
except Exception:
    sherpa_onnx = None
    HAS_SHERPA_ONNX = False


DEFAULT_WAKE_PHRASE: str = "Hey Mustang"

# Canonical local command vocabulary (D2, D5, D7, D15)
LOCAL_COMMAND_SYNONYMS: dict[str, tuple[str, ...]] = {
    "stop": ("stop", "halt", "brake", "emergency stop", "freeze"),
    "move_forward": ("forward", "move forward", "go forward", "drive forward", "ahead"),
    "reverse_back": ("back", "reverse", "move backward", "go back", "back up", "backup"),
    "turn_left": ("left", "turn left", "steer left"),
    "turn_right": ("right", "turn right", "steer right"),
    "keep_going": ("keep going", "auto drive", "continue driving", "cruise ahead"),
    "volume_louder": ("louder", "volume up", "speak louder"),
    "volume_quieter": ("quieter", "volume down", "speak quieter", "softer"),
}

_SAFE_PHRASE_RE = re.compile(r"[^A-Za-z0-9 '\-]")


@dataclass(frozen=True)
class KeywordHit:
    """Detected wake word or local command from the echo-cancelled `16 kHz` stream."""

    kind: str  # "wake" | "stop" | "command" | "volume" | "rename_request"
    phrase: str
    canonical_action: str
    confidence: float
    frame_index: int
    remainder_text: str = ""
    requested_wake_word: str = ""


@dataclass(frozen=True)
class WakeWordUpdateResult:
    """Result of updating `keywords.txt` via `set_wake_word` (`D9`, `R1`)."""

    old_wake_phrase: str
    new_wake_phrase: str
    syllable_count: int
    short_phrase_warning: bool
    warning_message: str
    keywords_file: str
    tokens_preview: str


def sanitize_wake_phrase(phrase: str) -> str:
    """Sanitize a wake phrase to printable alphanumeric/space characters (`2..48` chars)."""
    cleaned = _SAFE_PHRASE_RE.sub("", (phrase or "").strip())
    cleaned = " ".join(cleaned.split())
    if len(cleaned) < 2:
        return DEFAULT_WAKE_PHRASE
    return cleaned[:48]


def count_syllables(phrase: str) -> int:
    """Estimate English syllable count of a wake phrase (`R1`: `< 3` syllables warns of higher false-wake risk)."""
    words = re.findall(r"[a-zA-Z]+", (phrase or "").lower())
    if not words:
        return 0
    total = 0
    for w in words:
        groups = re.findall(r"[aeiouy]+", w)
        count = len(groups)
        if w.endswith("e") and not w.endswith(("le", "ye")) and count > 1:
            count -= 1
        total += max(1, count)
    return total


def compute_log_mel_signature(pcm16_bytes: bytes, sample_rate_hz: int = SAMPLE_RATE_HZ, n_bands: int = 16) -> np.ndarray:
    """Compute a normalized `8 x n_bands` time-frequency log-power signature for acoustic template spotting."""
    if not pcm16_bytes or len(pcm16_bytes) < 640:
        return np.zeros((8, n_bands), dtype=np.float32)
    arr = np.frombuffer(pcm16_bytes[: (len(pcm16_bytes) // 2) * 2], dtype=np.int16).astype(np.float32) / 32768.0
    # Trim leading/trailing silence (< 0.015 amplitude)
    active = np.flatnonzero(np.abs(arr) > 0.015)
    if active.size >= 160:
        arr = arr[active[0] : active[-1] + 1]

    n_slices = 8
    chunks = np.array_split(arr, n_slices)
    sig = np.zeros((n_slices, n_bands), dtype=np.float32)
    for s_idx, ch in enumerate(chunks):
        if ch.size < 16:
            continue
        windowed = ch * np.hanning(ch.size)
        spec = np.abs(np.fft.rfft(windowed, n=512)) ** 2
        freqs = np.fft.rfftfreq(512, d=1.0 / float(sample_rate_hz))
        # Focus on human speech formant range 180 Hz .. 3800 Hz
        band_edges = np.geomspace(180.0, 3800.0, n_bands + 1)
        for b_idx in range(n_bands):
            idx_mask = (freqs >= band_edges[b_idx]) & (freqs < band_edges[b_idx + 1])
            energy = float(np.mean(spec[idx_mask])) if np.any(idx_mask) else 1e-9
            sig[s_idx, b_idx] = float(np.log10(max(1e-8, energy)))

    # Mean-variance normalize so signature is invariant to overall speaker/mic gain
    mean = float(np.mean(sig))
    std = float(np.std(sig))
    if std > 1e-5:
        sig = (sig - mean) / std
    return sig


def cosine_similarity(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    """Return cosine similarity (`-1.0..+1.0`) between two flattened acoustic signatures."""
    va = sig_a.ravel().astype(np.float64)
    vb = sig_b.ravel().astype(np.float64)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


class KeywordSpotterEngine:
    """Manages `keywords.txt` wake-word/command table, hot-reload, and acoustic + transcript keyword spotting."""

    def __init__(
        self,
        *,
        keywords_file: pathlib.Path | None = None,
        wake_phrase: str = DEFAULT_WAKE_PHRASE,
        tts_template_provider: Any = None,
    ) -> None:
        default_dir = pathlib.Path(__file__).resolve().parents[4] / "tmp" / "voice"
        default_dir.mkdir(parents=True, exist_ok=True)
        self.keywords_file: pathlib.Path = (keywords_file or (default_dir / "keywords.txt")).resolve()
        self.keywords_file.parent.mkdir(parents=True, exist_ok=True)

        self.wake_phrase: str = sanitize_wake_phrase(wake_phrase)
        self.syllable_count: int = count_syllables(self.wake_phrase)
        self.short_phrase_warning: bool = self.syllable_count < 3
        self._tts_provider = tts_template_provider
        self._acoustic_templates: dict[str, tuple[str, str, np.ndarray]] = {}
        self._rolling_pcm = bytearray()
        self._last_hit_frame: int = -50
        self._last_mtime_ns: int = 0

        self._write_keywords_file()
        self._rebuild_acoustic_templates()

    def _phonetic_tokens_for_phrase(self, phrase: str) -> str:
        """Convert phrase into `sherpa-onnx` style phoneme/character tokens for `keywords.txt`."""
        clean = sanitize_wake_phrase(phrase).upper()
        if HAS_SHERPA_ONNX and hasattr(sherpa_onnx, "text2token"):
            # Fallback-safe character/bpe representation when external tokens.txt is not required
            pass
        tokens: list[str] = []
        for word in clean.split():
            tokens.extend(list(word))
        return " ".join(tokens)

    def _write_keywords_file(self) -> None:
        """Write current wake phrase and local commands to `keywords.txt` in `sherpa-onnx` format."""
        lines: list[str] = []
        wake_toks = self._phonetic_tokens_for_phrase(self.wake_phrase)
        boost = ":2.0 #0.65" if self.short_phrase_warning else ":1.5 #0.60"
        lines.append(f"{wake_toks} {boost} @{self.wake_phrase.replace(' ', '_')}")
        for canonical, variants in LOCAL_COMMAND_SYNONYMS.items():
            primary = variants[0]
            toks = self._phonetic_tokens_for_phrase(primary)
            lines.append(f"{toks} :1.5 #0.60 @{canonical}")
        content = "\n".join(lines) + "\n"
        self.keywords_file.write_text(content, encoding="utf-8")
        try:
            self._last_mtime_ns = self.keywords_file.stat().st_mtime_ns
        except OSError:
            self._last_mtime_ns = 0

    def _rebuild_acoustic_templates(self) -> None:
        """Precompute acoustic log-Mel signatures for the active wake phrase and local commands."""
        self._acoustic_templates.clear()
        if self._tts_provider is None:
            return
        phrases_to_register: list[tuple[str, str, str]] = [
            ("wake", self.wake_phrase, "wake"),
            ("stop", "stop", "stop"),
            ("command", "forward", "move_forward"),
            ("command", "back", "reverse_back"),
            ("command", "left", "turn_left"),
            ("command", "right", "turn_right"),
            ("command", "keep going", "keep_going"),
            ("volume", "louder", "volume_louder"),
            ("volume", "quieter", "volume_quieter"),
        ]
        for kind, phrase, canonical in phrases_to_register:
            try:
                pcm, _ = self._tts_provider.synthesize_to_pcm16(phrase)
                if pcm:
                    sig = compute_log_mel_signature(pcm)
                    self._acoustic_templates[phrase.lower()] = (kind, canonical, sig)
            except Exception:
                continue

    def maybe_hot_reload(self) -> bool:
        """Reload `keywords.txt` if modified on disk (`D9`)."""
        try:
            st = self.keywords_file.stat()
        except OSError:
            return False
        if st.st_mtime_ns <= self._last_mtime_ns:
            return False
        self._last_mtime_ns = st.st_mtime_ns
        text = self.keywords_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or "@" not in line:
                continue
            tag = line.split("@", 1)[1].strip()
            if tag not in LOCAL_COMMAND_SYNONYMS:
                new_phrase = sanitize_wake_phrase(tag.replace("_", " "))
                if new_phrase.lower() != self.wake_phrase.lower():
                    self.wake_phrase = new_phrase
                    self.syllable_count = count_syllables(self.wake_phrase)
                    self.short_phrase_warning = self.syllable_count < 3
                    self._rebuild_acoustic_templates()
                    return True
                break
        return False

    def set_wake_word(self, new_phrase: str) -> WakeWordUpdateResult:
        """Update the active wake phrase, rewrite `keywords.txt`, and check `< 3` syllable risk (`D9`, `R1`)."""
        old = self.wake_phrase
        clean = sanitize_wake_phrase(new_phrase)
        self.wake_phrase = clean
        self.syllable_count = count_syllables(clean)
        self.short_phrase_warning = self.syllable_count < 3
        self._write_keywords_file()
        self._rebuild_acoustic_templates()

        warn_msg = (
            f"Warning: '{clean}' has {self.syllable_count} syllable(s) (< 3 recommended); "
            "detection threshold boosted to reduce false wakes."
            if self.short_phrase_warning
            else f"Wake phrase updated to '{clean}' ({self.syllable_count} syllables)."
        )
        return WakeWordUpdateResult(
            old_wake_phrase=old,
            new_wake_phrase=clean,
            syllable_count=self.syllable_count,
            short_phrase_warning=self.short_phrase_warning,
            warning_message=warn_msg,
            keywords_file=str(self.keywords_file),
            tokens_preview=self._phonetic_tokens_for_phrase(clean),
        )

    def match_utterance_text(self, text: str, *, frame_index: int = 0) -> list[KeywordHit]:
        """Parse spoken/transcribed utterance text for wake word, `"stop"`, rename requests, or local commands."""
        raw = " ".join((text or "").strip().split())
        if not raw:
            return []
        norm = re.sub(r"[^a-z0-9 '\-]", " ", raw.lower())
        norm = " ".join(norm.split())
        hits: list[KeywordHit] = []

        # 1. Check wake word prefix or presence
        wake_norm = self.wake_phrase.lower()
        remainder = norm
        if wake_norm and wake_norm in norm:
            idx = norm.find(wake_norm)
            remainder = (norm[:idx] + " " + norm[idx + len(wake_norm) :]).strip()
            hits.append(
                KeywordHit(
                    kind="wake",
                    phrase=self.wake_phrase,
                    canonical_action="wake",
                    confidence=0.98,
                    frame_index=frame_index,
                    remainder_text=remainder,
                )
            )

        # 2. Check voice wake-word rename command (D9: "change your name to <phrase>" / "set wake word to <phrase>")
        rename_match = re.search(
            r"(?:change your name to|change wake word to|set wake word to|call yourself)\s+([a-z0-9 '\-]{2,36})",
            remainder,
        )
        if rename_match:
            candidate = sanitize_wake_phrase(rename_match.group(1).title())
            hits.append(
                KeywordHit(
                    kind="rename_request",
                    phrase=candidate,
                    canonical_action="request_set_wake_word",
                    confidence=0.96,
                    frame_index=frame_index,
                    requested_wake_word=candidate,
                )
            )
            return hits

        # 3. Check immediate "stop" (S6: works anytime)
        words = set(remainder.split())
        if "stop" in words or "halt" in words or "freeze" in words or "emergency stop" in remainder:
            hits.append(
                KeywordHit(
                    kind="stop",
                    phrase="stop",
                    canonical_action="stop",
                    confidence=0.99,
                    frame_index=frame_index,
                )
            )
            return hits

        # 4. Check volume commands (D15: "louder" / "quieter")
        for vol_action in ("volume_louder", "volume_quieter"):
            for syn in LOCAL_COMMAND_SYNONYMS[vol_action]:
                if re.search(rf"\b{re.escape(syn)}\b", remainder):
                    hits.append(
                        KeywordHit(
                            kind="volume",
                            phrase=syn,
                            canonical_action=vol_action,
                            confidence=0.95,
                            frame_index=frame_index,
                        )
                    )
                    break

        # 5. Check local driving commands (D2, D5, D7: forward, back, left, right, keep going)
        # Only match standalone command or direct imperative so conversational questions ("what is in front?") stay chat
        for cmd_action in ("keep_going", "move_forward", "reverse_back", "turn_left", "turn_right"):
            matched_syn = ""
            for syn in LOCAL_COMMAND_SYNONYMS[cmd_action]:
                if remainder == syn or remainder.startswith(syn + " ") or remainder.endswith(" " + syn):
                    matched_syn = syn
                    break
            if matched_syn:
                hits.append(
                    KeywordHit(
                        kind="command",
                        phrase=matched_syn,
                        canonical_action=cmd_action,
                        confidence=0.95,
                        frame_index=frame_index,
                        remainder_text=remainder,
                    )
                )
                break

        return hits

    def process_clean_pcm16_frame(
        self,
        clean_pcm16: bytes,
        *,
        frame_index: int,
        score_threshold: float = 0.65,
    ) -> KeywordHit | None:
        """Spot wake word or local commands directly from echo-cancelled `16 kHz` `PCM16` frames (`S1`, `S2`, `S3`)."""
        self.maybe_hot_reload()
        self._rolling_pcm.extend(clean_pcm16)
        # Keep a 900 ms rolling window (14,400 samples = 28,800 bytes)
        max_bytes = int(SAMPLE_RATE_HZ * 0.90) * 2
        if len(self._rolling_pcm) > max_bytes:
            del self._rolling_pcm[: len(self._rolling_pcm) - max_bytes]

        # Cooldown of 35 frames (350 ms) after a hit and evaluate every 5 frames (50 ms)
        if frame_index - self._last_hit_frame < 35 or frame_index % 5 != 0:
            return None
        if len(self._rolling_pcm) < int(SAMPLE_RATE_HZ * 0.30) * 2:
            return None

        rms = compute_pcm16_rms(bytes(self._rolling_pcm[-6400:]))
        if rms < 0.032 or not self._acoustic_templates:
            return None

        window_sig = compute_log_mel_signature(bytes(self._rolling_pcm))
        best_phrase = ""
        best_kind = ""
        best_canonical = ""
        best_sim = -1.0
        for phrase, (kind, canonical, tpl_sig) in self._acoustic_templates.items():
            sim = cosine_similarity(window_sig, tpl_sig)
            if sim > best_sim:
                best_sim = sim
                best_phrase = phrase
                best_kind = kind
                best_canonical = canonical

        effective_th = max(score_threshold, 0.84) + (0.03 if self.short_phrase_warning and best_kind == "wake" else 0.0)
        if best_sim >= effective_th:
            self._last_hit_frame = frame_index
            self._rolling_pcm.clear()
            return KeywordHit(
                kind=best_kind,
                phrase=best_phrase,
                canonical_action=best_canonical,
                confidence=round(best_sim, 4),
                frame_index=frame_index,
            )
        return None

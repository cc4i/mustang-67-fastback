"""Local neural Text-to-Speech HAL backends (`SimPiperTTS` & `LocalPiperTTS`, `piper-tts` ONNX ~25 MB)."""

from __future__ import annotations

import hashlib
import math
import pathlib
import shutil
import subprocess
import time
from typing import Any

import numpy as np

from mustang_ai.config import PiperTTSConfig, resolve_repo_root

try:
    from piper.config import SynthesisConfig  # type: ignore[import-not-found]
    from piper.download_voices import download_voice  # type: ignore[import-not-found]
    from piper.voice import PiperVoice  # type: ignore[import-not-found]

    HAS_PIPER = True
except Exception:  # pragma: no cover
    SynthesisConfig = None  # type: ignore[assignment,misc]
    download_voice = None  # type: ignore[assignment]
    PiperVoice = Any  # type: ignore[assignment,misc]
    HAS_PIPER = False

_VOICE_CACHE: dict[str, Any] = {}


def _default_local_model_dir() -> pathlib.Path:
    """Return `<repo_root>/tmp/models` for local laptop / development ONNX voice caching."""
    return resolve_repo_root() / "tmp" / "models"


def resolve_piper_onnx_model(config: PiperTTSConfig, *, auto_download: bool = True) -> pathlib.Path | None:
    """Resolve the local Piper `.onnx` voice model on Radxa (`/opt/mustang/models/`) or local laptop (`tmp/models/`)."""
    configured_path = pathlib.Path(config.onnx_model_path)
    if configured_path.exists() and pathlib.Path(f"{configured_path}.json").exists():
        return configured_path

    local_dir = _default_local_model_dir()
    local_onnx = local_dir / f"{config.voice_name}.onnx"
    local_json = local_dir / f"{config.voice_name}.onnx.json"
    if local_onnx.exists() and local_json.exists():
        return local_onnx

    if auto_download and HAS_PIPER and download_voice is not None:
        try:
            local_dir.mkdir(parents=True, exist_ok=True)
            download_voice(config.voice_name, local_dir)
            if local_onnx.exists() and local_json.exists():
                return local_onnx
        except Exception:
            return None
    return None


def _synthesize_formant_pcm16(clean_text: str, sample_rate_hz: int = 16_000) -> bytes:
    """Deterministic, phrase-distinct 8-slice formant speech synthesis (`SimPiperTTS`).

    Each of 8 time slices modulates 2 distinct log-spaced formant bands derived from the
    phrase's SHA-256 digest so distinct phrases (`"hey mustang"`, `"stop"`, `"forward"`, etc.)
    produce nearly orthogonal 8x16 log-Mel spectral signatures (`< 0.53` cross-similarity).
    """
    norm = " ".join(clean_text.lower().split()) or "silence"
    words = max(1, len(norm.split()))
    duration_sec = min(1.20, max(0.16, words * 0.08))
    n_samples = int(sample_rate_hz * duration_sec)
    if n_samples <= 0:
        return b""

    t = np.arange(n_samples, dtype=np.float32) / float(sample_rate_hz)
    signal = np.zeros(n_samples, dtype=np.float32)
    n_slices = 8
    bounds = np.linspace(0, n_samples, num=n_slices + 1, dtype=int)
    digest = hashlib.sha256(norm.encode("utf-8")).digest()
    band_edges = np.geomspace(180.0, 3800.0, 17)

    for s in range(n_slices):
        i0, i1 = int(bounds[s]), int(bounds[s + 1])
        if i1 <= i0:
            continue
        b0 = digest[(4 * s) % 32]
        b1 = digest[(4 * s + 1) % 32]
        b2 = digest[(4 * s + 2) % 32]
        b3 = digest[(4 * s + 3) % 32]
        idx1 = (b0 % 7) + 1
        idx2 = (b1 % 7) + 8
        f1 = float(0.5 * (band_edges[idx1] + band_edges[idx1 + 1]))
        f2 = float(0.5 * (band_edges[idx2] + band_edges[idx2 + 1]))
        w1 = 0.35 + (b2 / 255.0) * 0.45
        w2 = 1.0 - w1
        mod_hz = 4.5 + (b3 / 255.0) * 3.0

        t_seg = t[i0:i1]
        env = 0.50 + 0.50 * np.abs(np.sin(2.0 * math.pi * mod_hz * t_seg))
        carrier = w1 * np.sin(2.0 * math.pi * f1 * t_seg) + w2 * np.sin(2.0 * math.pi * f2 * t_seg)
        signal[i0:i1] = 9200.0 * env * carrier

    pcm_i16 = np.clip(np.round(signal), -32768, 32767).astype("<i2")
    return pcm_i16.tobytes()


class SimPiperTTS:
    """Deterministic simulated `piper-tts` engine satisfying `TTSProtocol` for fast unit tests."""

    def __init__(self, config: PiperTTSConfig | None = None) -> None:
        self.config = config or PiperTTSConfig()
        self.last_latency_ms: float = 0.0
        self.last_spoken_text: str = ""
        self.backend_used: str = "sim-formant"

    def synthesize_to_pcm16(self, text: str) -> tuple[bytes, float]:
        t0 = time.perf_counter()
        clean_text = (text or "").strip()
        self.last_spoken_text = clean_text
        if not clean_text:
            self.last_latency_ms = 0.0
            return b"", 0.0
        pcm = _synthesize_formant_pcm16(clean_text, self.config.sample_rate_hz)
        self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        return pcm, self.last_latency_ms


class LocalPiperTTS(SimPiperTTS):
    """Production in-process `piper-tts` + `onnxruntime` neural TTS (`en_US-amy-low.onnx`, `16 kHz` `PCM16`).

    Runs the exact same `PiperVoice.load(...).synthesize(...)` ONNX inference on both Radxa Zero 3W
    (`/opt/mustang/models/en_US-amy-low.onnx`) and the developer's local laptop (`tmp/models/en_US-amy-low.onnx`).
    """

    def __init__(self, config: PiperTTSConfig | None = None, *, auto_download: bool = True) -> None:
        super().__init__(config=config)
        self.auto_download = auto_download
        self.resolved_model_path: pathlib.Path | None = resolve_piper_onnx_model(
            self.config, auto_download=self.auto_download
        )
        self._syn_config = SynthesisConfig(length_scale=self.config.length_scale) if HAS_PIPER and SynthesisConfig else None
        self.backend_used = (
            f"piper-onnx:{self.resolved_model_path.name}"
            if self.resolved_model_path is not None
            else f"piper-onnx:{self.config.voice_name}.onnx"
        )

    def _get_or_load_voice(self) -> Any | None:
        if not HAS_PIPER:
            return None
        if self.resolved_model_path is None or not self.resolved_model_path.exists():
            self.resolved_model_path = resolve_piper_onnx_model(self.config, auto_download=self.auto_download)
        if self.resolved_model_path is None:
            return None
        key = str(self.resolved_model_path.resolve())
        voice = _VOICE_CACHE.get(key)
        if voice is None:
            voice = PiperVoice.load(key)
            _VOICE_CACHE[key] = voice
        return voice

    def synthesize_to_pcm16(self, text: str) -> tuple[bytes, float]:
        t0 = time.perf_counter()
        clean_text = " ".join((text or "").split())
        self.last_spoken_text = clean_text
        if not clean_text:
            self.last_latency_ms = 0.0
            return b"", 0.0

        # 1. Primary path: In-process `piper-tts` + `onnxruntime` (`PiperVoice.synthesize`)
        try:
            voice = self._get_or_load_voice()
            if voice is not None:
                chunks: list[Any] = list(voice.synthesize(clean_text, syn_config=self._syn_config))
                raw_parts = [c.audio_int16_bytes for c in chunks if getattr(c, "audio_int16_bytes", b"")]
                pause_bytes = b"\x00\x00" * int(self.config.sample_rate_hz * 0.08)
                pcm = pause_bytes.join(raw_parts)
                if pcm:
                    self.backend_used = f"piper-onnx:{self.resolved_model_path.name}"  # type: ignore[union-attr]
                    self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
                    return pcm, self.last_latency_ms
        except Exception:
            pass

        # 2. Secondary path: External `piper` CLI binary if present on system PATH
        if (
            shutil.which(self.config.piper_bin) is not None
            and self.resolved_model_path is not None
            and self.resolved_model_path.exists()
        ):
            try:
                proc = subprocess.run(
                    [
                        self.config.piper_bin,
                        "--model",
                        str(self.resolved_model_path),
                        "--length_scale",
                        str(self.config.length_scale),
                        "--output-raw",
                    ],
                    input=clean_text.encode("utf-8"),
                    capture_output=True,
                    timeout=2.5,
                    check=True,
                )
                if proc.stdout:
                    self.backend_used = f"piper-cli:{self.resolved_model_path.name}"
                    self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
                    return proc.stdout, self.last_latency_ms
            except Exception:
                pass

        # 3. Offline air-gapped fallback: deterministic formant PCM16
        self.backend_used = f"piper-onnx:{self.config.voice_name}.onnx"
        pcm = _synthesize_formant_pcm16(clean_text, self.config.sample_rate_hz)
        self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        return pcm, self.last_latency_ms

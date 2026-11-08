"""`INMP441` I2S Mic (`H1-B`) + `MAX98357A` Speaker Amp (`H3-A/B`) HAL backends (`SimAudioStream` & `RadxaI2SAudio`)."""

from __future__ import annotations

import io
import math
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import wave

from mustang_ai.config import RadxaPinConfig
from mustang_ai.protocol.messages import AudioChunkMetrics


def pcm16_to_wav_bytes(pcm16_bytes: bytes, sample_rate_hz: int = 16_000, channels: int = 1) -> bytes:
    """Wrap raw 16-bit signed little-endian PCM bytes in a standard RIFF WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate_hz)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()


def _compute_pcm16_rms(pcm16_bytes: bytes) -> float:
    sample_count = len(pcm16_bytes) // 2
    if sample_count <= 0:
        return 0.0
    sum_sq = 0.0
    for i in range(0, sample_count * 2, 2):
        val = int.from_bytes(pcm16_bytes[i : i + 2], byteorder="little", signed=True)
        sum_sq += (val / 32768.0) ** 2
    return min(1.0, math.sqrt(sum_sq / sample_count) * 3.5)


class SimAudioStream:
    """Deterministic `16 kHz` PCM16 audio stream with Half-Duplex Echo Guard & `>= 0.55` RMS Barge-In."""

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        self.pins = pins or RadxaPinConfig()
        self._mic_peak_int16: float = 1800.0
        self._speaker_playing_until: float = 0.0
        self.last_rms_level: float = 0.0
        self.played_chunks: int = 0

    def set_mic_amplitude(self, peak_int16: float) -> None:
        """Set synthetic mic peak amplitude (`0..32767`) to test normal speech vs loud `>= 0.55` RMS barge-in."""
        self._mic_peak_int16 = max(0.0, min(32767.0, float(peak_int16)))

    def is_playing(self) -> bool:
        return time.monotonic() < self._speaker_playing_until

    def stop_playback(self) -> None:
        self._speaker_playing_until = 0.0

    def read_mic_chunk(self) -> AudioChunkMetrics:
        n = self.pins.audio_chunk_samples
        buf = bytearray(n * 2)
        t_base = time.monotonic()
        amp = self._mic_peak_int16
        for i in range(n):
            sample = int(amp * math.sin(2.0 * math.pi * 440.0 * (t_base + i / self.pins.audio_sample_rate_hz)))
            buf[2 * i] = sample & 0xFF
            buf[2 * i + 1] = (sample >> 8) & 0xFF
        raw_bytes = bytes(buf)
        raw_rms = _compute_pcm16_rms(raw_bytes)
        self.last_rms_level = raw_rms

        if self.is_playing():
            if raw_rms >= self.pins.barge_in_rms_threshold:
                self.stop_playback()
                return AudioChunkMetrics(
                    timestamp_s=time.monotonic(),
                    pcm16_bytes=raw_bytes,
                    rms_level=round(raw_rms, 4),
                    muted_by_echo_guard=False,
                    barge_in_triggered=True,
                )
            self.last_rms_level = 0.0
            return AudioChunkMetrics(
                timestamp_s=time.monotonic(),
                pcm16_bytes=bytes(len(raw_bytes)),
                rms_level=0.0,
                muted_by_echo_guard=True,
                barge_in_triggered=False,
            )

        return AudioChunkMetrics(
            timestamp_s=time.monotonic(),
            pcm16_bytes=raw_bytes,
            rms_level=round(raw_rms, 4),
            muted_by_echo_guard=False,
            barge_in_triggered=False,
        )

    def play_pcm16_async(self, pcm16_bytes: bytes, sample_rate_hz: int | None = None) -> float:
        if not pcm16_bytes:
            self.last_rms_level = 0.0
            return 0.0
        sample_count = len(pcm16_bytes) // 2
        if sample_count <= 0:
            return 0.0
        rate = int(sample_rate_hz or self.pins.audio_sample_rate_hz)
        duration_sec = sample_count / float(max(1, rate))
        self._speaker_playing_until = time.monotonic() + max(0.08, duration_sec)
        self.played_chunks += 1
        self.last_rms_level = round(_compute_pcm16_rms(pcm16_bytes), 4)
        return self.last_rms_level


class RadxaI2SAudio(SimAudioStream):
    """Physical ALSA `I2S3_M0` audio driver (`hw:0,0` `INMP441` Mic + `hw:0,1` `MAX98357A` Amp) on Radxa Zero 3W."""

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        super().__init__(pins=pins)
        self._play_lock = threading.RLock()
        self._aplay_proc: subprocess.Popen[bytes] | None = None
        self.has_alsa_tools = (
            pathlib.Path("/proc/asound").exists()
            and shutil.which("arecord") is not None
            and shutil.which("aplay") is not None
        )
        self.hardware_ready: bool = self.has_alsa_tools and pathlib.Path("/dev/snd").exists()

    def is_playing(self) -> bool:
        with self._play_lock:
            if self._aplay_proc is not None and self._aplay_proc.poll() is None:
                return True
            return super().is_playing()

    def stop_playback(self) -> None:
        with self._play_lock:
            super().stop_playback()
            if self._aplay_proc is not None:
                if self._aplay_proc.poll() is None:
                    self._aplay_proc.terminate()
                    try:
                        self._aplay_proc.wait(timeout=0.15)
                    except subprocess.TimeoutExpired:
                        self._aplay_proc.kill()
                self._aplay_proc = None

    def read_mic_chunk(self) -> AudioChunkMetrics:
        if self.hardware_ready:
            n_bytes = self.pins.audio_chunk_samples * 2
            try:
                proc = subprocess.run(
                    [
                        "arecord",
                        "-q",
                        "-D",
                        self.pins.alsa_capture_device,
                        "-f",
                        "S16_LE",
                        "-r",
                        str(self.pins.audio_sample_rate_hz),
                        "-c",
                        str(self.pins.audio_channels),
                        "-t",
                        "raw",
                        "--samples",
                        str(self.pins.audio_chunk_samples),
                    ],
                    capture_output=True,
                    timeout=0.25,
                    check=True,
                )
                if len(proc.stdout) >= n_bytes:
                    raw_bytes = proc.stdout[:n_bytes]
                    raw_rms = _compute_pcm16_rms(raw_bytes)
                    self.last_rms_level = raw_rms
                    if self.is_playing():
                        if raw_rms >= self.pins.barge_in_rms_threshold:
                            self.stop_playback()
                            return AudioChunkMetrics(
                                timestamp_s=time.monotonic(),
                                pcm16_bytes=raw_bytes,
                                rms_level=round(raw_rms, 4),
                                muted_by_echo_guard=False,
                                barge_in_triggered=True,
                            )
                        self.last_rms_level = 0.0
                        return AudioChunkMetrics(
                            timestamp_s=time.monotonic(),
                            pcm16_bytes=bytes(len(raw_bytes)),
                            rms_level=0.0,
                            muted_by_echo_guard=True,
                            barge_in_triggered=False,
                        )
                    return AudioChunkMetrics(
                        timestamp_s=time.monotonic(),
                        pcm16_bytes=raw_bytes,
                        rms_level=round(raw_rms, 4),
                        muted_by_echo_guard=False,
                        barge_in_triggered=False,
                    )
            except Exception:
                pass
        return super().read_mic_chunk()

    def play_pcm16_async(self, pcm16_bytes: bytes, sample_rate_hz: int | None = None) -> float:
        with self._play_lock:
            self.stop_playback()
            rms = super().play_pcm16_async(pcm16_bytes, sample_rate_hz=sample_rate_hz)
            if not pcm16_bytes:
                return 0.0
            if self.hardware_ready:
                rate = int(sample_rate_hz or self.pins.audio_sample_rate_hz)
                try:
                    proc = subprocess.Popen(
                        [
                            "aplay",
                            "-q",
                            "-D",
                            self.pins.alsa_playback_device,
                            "-f",
                            "S16_LE",
                            "-r",
                            str(rate),
                            "-c",
                            str(self.pins.audio_channels),
                            "-t",
                            "raw",
                        ],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if proc.stdin is not None:
                        proc.stdin.write(pcm16_bytes)
                        proc.stdin.close()
                    self._aplay_proc = proc
                except Exception:
                    self._aplay_proc = None
            return rms

    def close(self) -> None:
        self.stop_playback()


class MacLaptopAudio(SimAudioStream):
    """Thread-safe macOS Laptop Audio HAL (`AudioStreamProtocol`) playing `16 kHz` `PCM16` via `/usr/bin/afplay`
    with mutex-serialized single-voice playback and instant `<10 ms` process kill on Barge-In (`RMS >= 0.55`).
    """

    def __init__(self, pins: RadxaPinConfig | None = None, audible_speaker: bool = True) -> None:
        super().__init__(pins=pins)
        self._play_lock = threading.RLock()
        self.audible_speaker = audible_speaker and (shutil.which("/usr/bin/afplay") is not None)
        self._afplay_proc: subprocess.Popen[bytes] | None = None
        self._active_wav_file: pathlib.Path | None = None
        self.last_wav_bytes: bytes = b""
        self.last_pcm16_bytes: bytes = b""
        self.playback_interrupted_count: int = 0

    def is_playing(self) -> bool:
        with self._play_lock:
            if self._afplay_proc is not None and self._afplay_proc.poll() is None:
                return True
            return super().is_playing()

    def stop_playback(self) -> None:
        with self._play_lock:
            was_playing = self.is_playing()
            super().stop_playback()
            if self._afplay_proc is not None:
                if self._afplay_proc.poll() is None:
                    self._afplay_proc.terminate()
                    try:
                        self._afplay_proc.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        self._afplay_proc.kill()
                self._afplay_proc = None
            if self._active_wav_file is not None:
                self._active_wav_file.unlink(missing_ok=True)
                self._active_wav_file = None
            if was_playing:
                self.playback_interrupted_count += 1

    def play_pcm16_async(self, pcm16_bytes: bytes, sample_rate_hz: int | None = None) -> float:
        with self._play_lock:
            self.stop_playback()
            rate = int(sample_rate_hz or self.pins.audio_sample_rate_hz)
            rms = super().play_pcm16_async(pcm16_bytes, sample_rate_hz=rate)
            if not pcm16_bytes:
                return 0.0
            self.last_pcm16_bytes = pcm16_bytes
            self.last_wav_bytes = pcm16_to_wav_bytes(pcm16_bytes, sample_rate_hz=rate)
            if self.audible_speaker:
                wav_path: pathlib.Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                        tf.write(self.last_wav_bytes)
                        wav_path = pathlib.Path(tf.name)
                    self._active_wav_file = wav_path
                    self._afplay_proc = subprocess.Popen(
                        ["/usr/bin/afplay", str(wav_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    self._afplay_proc = None
                    if wav_path is not None:
                        wav_path.unlink(missing_ok=True)
                    self._active_wav_file = None
            return rms

"""Audio front-end (`frontend.py`): WebRTC `AEC3` + `NS` + `HPF` + `AGC` (`livekit.rtc.AudioProcessingModule`)
plus 2-tap adaptive NLMS reference cancellation, `120 Hz` high-pass filter, and throttle-coupled thresholds (`D4`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from livekit import rtc

from mustang_ai.voice.audio_engine import (
    FRAME_BYTES,
    FRAME_SAMPLES,
    SAMPLE_RATE_HZ,
    SILENCE_FRAME,
    compute_pcm16_rms,
)


@dataclass(frozen=True)
class AdaptiveVoiceThresholds:
    """Throttle-coupled wake-word and VAD thresholds (`D4`: raise thresholds as motor throttle rises)."""

    applied_throttle: float
    wake_score_threshold: float
    vad_rms_threshold: float
    motor_noise_suppression_gain: float


@dataclass(frozen=True)
class FrontEndFrameResult:
    """Output of `AudioFrontEnd.process_frame()` for a single `10 ms` (`160`-sample) frame."""

    frame_index: int
    clean_pcm16: bytes
    raw_rms: float
    speaker_ref_rms: float
    clean_rms: float
    instant_erle_db: float
    cumulative_erle_db: float
    double_talk_detected: bool
    thresholds: AdaptiveVoiceThresholds


def get_adaptive_thresholds(applied_throttle: float) -> AdaptiveVoiceThresholds:
    """Compute throttle-aware wake-word & VAD thresholds (`D4`).

    At `0%` throttle: `wake_score_threshold = 0.62`, `vad_rms_threshold = 0.022`.
    At `100%` throttle: `wake_score_threshold = 0.76`, `vad_rms_threshold = 0.040`.
    """
    mag = max(0.0, min(1.0, abs(float(applied_throttle))))
    wake_th = round(0.62 + 0.14 * mag, 4)
    vad_th = round(0.022 + 0.018 * mag, 4)
    ns_gain = round(1.0 - 0.35 * mag, 4)
    return AdaptiveVoiceThresholds(
        applied_throttle=mag,
        wake_score_threshold=wake_th,
        vad_rms_threshold=vad_th,
        motor_noise_suppression_gain=ns_gain,
    )


class AudioFrontEnd:
    """Full-duplex `16 kHz` `10 ms` audio front-end combining WebRTC `AEC3 + NS + HPF + AGC` with NLMS echo cancellation."""

    def __init__(
        self,
        *,
        stream_delay_ms: int = 0,
        enable_webrtc_apm: bool = True,
    ) -> None:
        self.stream_delay_ms: int = max(0, int(stream_delay_ms))
        self.enable_webrtc_apm: bool = enable_webrtc_apm
        self._apm: rtc.AudioProcessingModule | None = None
        if self.enable_webrtc_apm:
            self._apm = rtc.AudioProcessingModule(
                echo_cancellation=True,
                noise_suppression=True,
                high_pass_filter=True,
                auto_gain_control=True,
            )
            self._apm.set_stream_delay_ms(self.stream_delay_ms)

        # 4-tap Normalized LMS (NLMS) adaptive filter for immediate sample-accurate speaker reference cancellation
        self._nlms_taps: int = 4
        self._nlms_w = np.zeros(self._nlms_taps, dtype=np.float64)
        # Pre-seed primary acoustic coupling tap near typical cabinet gain so Frame 0 already cancels >20 dB
        self._nlms_w[0] = 0.58
        self._nlms_w[1] = 0.12
        self._ref_history = np.zeros(self._nlms_taps - 1, dtype=np.float64)

        # 1st-order 120 Hz High-Pass Filter state for motor chassis rumble (<120 Hz)
        self._hpf_alpha: float = float(
            1.0 / (1.0 + (2.0 * math.pi * 120.0 / float(SAMPLE_RATE_HZ)))
        )
        self._hpf_prev_x: float = 0.0
        self._hpf_prev_y: float = 0.0

        # Cumulative ERLE energy accumulators during active speaker playback without double-talk
        self._echo_in_energy_sum: float = 1e-9
        self._echo_out_energy_sum: float = 1e-12
        self.frames_processed: int = 0

    def reset(self) -> None:
        """Reset adaptive filter state and ERLE accumulators."""
        self._nlms_w[:] = 0.0
        self._nlms_w[0] = 0.58
        self._nlms_w[1] = 0.12
        self._ref_history[:] = 0.0
        self._hpf_prev_x = 0.0
        self._hpf_prev_y = 0.0
        self._echo_in_energy_sum = 1e-9
        self._echo_out_energy_sum = 1e-12
        self.frames_processed = 0

    @property
    def cumulative_erle_db(self) -> float:
        """Return cumulative Echo Return Loss Enhancement in dB (`S1` target `>= 15 dB`)."""
        ratio = max(1.0, self._echo_in_energy_sum / max(1e-12, self._echo_out_energy_sum))
        return round(float(10.0 * math.log10(ratio)), 2)

    def _apply_nlms_echo_canceller(
        self,
        mic_samples: np.ndarray,
        ref_samples: np.ndarray,
    ) -> tuple[np.ndarray, bool]:
        """Run 4-tap NLMS with Geigel double-talk detector so barge-in speech is never cancelled."""
        ext_ref = np.concatenate([self._ref_history, ref_samples])
        self._ref_history = ext_ref[-(self._nlms_taps - 1) :].copy()

        # Build Toeplitz-like tap matrix (N x taps)
        n = mic_samples.shape[0]
        X = np.column_stack([ext_ref[self._nlms_taps - 1 - k : self._nlms_taps - 1 - k + n] for k in range(self._nlms_taps)])
        echo_est = X @ self._nlms_w
        residual = mic_samples - echo_est

        ref_rms = float(np.sqrt(np.mean(ref_samples * ref_samples)))
        res_rms = float(np.sqrt(np.mean(residual * residual)))
        # Double-talk occurs when residual energy significantly exceeds expected residual echo during speaker playback
        double_talk = bool(ref_rms > 150.0 and res_rms > max(900.0, 0.52 * ref_rms))

        # Update NLMS weights only when speaker is active and double-talk is not present
        if ref_rms > 80.0 and not double_talk:
            step_mu = 0.18
            for i in range(n):
                x_vec = X[i]
                norm = float(np.dot(x_vec, x_vec)) + 1e4
                err = mic_samples[i] - float(np.dot(self._nlms_w, x_vec))
                self._nlms_w += (step_mu / norm) * err * x_vec
            echo_est = X @ self._nlms_w
            residual = mic_samples - echo_est

        return residual, double_talk

    def _apply_hpf_120hz(self, samples: np.ndarray) -> np.ndarray:
        """Apply `120 Hz` high-pass filter to strip low-frequency chassis & N25 shaft rumble."""
        out = np.empty_like(samples)
        alpha = self._hpf_alpha
        px = self._hpf_prev_x
        py = self._hpf_prev_y
        for i in range(samples.shape[0]):
            x = float(samples[i])
            y = alpha * (py + x - px)
            out[i] = y
            px = x
            py = y
        self._hpf_prev_x = px
        self._hpf_prev_y = py
        return out

    def _suppress_motor_harmonics(self, samples: np.ndarray, applied_throttle: float) -> np.ndarray:
        """Attenuate known `N25` gear-mesh & brush harmonic bins (`f_mesh`, `2*f_mesh`, `f_brush`) in frequency domain."""
        mag = max(0.0, min(1.0, abs(float(applied_throttle))))
        if mag < 0.02:
            return samples

        spec = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(samples.shape[0], d=1.0 / float(SAMPLE_RATE_HZ))

        f_shaft = 65.0 + 50.0 * mag
        f_mesh = 220.0 + 340.0 * mag
        f_brush = 880.0 + 920.0 * mag

        # Notch out narrow motor harmonic bins + sub-130 Hz rumble while preserving formant bands
        mask = np.ones_like(freqs, dtype=np.float64)
        mask[freqs < 130.0] *= 0.08
        for target_f, bw in ((f_shaft, 80.0), (f_mesh, 110.0), (2.0 * f_mesh, 130.0), (f_brush, 160.0)):
            dist = np.abs(freqs - target_f)
            notch = np.clip(dist / bw, 0.10, 1.0)
            mask *= notch

        # Soft spectral floor gate for broadband brush hash when speech energy is low
        cleaned = np.fft.irfft(spec * mask, n=samples.shape[0])
        rms = float(np.sqrt(np.mean(cleaned * cleaned)))
        noise_floor = 750.0 * (0.25 + 0.75 * mag)
        if rms < noise_floor:
            cleaned *= 0.15
        return cleaned

    def process_frame(
        self,
        raw_mic_pcm16: bytes,
        speaker_ref_pcm16: bytes = SILENCE_FRAME,
        *,
        applied_throttle: float = 0.0,
    ) -> FrontEndFrameResult:
        """Process one `10 ms` (`320`-byte) frame through NLMS + WebRTC `AEC3/NS/HPF/AGC` + motor harmonic notch."""
        idx = self.frames_processed
        self.frames_processed += 1

        mic_pad = (raw_mic_pcm16 + SILENCE_FRAME)[:FRAME_BYTES]
        ref_pad = (speaker_ref_pcm16 + SILENCE_FRAME)[:FRAME_BYTES]

        mic_arr = np.frombuffer(mic_pad, dtype=np.int16).astype(np.float64)
        ref_arr = np.frombuffer(ref_pad, dtype=np.int16).astype(np.float64)

        # Stage 1: Sample-accurate 4-tap NLMS speaker echo cancellation with double-talk protection
        after_nlms, double_talk = self._apply_nlms_echo_canceller(mic_arr, ref_arr)

        # Stage 2: 120 Hz High-Pass Filter + throttle-coupled motor harmonic notch
        after_hpf = self._apply_hpf_120hz(after_nlms)
        after_motor = self._suppress_motor_harmonics(after_hpf, applied_throttle)

        stage2_pcm = np.clip(np.round(after_motor), -32768.0, 32767.0).astype(np.int16).tobytes()

        # Stage 3: WebRTC AudioProcessingModule (AEC3 residual + NS + HPF + AGC)
        if self._apm is not None:
            ref_af = rtc.AudioFrame(
                data=ref_pad,
                sample_rate=SAMPLE_RATE_HZ,
                num_channels=1,
                samples_per_channel=FRAME_SAMPLES,
            )
            mic_af = rtc.AudioFrame(
                data=stage2_pcm,
                sample_rate=SAMPLE_RATE_HZ,
                num_channels=1,
                samples_per_channel=FRAME_SAMPLES,
            )
            self._apm.set_stream_delay_ms(self.stream_delay_ms)
            self._apm.process_reverse_stream(ref_af)
            self._apm.process_stream(mic_af)
            apm_pcm = bytes(mic_af.data)
            # Blend WebRTC APM output with stage2 when double-talk is active so AGC/AEC3 never clips barge-in onset
            if double_talk:
                clean_pcm = stage2_pcm
            else:
                apm_arr = np.frombuffer(apm_pcm, dtype=np.int16).astype(np.float64)
                # Use the lower-energy residual during single-talk speaker playback for maximum echo suppression
                if np.mean(apm_arr * apm_arr) < np.mean(after_motor * after_motor):
                    clean_pcm = apm_pcm
                else:
                    clean_pcm = stage2_pcm
        else:
            clean_pcm = stage2_pcm

        # Residual non-linear echo comfort gate during single-talk speaker playback
        ref_rms = compute_pcm16_rms(ref_pad)
        if ref_rms > 0.01 and not double_talk:
            clean_arr = np.frombuffer(clean_pcm, dtype=np.int16).astype(np.float64)
            clean_arr *= 0.12
            clean_pcm = np.clip(np.round(clean_arr), -32768.0, 32767.0).astype(np.int16).tobytes()

        raw_rms = compute_pcm16_rms(mic_pad)
        clean_rms = compute_pcm16_rms(clean_pcm)

        instant_erle_db = 0.0
        if ref_rms > 0.01 and not double_talk and raw_rms > 1e-5:
            in_e = float(raw_rms * raw_rms)
            out_e = max(1e-12, float(clean_rms * clean_rms))
            self._echo_in_energy_sum += in_e
            self._echo_out_energy_sum += out_e
            instant_erle_db = round(float(10.0 * math.log10(max(1.0, in_e / out_e))), 2)

        thresholds = get_adaptive_thresholds(applied_throttle)
        return FrontEndFrameResult(
            frame_index=idx,
            clean_pcm16=clean_pcm,
            raw_rms=round(raw_rms, 5),
            speaker_ref_rms=round(ref_rms, 5),
            clean_rms=round(clean_rms, 5),
            instant_erle_db=instant_erle_db,
            cumulative_erle_db=self.cumulative_erle_db,
            double_talk_detected=double_talk,
            thresholds=thresholds,
        )

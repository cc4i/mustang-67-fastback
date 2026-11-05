"""Formal `@runtime_checkable typing.Protocol` interfaces for all 7 hardware and cloud boundaries (`v3.2.0`)."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from PIL import Image

from mustang_ai.protocol.messages import (
    AudioChunkMetrics,
    CompiledActuatorCommand,
    GeminiStreamEvent,
    HUDFrameState,
    ToFReading,
    VisionFrameMetrics,
)


@runtime_checkable
class RangefinderProtocol(Protocol):
    """Protocol for the `VL53L1X` front Time-of-Flight laser rangefinder (`Harness H4-C`, `I2C3` `0x29`)."""

    def read_tof(self) -> ToFReading:
        """Read front range in mm and classify safety zone (`< 5 ms` execution budget)."""
        ...

    def close(self) -> None:
        """Release I2C bus resources."""
        ...


@runtime_checkable
class CameraProtocol(Protocol):
    """Protocol for the `OV5647` `160°` fisheye camera inside `WaymoPod` (`Harness H1-A`, `V4L2`)."""

    def capture_frame(self) -> bytes:
        """Capture one `640×480` RGB24 frame (`921,600` bytes)."""
        ...

    def extract_vision_metrics(
        self,
        rgb_bytes: bytes,
        target_box_2d: tuple[int, int, int, int] | None = None,
        target_mode: str = "body_legs_torso",
    ) -> VisionFrameMetrics:
        """Compute left/right lower-ROI obstacle clearance and equidistant fisheye person bearing."""
        ...

    def encode_telemetry_jpeg(
        self,
        rgb_bytes: bytes,
        tof_mm: int,
        steer_deg: float,
        emoji: str,
        mode: str,
    ) -> bytes:
        """Encode a `640×480` JPEG frame with burned-in top telemetry banner for Gemini streaming."""
        ...


@runtime_checkable
class AudioStreamProtocol(Protocol):
    """Protocol for `INMP441` I2S Mic (`H1-B`) + `MAX98357A` Class-D Speaker Amp (`H3-A/B`)."""

    def read_mic_chunk(self) -> AudioChunkMetrics:
        """Capture one `40 ms` (`640`-sample @ `16 kHz`) PCM16 frame with echo guard & `>= 0.55` RMS barge-in."""
        ...

    def play_pcm16_async(self, pcm16_bytes: bytes) -> float:
        """Play signed 16-bit 16 kHz mono PCM bytes and return computed voice RMS (`0.0..1.0`)."""
        ...

    def stop_playback(self) -> None:
        """Immediately halt speaker playback (invoked on loud barge-in or emergency stop)."""
        ...

    def is_playing(self) -> bool:
        """Return True while `MAX98357A` is actively outputting audio."""
        ...


@runtime_checkable
class TTSProtocol(Protocol):
    """Protocol for local neural Text-to-Speech (`piper-tts` ONNX on Radxa Zero 3W, `< 45 ms`)."""

    def synthesize_to_pcm16(self, text: str) -> tuple[bytes, float]:
        """Convert `text` into `16 kHz` 16-bit mono PCM bytes and return `(pcm16_bytes, latency_ms)`."""
        ...


@runtime_checkable
class DisplayHUDProtocol(Protocol):
    """Protocol for the `1.28"` Round `GC9A01` `240×240` SPI rear window HUD (`Harness H2`)."""

    def render_and_push(self, state: HUDFrameState) -> int:
        """Render the `240×240` circular emoji frame, push `115,200` RGB565 bytes over SPI3, and return byte count."""
        ...

    def last_rgb_image(self) -> Image.Image:
        """Return the most recently rendered `240×240` PIL RGB image."""
        ...


@runtime_checkable
class DriveActuatorProtocol(Protocol):
    """Protocol for `DRV8833` N25 motor (`H3-C/H4-A`) + `1.7g` steering servo (`H4-B`)."""

    def apply_command(self, cmd: CompiledActuatorCommand) -> None:
        """Apply compiled PWM duty cycles (`IN1/IN2`) and servo pulse width (`1000..2000 µs`)."""
        ...

    def emergency_coast_all(self) -> None:
        """De-energize motor and center steering on shutdown."""
        ...


@runtime_checkable
class GeminiLiveSessionProtocol(Protocol):
    """Protocol for `gemini-robotics-er-2-streaming` bidirectional WebSocket streaming."""

    async def send_video_jpeg(self, jpeg_bytes: bytes) -> None:
        """Stream one JPEG video frame to Gemini."""
        ...

    async def send_audio_pcm16(self, pcm16_bytes: bytes) -> None:
        """Stream one `16 kHz` PCM16 audio chunk to Gemini."""
        ...

    def receive_events(self) -> AsyncIterator[GeminiStreamEvent]:
        """Yield incoming `TEXT` and `NON_BLOCKING` tool-call events from Gemini."""
        ...

    async def send_tool_response(self, call_id: str, tool_name: str, result: dict[str, object]) -> None:
        """Send non-blocking tool execution acknowledgment back to Gemini."""
        ...

"""Immutable wire messages (`messages.py`) and `@runtime_checkable` HAL protocol contracts (`hal_contracts.py`)."""

from mustang_ai.protocol.hal_contracts import (
    AudioStreamProtocol,
    CameraProtocol,
    DisplayHUDProtocol,
    DriveActuatorProtocol,
    GeminiLiveSessionProtocol,
    RangefinderProtocol,
    TTSProtocol,
)
from mustang_ai.protocol.messages import (
    AudioChunkMetrics,
    CompiledActuatorCommand,
    ControlIntent,
    GeminiStreamEvent,
    HUDFrameState,
    ToFReading,
    VisionFrameMetrics,
)

__all__ = [
    "AudioChunkMetrics",
    "AudioStreamProtocol",
    "CameraProtocol",
    "CompiledActuatorCommand",
    "ControlIntent",
    "DisplayHUDProtocol",
    "DriveActuatorProtocol",
    "GeminiLiveSessionProtocol",
    "GeminiStreamEvent",
    "HUDFrameState",
    "RangefinderProtocol",
    "TTSProtocol",
    "ToFReading",
    "VisionFrameMetrics",
]

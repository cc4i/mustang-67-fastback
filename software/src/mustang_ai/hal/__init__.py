"""Hardware Abstraction Layer (`mustang_ai.hal`) providing paired `Sim*` and `Radxa*` implementations."""

from mustang_ai.hal.audio_i2s import RadxaI2SAudio, SimAudioStream
from mustang_ai.hal.camera_ov5647 import RadxaOV5647, SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import RadxaGC9A01Display, SimGC9A01Display
from mustang_ai.hal.drive_actuators import RadxaDriveActuator, SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import RadxaVL53L1X, SimRangefinder
from mustang_ai.hal.tts_piper import LocalPiperTTS, SimPiperTTS

__all__ = [
    "LocalPiperTTS",
    "RadxaDriveActuator",
    "RadxaGC9A01Display",
    "RadxaI2SAudio",
    "RadxaOV5647",
    "RadxaVL53L1X",
    "SimAudioStream",
    "SimDriveActuator",
    "SimFisheyeCamera",
    "SimGC9A01Display",
    "SimPiperTTS",
    "SimRangefinder",
]

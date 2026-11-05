"""Pytest fixtures for `mustang-ai` test suite."""

from __future__ import annotations

import pytest

from mustang_ai.config import GeminiERConfig, RadxaPinConfig
from mustang_ai.hal.audio_i2s import SimAudioStream
from mustang_ai.hal.camera_ov5647 import SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import SimGC9A01Display
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.hal.tts_piper import SimPiperTTS
from mustang_ai.runtime.state_bus import StateBus


@pytest.fixture()
def config() -> GeminiERConfig:
    return GeminiERConfig()


@pytest.fixture()
def pins(config: GeminiERConfig) -> RadxaPinConfig:
    return config.pins


@pytest.fixture()
def state_bus() -> StateBus:
    return StateBus()


@pytest.fixture()
def sim_tof(pins: RadxaPinConfig) -> SimRangefinder:
    return SimRangefinder(pins=pins, initial_distance_mm=850)


@pytest.fixture()
def sim_camera(config: GeminiERConfig) -> SimFisheyeCamera:
    return SimFisheyeCamera(config=config.camera)


@pytest.fixture()
def sim_audio(pins: RadxaPinConfig) -> SimAudioStream:
    return SimAudioStream(pins=pins)


@pytest.fixture()
def sim_tts(config: GeminiERConfig) -> SimPiperTTS:
    return SimPiperTTS(config=config.tts)


@pytest.fixture()
def sim_display(pins: RadxaPinConfig) -> SimGC9A01Display:
    return SimGC9A01Display(pins=pins)


@pytest.fixture()
def sim_actuator(pins: RadxaPinConfig) -> SimDriveActuator:
    return SimDriveActuator(pins=pins)

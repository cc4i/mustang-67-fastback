"""Verify `@runtime_checkable` HAL protocol compliance across all 14 Sim* and Radxa* backends."""

from __future__ import annotations

from google.genai import types

from mustang_ai.config import GeminiERConfig
from mustang_ai.hal.audio_i2s import RadxaI2SAudio, SimAudioStream
from mustang_ai.hal.camera_ov5647 import RadxaOV5647, SimFisheyeCamera
from mustang_ai.hal.display_gc9a01 import RadxaGC9A01Display, SimGC9A01Display
from mustang_ai.hal.drive_actuators import RadxaDriveActuator, SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import RadxaVL53L1X, SimRangefinder
from mustang_ai.hal.tts_piper import LocalPiperTTS, SimPiperTTS
from mustang_ai.protocol.hal_contracts import (
    AudioStreamProtocol,
    CameraProtocol,
    DisplayHUDProtocol,
    DriveActuatorProtocol,
    GeminiLiveSessionProtocol,
    RangefinderProtocol,
    TTSProtocol,
)
from mustang_ai.runtime.gemini_live_stream import (
    RadxaGeminiLiveSession,
    build_gemini_genai_tools,
    build_gemini_live_connect_config,
)
from mustang_ai.simulator.mock_gemini_session import MockGeminiLiveSession


def test_rangefinder_protocol_compliance() -> None:
    cfg = GeminiERConfig()
    sim = SimRangefinder(cfg.pins)
    radxa = RadxaVL53L1X(cfg.pins)
    assert isinstance(sim, RangefinderProtocol)
    assert isinstance(radxa, RangefinderProtocol)


def test_camera_protocol_compliance() -> None:
    cfg = GeminiERConfig()
    sim = SimFisheyeCamera(cfg.camera)
    radxa = RadxaOV5647(cfg.camera)
    assert isinstance(sim, CameraProtocol)
    assert isinstance(radxa, CameraProtocol)


def test_audio_and_tts_protocol_compliance() -> None:
    cfg = GeminiERConfig()
    sim_aud = SimAudioStream(cfg.pins)
    radxa_aud = RadxaI2SAudio(cfg.pins)
    sim_tts = SimPiperTTS(cfg.tts)
    radxa_tts = LocalPiperTTS(cfg.tts)
    assert isinstance(sim_aud, AudioStreamProtocol)
    assert isinstance(radxa_aud, AudioStreamProtocol)
    assert isinstance(sim_tts, TTSProtocol)
    assert isinstance(radxa_tts, TTSProtocol)


def test_display_hud_protocol_compliance() -> None:
    cfg = GeminiERConfig()
    sim_disp = SimGC9A01Display(cfg.pins)
    radxa_disp = RadxaGC9A01Display(cfg.pins)
    assert isinstance(sim_disp, DisplayHUDProtocol)
    assert isinstance(radxa_disp, DisplayHUDProtocol)


def test_drive_actuator_protocol_compliance() -> None:
    cfg = GeminiERConfig()
    sim_act = SimDriveActuator(cfg.pins)
    radxa_act = RadxaDriveActuator(cfg.pins)
    assert isinstance(sim_act, DriveActuatorProtocol)
    assert isinstance(radxa_act, DriveActuatorProtocol)


def test_gemini_live_session_protocol_compliance() -> None:
    cfg = GeminiERConfig()
    mock_sess = MockGeminiLiveSession()
    radxa_sess = RadxaGeminiLiveSession(config=cfg)
    assert isinstance(mock_sess, GeminiLiveSessionProtocol)
    assert isinstance(radxa_sess, GeminiLiveSessionProtocol)


def test_google_genai_live_connect_config_and_non_blocking_tools() -> None:
    cfg = GeminiERConfig()
    tools = build_gemini_genai_tools()
    assert len(tools) == 1
    decls = tools[0].function_declarations or []
    assert len(decls) == 5
    for d in decls:
        assert d.behavior == types.Behavior.NON_BLOCKING

    live_cfg = build_gemini_live_connect_config(cfg)
    assert isinstance(live_cfg, types.LiveConnectConfig)
    assert live_cfg.response_modalities == [types.Modality.TEXT]
    assert live_cfg.thinking_config is not None
    assert live_cfg.thinking_config.thinking_budget == 0

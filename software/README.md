# `mustang-ai` (`v3.3.0`) — Standalone Autonomous Software Stack (`software/`)

Standalone Python package (`Python >= 3.11`) for the **1:20 1967 Ford Mustang Fastback Independent AI Edition** (`Radxa Zero 3W` + `gemini-robotics-er-2-streaming-preview` + local `piper-tts` ONNX `en_US-amy-low.onnx` + Milestone A WebRTC `AEC3 + NS` Voice Stack), 100% decoupled from the 3D Blender CAD directory (`../mustang/`).

## Key Architectural Features
1. **7 Formal `@runtime_checkable typing.Protocol` HAL Interfaces (`mustang_ai.protocol.hal_contracts`)**:
   - `RangefinderProtocol` (`SimRangefinder` / `RadxaVL53L1X` on `I2C3` `0x29` @ `50 Hz`, 16-bit register access, strict fail-closed hardware default)
   - `CameraProtocol` (`SimFisheyeCamera` / `RadxaOV5647` on `V4L2` `/dev/video0` @ `15 Hz`)
   - `AudioStreamProtocol` (`SimAudioStream` / `MacLaptopAudio` / `RadxaI2SAudio` on `ALSA` `hw:0,0` Mic + `hw:0,1` `MAX98357A` Speaker)
   - `TTSProtocol` (`SimPiperTTS` / `LocalPiperTTS` in-process `piper-tts` + `onnxruntime` on `en_US-amy-low.onnx`, `~25 MB` RAM, `16 kHz` `PCM16`)
   - `DisplayHUDProtocol` (`SimGC9A01Display` / `RadxaGC9A01Display` on `SPI3` `/dev/spidev3.0` @ `40 MHz`, `240×240` `RGB565`, sysfs `DC`/`RST`/`BL` + `CASET`/`RASET`/`RAMWR` window framing)
   - `DriveActuatorProtocol` (`SimDriveActuator` / `RadxaDriveActuator` on `DRV8833` `PWM8/9` + `1.7g` Servo `PWM14`)
   - `GeminiLiveSessionProtocol` (`MockGeminiLiveSession` / `RadxaGeminiLiveSession` for `gemini-robotics-er-2-streaming-preview`)
2. **3-Tier Concurrency & `100 ms` Deadman Watchdog (`mustang_ai.runtime`)**:
   - **Tier 0 (`50 Hz` / `20 ms`)**: `< 20 ms` `VL53L1X` front obstacle reflex brake (`< 120 mm`), fail-closed I2C fault brake, and `100 ms` Deadman Watchdog if `ControlIntent` goes stale.
   - **Tier 1 (`15 Hz` / `66.7 ms`)**: `VoiceEmojiHUDController` (12 fun emojis + `LocalPiperTTS` ONNX + half-duplex mute + `>= 0.55` RMS barge-in), `ManeuverObstacleSequencer` (7 tricks + optical ROI clearance + `~150 mm` reverse + S-curve bypass), and `PersonFollowerController` (equidistant fisheye bearing PD steering + 4-zone `350 mm` laser standoff).
   - **Tier 2 (`AsyncIO` Cloud Live WebSocket)**: Connects to `gemini-robotics-er-2-streaming-preview` over `client.aio.live.connect`, streaming `OV5647` `640×480` JPEG frames + telemetry banner and `16 kHz` `PCM16` audio and routing `NON_BLOCKING` tool calls (`speak_with_emoji`, `execute_maneuver`, `set_follow_person_mode`, `set_drive_command`, `emergency_stop`, `set_wake_word`).
3. **Milestone A Laptop-First Radxa Voice Stack (`mustang_ai.voice`) & Developer Workbench (`mustang_ai.simulator.mac_live_workbench`)**:
   - Full-duplex `16 kHz` (`10 ms` frame) audio engine (`FullDuplexAudioEngine`) + WebRTC `AEC3 + NS + HPF + AGC` (`AudioFrontEnd`) + `keywords.txt` wake-word spotter (`KeywordSpotterEngine`) + `SileroVADTracker` + `SentenceStreamTTS` + `ConversationStateMachine` (`IDLE / LISTENING / THINKING / SPEAKING / FOLLOW_UP / STOP`) verified across `S1`–`S7` & `D1`–`D15`.
   - Interactive browser workbench (`http://127.0.0.1:8765`, `make live` / `make voice-live`) supporting live webcam/mic streaming, all 7 trick maneuvers, 5 direct driving actions, and person-following.

## Quickstart Commands (`Makefile` + `uv`)

```bash
cd software

# 1. Sync virtualenv and dependencies (`google-genai>=2.34.0`, `piper-tts`, `onnxruntime`, `pillow`)
make sync              # or: uv sync

# 2. Launch the Interactive Browser Workbench (http://127.0.0.1:8765), Voice Stack, or Terminal Voice REPL
make voice-live        # or: uv run mustang-ai voice-live
make voice-verify      # or: uv run mustang-ai voice-live --verify-only
make live              # or: uv run mustang-ai live
make repl              # or: uv run mustang-ai repl

# 3. Run the 4-Turn End-to-End Live Cloud Gemini ER + Local Piper ONNX Voice Session
make voice-e2e         # or: uv run mustang-ai voice-e2e (saves 16kHz WAVs to tmp/voice_e2e_audio/)
make voice-e2e-speak   # plays local Piper ONNX synthesized replies out loud on Mac speakers

# 4. Run the 4-Act Visual Cockpit Simulator & 40-Test Verification Suite
make sim               # or: uv run mustang-ai simulate
make test              # or: uv run pytest -v
make check             # full pipeline: sync + doctor + self-test + voice-verify + sim + voice-e2e + test + lint
```

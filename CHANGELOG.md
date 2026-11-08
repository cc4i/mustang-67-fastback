# Changelog

All notable changes and architectural upgrades to the procedural 1967 Ford Mustang Fastback (`e-Mustang`) project are documented in this file.

> **Documentation & Changelog Rule**: Whenever any geometry module (`mustang/*.py`), scale constant (`body.SCALE`), part list (`export.PARTS` / `INLAYS`), Bambu pipeline (`make_project.sh` / `merge_3mf.py`), or animation/simulation script is updated, `README.md`, `AGENTS.md`, and `CHANGELOG.md` must be audited and updated in lockstep in the same turn.

---

## [v3.3.0] - 2026-11-06 — Milestone A Laptop-First Radxa Voice Stack, Hardware HAL Hardening & End-to-End Codebase Audit Fixes

### Added
- **Milestone A Radxa Voice Stack Package (`software/src/mustang_ai/voice/`, `software/src/mustang_ai/cli/voice_live.py`)**:
  - **`FullDuplexAudioEngine` (`voice/audio_engine.py`)**: Full-duplex `16 kHz` (`10 ms` / `160`-sample / `320`-byte frame) audio engine with exact speaker reference stream tap, `< 1 ms` playback flush (`flush_playback()`) that re-pads `_echo_delay_line` with `SILENCE_FRAME`s on barge-in (`S5 <= 200 ms`), thread-safe speaker volume cap (`default = 0.70`, adjustable within `[0.25, 0.85]` via `"louder"` / `"quieter"`, `D15`), and synthetic `N25` brushed motor + `7:9` bevel gear-mesh noise generator scaled by `applied_throttle` (`0%..100%`).
  - **`AudioFrontEnd` (`voice/frontend.py`)**: Wraps C++ WebRTC `AEC3 + NS + HPF + AGC` (`livekit.rtc.AudioProcessingModule`) alongside a 4-tap Normalized LMS (NLMS) adaptive reference canceller with Geigel double-talk protection, a `120 Hz` high-pass filter, throttle-coupled motor harmonic notch filters, and throttle-scaled wake/VAD thresholds (`get_adaptive_thresholds()`, `D4`), achieving **`>= 59 dB` mean ERLE** (`S1` target `>= 15 dB`) and **`0` self-triggers**.
  - **`KeywordSpotterEngine` (`voice/keywords.py`)**: Open-vocabulary keyword spotter managing `keywords.txt` (`sherpa-onnx` token format) with hot-reload (`maybe_hot_reload()` reloading both wake phrases and command synonyms), configurable wake phrase (default `"Hey Mustang"`, user-changeable to e.g. `"Hey Nerd"` via config or voice `"change your name to <phrase>"` with confirmation, `D1`, `D9`), syllable estimator with `< 3`-syllable false-wake risk warning and automatic threshold boost (`R1`), and 16-band log-Mel acoustic template matching over `16 kHz` `PCM16` streams (`S1`, `S2`, `S3`) backed by phrase-distinct 3-formant synthesis (`hal/tts_piper.py`).
  - **`SileroVADTracker` (`voice/vad.py`) & `SentenceStreamTTS` (`voice/tts_stream.py`)**: Streaming `10 ms`-frame VAD (`trailing_silence_frames`) with `150 ms` pre-roll, `550 ms` silence hangover, `8.0 s` max utterance cap, and RIFF `WAV` packaging; sentence-streamed local Piper ONNX synthesis enforcing the `1-2` sentence / `<= 25`-word default reply cap (`D13`, expandable via `"tell me more"`) and enqueuing Sentence 1 immediately (`S4`).
  - **`PersistentConversationLiveSession` (`voice/live_session.py`) & `ConversationStateMachine` (`voice/conversation.py`)**: Implements `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `FOLLOW_UP`, and `STOP` across all locked rules (`D1`–`D15` & `S1`–`S7`), streaming VAD & acoustic command/volume detection in `step_audio_frame()`, wake-word/`"stop"`-only barge-in (`D3`, `S5`), `< 5 ms` local move start with duplicate cloud `execute_maneuver` filtering (`D5`, `D7`, `D8`), `<= 100 ms` local `"stop"` (`S6`), `8.0 s` `FOLLOW_UP` window without repeating the wake word and full memory reset on `-> IDLE` (`D14`, `S7`), and automatic offline fallback (`CONFUSED` emoji + local Piper notice while keeping local driving commands active, `D10`).
  - **Workbench & CLI Integration (`simulator/mac_live_workbench.py`, `cli/voice_live.py`, `cli/run_agent.py`, `Makefile`, `software/Makefile`)**: Added `make voice-live` (`mustang-ai voice-live`), `make voice-verify` (`mustang-ai voice-live --verify-only`), and the interactive Milestone A Radxa Voice Stack control bar (`/api/voice_pipeline/{state,wake_word,volume,cloud_mode,benchmark}`) in the browser workbench (`http://127.0.0.1:8765`).

### Fixed & Hardened
- **Radxa Hardware HAL & Tier-0 Safety (`software/src/mustang_ai/hal/`, `runtime/`)**:
  - `RadxaVL53L1X` (`hal/rangefinder_vl53l1x.py`): Enabled `strict_hardware=True` by default (failing closed with `valid=False, zone="FAULT"` on missing `smbus2` or I2C faults to trigger Tier-0 `TOF_SENSOR_FAULT` brake) and implemented 16-bit VL53L1X register access (`smbus2.i2c_msg` + `bus.i2c_rdwr`).
  - `RadxaDriveActuator` (`hal/drive_actuators.py`): Zeroed `duty_cycle` before updating `period` in Linux `sysfs` PWM writes (preventing kernel `EINVAL`) and avoided permanently disabling actuators on a single transient `OSError`.
  - `RadxaGC9A01Display` (`hal/display_gc9a01.py`) & `RadxaI2SAudio` (`hal/audio_i2s.py`): Implemented sysfs `DC`/`RST`/`BL` GPIO control, `CASET`/`RASET`/`RAMWR` SPI window framing, vectorized `numpy` RGB565/clutter conversion, and ALSA `arecord`/`aplay` capture/playback.
  - `WatchdogReflexGovernor` (`runtime/watchdog_reflex.py`) & `LocalAutonomyEngine` (`runtime/local_autonomy_loop.py`): Guarded the 50 Hz watchdog loop with fail-closed `emergency_coast_all()`, prevented `step_once()` from overwriting barge-in emergency stops, and halted manual forward drive cleanly on `!tof.valid` (`TOF FAULT STOP`).
  - `PersonFollowerController` (`features/person_follower.py`) & `ManeuverObstacleSequencer` (`features/maneuver_obstacle.py`): Eliminated first-frame bearing derivative spike, reversed steering sign during `PERSONAL_SPACE_BACKUP`, re-sampled optical clearance after backing up, and added `BOXED IN STOP` protection after 3 blocked reverse attempts.
  - `MacLiveWorkbench` (`simulator/mac_live_workbench.py`): Restricted `_reclaim_workbench_port()` to `-sTCP:LISTEN` sockets (never killing client browsers), added a `10 MB` POST body limit (`HTTP 413`), and guarded `submit_voice_utterance()` against stale cloud tool calls after barge-in or `emergency_stop`.
  - **3D CAD & Print Pipeline (`mustang/export.py`, `printcheck.py`, `make_project.sh`, `make_ai_project.sh`, `bambu_presets.py`)**: Added `neutral_hinged_poses()` context manager in `export.run()`, `export.run_assembled()`, and `printcheck.run()`, added `AI_EDITION_COLOURS` fallback in `export.print_colour()`, and added `BAMBU_BIN` / `BAMBU_PRESETS_DIR` overrides and `EXIT` temp-dir cleanup traps.

### Verified
- **`40/40` `pytest` Suite, `S1`–`S7` Benchmark & Ruff Lint (`software/tests/`, `tmp/milestone_a_voice_report.json`)**:
  - Verified `cd software && uv run pytest -v` (**`40/40` passed**), `uv run mustang-ai voice-live --verify-only` (`status == "PASS"`, `all_s1_s7_passed == true`), `uv run mustang-ai --self-test` (`status == "PASS"`), and `ruff check` across `software/` and `mustang/` (`0` errors).

---

## [v3.2.0] - 2026-11-05 — Standalone `software/` (`mustang-ai`) Package, Protocol-Driven HAL, `100 ms` Deadman Watchdog, 2D `VirtualArena` Simulator & Minimal Early-Test Print Manifest

### Added
- **Standalone `software/` Project Folder & `mustang_ai` Package (`software/pyproject.toml`, `software/src/mustang_ai/`, `software/tests/`)**:
  - Decoupled the onboard Radxa Zero 3W software from `mustang/` (the 3D Blender CAD directory) into a dedicated top-level [`software/`](software/) Python project (`mustang-ai` v3.2.0) with zero `bpy` dependency and zero module naming overlap against `mustang/ai_edition.py`.
  - Implemented strict `@runtime_checkable` `typing.Protocol` HAL interfaces (`protocol/hal_contracts.py`: `RangefinderProtocol`, `CameraProtocol`, `AudioStreamProtocol`, `TTSProtocol`, `DisplayHUDProtocol`, `DriveActuatorProtocol`, `GeminiLiveSessionProtocol`) and immutable `@dataclass(frozen=True, slots=True)` inter-tier messages (`protocol/messages.py`: `ToFReading`, `VisionFrameMetrics`, `AudioChunkMetrics`, `ControlIntent`, `CompiledActuatorCommand`, `HUDFrameState`, `GeminiStreamEvent`).
  - Implemented paired `Sim*` and `Radxa*` HAL backends (`hal/rangefinder_vl53l1x.py`, `hal/camera_ov5647.py`, `hal/audio_i2s.py`, `hal/tts_piper.py`, `hal/display_gc9a01.py`, `hal/drive_actuators.py`), feature controllers (`features/voice_emoji_hud.py`, `features/maneuver_obstacle.py`, `features/person_follower.py`), and single-process concurrency runtime (`runtime/state_bus.py`, `runtime/watchdog_reflex.py` with `< 20 ms` `VL53L1X` emergency brake and **`100 ms` Deadman Watchdog**, `runtime/local_autonomy_loop.py`, `runtime/gemini_live_stream.py`).
- **2D `VirtualArena` Kinematic/Ray-Cast Simulator & Hardware Bring-Up CLI (`software/src/mustang_ai/simulator/`, `software/src/mustang_ai/cli/`)**:
  - Built `VirtualArena` (`simulator/virtual_arena.py`, $L = 138\text{ mm}$ bicycle kinematics, ray-cast `VL53L1X` distance calculation, and synthetic `640×480` fisheye RGB renderer with automatic teal silhouette target extraction) and `MockGeminiLiveSession` (`simulator/mock_gemini_session.py`).
  - Built `mustang-ai doctor --harness {H1,H2,H3,H4,H5,all} [--mode {sim,radxa}]` (`cli/doctor.py`) and `mustang-ai --self-test` (`cli/run_agent.py`) to verify all 5 cable harnesses (`H1`–`H5`) and all 3 Major Functions before connecting physical hardware.
- **Minimal Early-Test 3D Print Manifest (`docs/ai-edition-software-architecture.md` Section 6)**:
  - Documented the 2-Stage Minimal Print Manifest for early functional testing: **Stage 1 Open-Top Rolling Chassis & Avionics Mule** requires only **`16` STLs (`23` pieces)** (`15` STLs / `21` pieces if using a `10 mm` tall motor without Z-shims), and **Stage 2 Full Optical & HUD Geometry** adds **`+5` STLs (`+5` pieces)** (`body`, `waymo_pod`, `glass_windshield`, `glass_rear`, `gc9a01_bezel`) for **`21` STLs (`28` pieces)** total, skipping `34` cosmetic STLs (`47` pieces) out of `55` STLs (`75` pieces).

### Verified
- **26-Test `pytest` Suite, Harness Doctor `H1..H5` & Ruff Lint (`software/tests/`, `tmp/ai_edition_runtime_report.json`)**:
  - Verified `cd software && uv run --with pytest pytest -v` (`26/26` passed across `test_protocol_contracts.py`, `test_watchdog_and_safety.py`, `test_fn1_voice_emoji_hud.py`, `test_fn2_maneuver_obstacle.py`, `test_fn3_person_follower.py`, and `test_virtual_arena_e2e.py`), `mustang-ai doctor --harness all --mode sim` (`PASS` across `H1`–`H5`), `mustang-ai --self-test` (`PASS`), and `uvx ruff check software/ mustang/` (`0` errors).

---

## [v3.1.0] - 2026-11-05 — 3-Tier Autonomous Software Architecture: Voice + 12 Fun Emojis, 7 Action Macros with Auto Reverse/Bypass & Coupled Visual-Laser Person-Following

### Added
- **3-Tier Software Architecture & Sensor-to-Command Specification (`docs/ai-edition-software-architecture.md`, `ai_edition/config.py`)**:
  - Authored [`docs/ai-edition-software-architecture.md`](docs/ai-edition-software-architecture.md) defining how raw signals from the 5-Harness (`H1`–`H5`) topology (`VL53L1X` `50 Hz` I2C3 laser, `OV5647` `15 Hz` MIPI CSI-2 `160°` fisheye camera, and `INMP441` `16 kHz` I2S MEMS mic) compile into real-time actuator commands (`DRV8833` `20 kHz` PWM motor, `1.7g` `50 Hz` steering servo, `MAX98357A` I2S speaker amp, and `1.28"` Round `GC9A01` `240×240` SPI HUD) across 3 hierarchical control tiers (`50 Hz` Reflex Governor, `15 Hz` Local Autonomy Sequencer, `5 Hz / 16 kHz` Cloud `gemini-robotics-er-2-streaming` Live API).
- **Major Function 1 — Option B Hybrid Voice Conversation (`Cloud Audio-In` + Local `Piper ONNX` TTS), Half-Duplex Barge-In Guard & 12 Expressive Fun Emojis (`ai_edition/drivers/gc9a01_display.py`, `ai_edition/drivers/sensors_audio.py`)**:
  - Configured Option B Hybrid Voice Architecture (`GeminiERConfig.voice_architecture = "hybrid_cloud_audio_in_local_piper_tts"`, `input_modalities = ("VIDEO", "AUDIO", "TEXT")`, `output_modalities = ("TEXT",)`): `INMP441` `16 kHz` PCM audio streams directly into `gemini-robotics-er-2-streaming` (requiring **zero local STT model** on the Radxa Zero 3W), while `LocalPiperTTS` (`piper-tts` ONNX, `~25 MB` RAM, `< 45 ms` latency) synthesizes Gemini's `spoken_text` locally on the Radxa into `16 kHz` PCM for the `MAX98357A` I2S speaker.
  - Upgraded `GC9A01Display.render_hud()` and added `render_emoji_contact_sheet()` (`docs/images/ai_gc9a01_emoji_sheet.png`, `960×720` `4×3` grid) supporting all **12 Expressive Fun Emojis** (`CRUISE`, `HAPPY`, `WINK`, `LAUGH`, `COOL_SHADES`, `HEART_EYES`, `SURPRISED`, `THINKING`, `CONFUSED`, `SLEEPY`, `ANGRY_REV`, `ALERT_STOP`) with steering-coupled pupil gaze and a 13-bar live voice waveform equalizer.
  - Added `I2SAudioStream.read_mic_with_echo_guard()` implementing **Half-Duplex Auto-Mute** during `LocalPiperTTS` / `MAX98357A` playback (`muted_by_half_duplex = True`) and **High-Threshold Barge-In** (`barge_in_rms_threshold = 0.55`) so a loud `"Stop!"` immediately cancels speaker playback and triggers `emergency_stop`.
- **Major Function 2 — 7 Predefined Action Macros & Auto Reverse + S-Curve Obstacle Bypass (`ai_edition/gemini_er_agent.py`, `ai_edition/drivers/sensors_audio.py`)**:
  - Implemented `MANEUVER_LIBRARY` and `ManeuverSequencer` supporting all **7 Core Tricks** (`circle_left`, `circle_right`, `figure_eight`, `slalom`, `spin_wiggle`, `u_turn_3pt`, and `patrol`) via the non-blocking `execute_maneuver` Gemini tool.
  - Implemented `OV5647FisheyeCamera.estimate_left_right_clearance()` and the 5-state obstacle recovery state machine (`CLEAR` $\rightarrow$ `CAUTION_SLOW` $\rightarrow$ `REFLEX_BRAKE` at `< 120 mm` $\rightarrow$ `EVASIVE_REVERSE` at `-0.40` throttle until `d >= 240 mm` $\rightarrow$ `EVASIVE_BYPASS_PASS` at `±15°` toward the clearer lane $\rightarrow$ `EVASIVE_BYPASS_REJOIN` counter-steer $\rightarrow$ `CLEAR` maneuver resume).
- **Major Function 3 — Coupled Visual-Laser Person-Following (`ai_edition/gemini_er_agent.py`, `ai_edition/drivers/sensors_audio.py`)**:
  - Implemented `OV5647FisheyeCamera.track_person_target()` (equidistant fisheye horizontal bearing $\theta_x = \operatorname{degrees}((u - c_x)/f_x)$ for `body_legs_torso` primary and `face_hand_fallback` bounding boxes `[ymin, xmin, ymax, xmax]`) and `FollowPersonController` (`set_follow_person_mode`) with PD steering ($K_p = 0.42, K_d = 0.08$) and 4-zone `VL53L1X` longitudinal standoff control (`> 450 mm` proportional approach, `220..450 mm` hold at `350 mm` with `HEART_EYES`, `120..220 mm` `-0.32` personal-space reverse with `WINK`, and `< 120 mm` reflex brake).

### Verified
- **Closed-Loop Self-Test Across All 3 Major Functions & Lint (`tmp/ai_edition_runtime_report.json`)**:
  - Verified `uv run --with pillow python3 -m ai_edition.gemini_er_agent --self-test` (`all_checks_passed == true`, `12/12` emojis rendered, half-duplex mute + shout barge-in verified, `7/7` maneuvers verified, left-obstacle right-bypass state machine transitions verified, and `620 mm / 350 mm / 175 mm` person-following states verified) and `uvx ruff check ai_edition/` (`0` warnings/errors).

---

## [v3.0.0] - 2026-11-04 — Independent AI Edition (`Radxa Zero 3W` + `OV5647` Roof Scoop + Sub-Surface `1.28"` `GC9A01` Rear Window HUD + `gemini-robotics-er-2-streaming` Runtime)

### Added
- **Independent AI Edition CAD & Bambu Lab X2D Pipeline (`mustang/ai_edition.py`, `mustang/make_ai_project.sh`, `mustang/merge_3mf.py`)**:
  - Created `mustang/ai_edition.py` (`build_and_export()`), preserving the baseline `1:20` RC Mustang files (`output/mustang_67_fastback.blend`, `output/stl/`, `output/mustang_67_fastback_1-24.3mf`) untouched while building the **Sleek Sub-Surface Option B** AI Edition (`69` scene parts, `55` STLs, `75` printed pieces) into `output/ai_edition/` (`output/ai_edition/mustang_67_ai_edition.blend`, `output/ai_edition/stl/`, and `output/ai_edition/mustang_67_ai_edition_x2d.3mf`).
  - **`WaymoPod` (`waymo_pod.stl`, Burgundy `#6B0F1A`, `34.25 × 21.80 × 6.45 mm`, `2,144.5 mm³`)**: Engineered a `5.5 mm` low-profile Shelby-style teardrop roof vision scoop with a flat print-bed bottom (`Z = 63.80 mm` seated inside `Cut_WaymoSocket`), a `45°` Gothic-crowned fisheye lens bay (`WaymoPod_LensArch`), and top `INMP441` MEMS microphone vents (`WaymoPod_MicCup`), sinking `80%` of the `OV5647` wide-angle/fisheye camera (`25 × 24 mm` PCB + CSI ribbon) inside `Cut_WaymoChimney` (`floating == []`, `cantilevers == []`).
  - **`GC9A01Bezel` (`gc9a01_bezel.stl`, Silver `#C8C8CC`, `29.60 × 29.60 × 0.85 mm`)**: Engineered a `0.0 mm`-protrusion flush sub-surface chrome bezel ring mounted inside a circular cutout (`Cut_RearGlassHUD`, `Ø 30.40 mm` on `Glass_Rear` + `Cut_RearGlassHUDWell`, `Ø 32.40 mm` on `Body`) along the `+20.5°` fastback rear window slope (`floating == []`, `cantilevers == []`), framing the `1.28"` Round `GC9A01` (`240×240` SPI IPS) display `< 12 mm` above the `Radxa Zero 3W` GPIO header.
  - **Bridged Two-Story Rear Avionics Deck & Lower-Valance ToF Cradle (`Cut_RadxaBulkheadBridge`, `BootTub_RadxaBridge`, `BootTub_RadxaRail_L/R`, `Tub_AIRadxaSled`, `Tub_AISpeakerBay`, `Tub_AIAmpDrvBay`, `BayTub_ToFSlot`)**: Bridged the rear bulkhead (`X = 3390..4010`, `45°` self-supporting gable roof) and `InteriorTub` / `BootTub` to seat the `65.0 × 30.0 × 5.2 mm` `Radxa Zero 3W` on the upper sled (`Z = 36.4..41.4 mm`, dual USB-C facing the `-40°` opening `TrunkLid`) above the `2S 7.4V` LiPo, `5V 3A` BEC, `15×24×4 mm` Speaker, `MAX98357A` I2S amp, and `DRV8833` H-bridge, plus a lower-valance `VL53L1X` ToF laser rangefinder cradle (`BayTub_ToFSlot`), leaving the 1967 Pony Grille and Windshield 100% untouched.
- **Radxa Zero 3W + `gemini-robotics-er-2-streaming` Python Runtime (`ai_edition/`) & 4-Act Cable Assembly / Autonomous Drive Simulation (`mustang/ai_animate.py`, `docs/ai-edition-gemini-robotics-guide.md`)**:
  - Created `ai_edition/config.py`, `ai_edition/drivers/gc9a01_display.py` (`240×240` RGB565 SPI TFT driver + circular HUD compositor with steering-synced eyes, voice waveform equalizer, and ToF alert ring), `ai_edition/drivers/motor_servo.py` (`DRV8833` `20 kHz` PWM H-bridge + `50 Hz` `1.7g` steering servo driver), `ai_edition/drivers/sensors_audio.py` (`OV5647FisheyeCamera`, `VL53L1XRangefinder` `< 20 ms` hardware emergency-stop reflex, and `I2SAudioStream` `16 kHz` PCM audio), and `ai_edition/gemini_er_agent.py` (`MustangGeminiERAgent` bidirectional Live API streaming loop + `--self-test` suite).
  - Created `mustang/ai_animate.py` (`render_ai_simulation()`, `144` frames @ `24 fps`, `1280×720` Cycles Metal GPU) and [`docs/ai-edition-gemini-robotics-guide.md`](docs/ai-edition-gemini-robotics-guide.md), rendering the 4-Act 3D Cable Assembly (`H1`–`H5` animated cable growth onto the 40-pin Radxa Zero 3W header) and Autonomous `gemini-robotics-er-2-streaming` Drive Simulation (`output/ai_edition/mustang_67_ai_simulation.mp4`, `docs/images/ai_simulation.mp4`, `docs/images/ai_simulation.gif`, and `docs/images/ai_simulation_storyboard.jpg`).

### Verified
- **Zero-Overlap CAD, 55-STL / 9-Plate X2D `.3mf` & Closed-Loop Runtime Verification (`tmp/ai_edition_build_report.json`, `tmp/ai_edition_runtime_report.json`)**:
  - Verified `printcheck.run()` across all `69` scene parts (`problems == {}`, `overlaps_with_body == {}`, `mirror_mismatches == {}`, `part_overlaps == {}`, `body.shells == 1`), `verify_virtual_ai_hardware() == {}` (`0.0 mm³` overlap across all 8 virtual AI hardware envelopes), and `export.run()` across all `55` STLs (`75` pieces, `0` non-manifold edges, `floating == []` and `cantilevers == []` on all `50` support-free STLs).
  - Verified `ai_edition.gemini_er_agent --self-test` (`all_checks_passed == true`, `< 20 ms` ToF reflex brake latency, `240×240` `GC9A01` HUD frames exported to `tmp/`).

---

## [v2.9.1] - 2026-11-03 — Open-Bottom Driveshaft U-Channels, Straight-Vertical V8 Drop, Tie-Rod Assembly Notch & `1:20` Door Hinge Bores

### Fixed
- **Open-Bottom `45°` Gable Driveshaft U-Channels & Tie-Rod Straight-Lift Notch (`mustang/interior.py`, `mustang/details.py`, `mustang/engine_bay.py`)**:
  - Opened the bottom floors of `Tub_ShaftTunnel` (`interior.py`, `FLOOR_Z0 - 15.0 = 275.0`), `Cut_DiffShaftWeb` (`details.py`, `body_z_bottom() - 20.0 = 270.0`), and `BayTub_ShaftTunnel` (`engine_bay.py`, `FLOOR_Z0 - 15.0 = 275.0`) into continuous `45°` self-supporting gable-roofed open-bottom U-channels while keeping the adjacent driver-side 5-wire conduit (`4.00 × 5.05 mm`) fully enclosed behind the `1.05 mm` partition wall. `Driveshaft + PinionGear` now lifts straight up from underneath into `MotorCoupler` without closed-tunnel threading, while `Body` (`209,970.67 mm³`), `InteriorTub` (`65,591.22 mm³`), and `BayTub` (`25,622.40 mm³`) each retain `shells == 1`, `non_manifold_edges == 0`, `floating == []`, and `cantilevers == []`.
  - Added `BayTub_TieRodClear` (`X = 666..682, Y = -58..+58`, vertical through-notch at the rear lip of `BayTub_FloorFront`) so the complete rolling `Chassis` (`Chassis + Axle_R + AxleGear + Knuckle_L/R + SteeringLink + Rim_* + Tire_*`) pushes straight `+Z` from underneath into `Body + InteriorTub + BayTub + MotorCoupler + Driveshaft + PinionGear` with **`0.40 mm` front clearance** on `SteeringLink` (`X >= 674.0`) and **`0` BVH collisions** across all `35` vertical steps.
- **Straight-Vertical (`0°` Pitch) `EngineBlock` Drop Past `BayTub_Booster` & Clean `TrunkLid` Swing (`mustang/engine_bay.py`)**:
  - Trimmed `Engine_BellhousingMount` outer `|Y|` from `282.0` real mm (`14.10 mm` print) inward to `266.0` real mm (`13.30 mm` print, with a `45°` bevel to `(212.0, 436.0)`), eliminating the `0.35 mm` vertical-path overlap against `BayTub_Booster` (`Y = -275.0` real mm = `-13.75 mm` print). `EngineBlock + ValveCover_L/R + AirCleaner` now drops straight down (`-Z`, `dx = 0, dy = 0, pitch = 0°`) with **`0.45 mm` radial booster clearance**, **`0` BVH collisions**, `CoM = [52.17, 0.26, 29.14] mm` centered inside `[43.30, 79.00] mm`, and **`324.45 mm²` (`12.4×`)** flat floor contact.
  - Widened `TRUNK_FRONT_GAP` from `11.0` to `15.0` real mm (`0.75 mm` print, safely behind `DECKLID_X0 = 3865.0`), bringing `TrunkLid`'s `0°..-40°` kinematic sweep overlap down from `0.014 mm³` to **`0.000 mm³`**.
- **Calibrated `1:20` Door `1.75 mm` Filament Hinge Bores (`mustang/doors.py`)**:
  - Tightened `PIN_HOLE_R, DOOR_HOLE_R` from `22.0, 24.0` real mm (`Ø 2.20 / Ø 2.40 mm` carried over from `1:24`) to **`18.4, 20.0` real mm**, producing **`Ø 1.84 mm` blind sill bores (`+0.045 mm`/side press/glue fit)** in `body.stl` and **`Ø 2.00 mm` blind door bores (`+0.125 mm`/side rattle-free running fit)** in `door_l.stl` and `door_r.stl` around standard `1.75 mm` PLA filament.

### Verified
- **Full `53`-STL, `9`-Plate Bambu `.3mf`, `67`-Solid STEP & `3D` Trajectory Regeneration**:
  - Rebuilt `output/mustang_67_fastback.blend` (`4` studio cameras preserved), `output/stl/*.stl` (`53` STLs, `0` non-manifold edges, `floating == []` and `cantilevers == []` on all `48` support-free STLs), `output/stl_assembled/*.stl` (`67` parts), `output/mustang_67_fastback_1-24.3mf` (**`0` warnings across all `9` plates** in Bambu Studio `02.08.02.61` `--slice 0`, `tmp/bambu_slice_report.json`), and `output/step/*.step` + `output/mustang_67_fastback.step` (**`67` valid closed OpenCascade STEP solids**, `exit_code == 0`), with **`0` collisions across all 6 straight-line `3D` physical insertion trajectories** and **`0.000 mm³` across all kinematic sweeps** (`tmp/v291_assembly_trajectory_report.json`).

---

## [v2.9.0] - 2026-11-03 — Multi-Fit Motor Coupler & Z-Shim Kit, Flat-Printed `7T:9T` Bevel Gears & `21 × 11 mm` Motor Cradle

### Fixed
- **Multi-Fit Upright `MotorCoupler` Kit & Side `M2` / Glue Lock Port (`mustang/engine_bay.py`, `mustang/build.py`, `mustang/export.py`, `mustang/materials.py`, `mustang/animate.py`)**:
  - Replaced the loose `Ø 3.20 mm` horizontal teardrop D-bore on `Driveshaft` (which slipped freely around bare `Ø 1.0–1.5 mm` smooth steel motor pins) with a dedicated upright-printed (`RY_UP_FROM_POS_X`) `10.0 mm` × `Ø 5.50 mm` modular coupler (`MotorCoupler` $\rightarrow$ `motor_coupler_1p0.stl` on the car, plus 3 spare variants `motor_coupler_1p5.stl`, `motor_coupler_tube.stl`, and `motor_coupler_n25.stl` in `Accessories` exported onto Plate 6 `3_silver_small`).
  - Engineered 4 `XY`-traced 48-vertex precision motor bores distinguishable off the bed by external V-flutes (`1` flute = `Ø 0.92 mm` inscribed 3-lobe crush bore for `Ø 1.0 mm` smooth pin, **`0.108–0.136 mm³` positive crush grip**; `2` flutes = `Ø 1.42 mm` 3-lobe crush bore for `Ø 1.5 mm` pin; `3` flutes = `Ø 2.28 mm` 6-spline collet bore for a silicone-tube friction sleeve; `0` flutes = `Ø 3.08 mm` / `2.58 mm`-flat D-bore for geared `N20/N25` `Ø 3.0 mm` D-shafts), each incorporating a `45°` self-supporting transverse diamond `M2` set-screw / CA-glue lock port and flaring upward (`0` internal ceiling overhang) into a `3.32 mm`-flats octagonal rear spline socket (**`0.650 mm³` rotational lock** at `22.5°`).
- **Flat-Printed Coarse `7T:9T` Bevel Gear Pair & Toothless Horizontal `Driveshaft` (`mustang/engine_bay.py`, `mustang/details.py`, `mustang/export.py`)**:
  - Split the bevel pinion off the horizontal `Driveshaft` (`driveshaft.stl`: `97.15 × 3.80 × 3.62 mm`, symmetric `3.24 mm`-flats front/rear octagonal spline tenons, continuous bed-flat `+Z_car` top face) into a standalone `7`-tooth bevel pinion (`PinionGear` $\rightarrow$ `pinion_gear.stl`, `5.39 × 5.38 × 3.80 mm`, `38.80 mm³`) printed flat in the `XY` plane (`RY_UP_FROM_POS_X`, **`0.54 mm` heel crest / `0.43 mm` toe crest**) with a `3.32 mm`-flats octagonal spline socket (**`0.372 mm³` spline lock** at `22.5°`).
  - Upgraded `AxleGear` (`axle_gear.stl`, `6.95 × 6.94 × 1.75 mm`, `33.00 mm³`) from `12T` to a coarser flat-printed `9`-tooth crown bevel gear (`RX_UP_FROM_NEG_Y`, **`0.60 mm` heel crest**, `40%` tooth / `60%` valley profile) meshing at `90°` (`1.29 : 1` reduction) inside `Cut_ChassisAxlePinion` + `Cut_ChassisAxleGear`, increasing locked-crown half-pitch tooth interlock by **`+50.0%` (`0.099 mm³` vs `0.066 mm³`)** with `0.047 mm³` static clearance and **`0.000 mm³` housing interference** across a `36`-step `360°` `7:9` coupled rotation sweep.
- **Exact `21.25 × 11.25 mm` `BayTub` Motor Cradle, `0.48 mm` Z-Shims & Zero-Overhang Wire Partition (`mustang/engine_bay.py`)**:
  - Resized `BayTub_N25Bed` (`X = 951..1376`, `Y = -112.5..+112.5`, `Z = 295`, shaft centerline `Z = 395 = 19.75 mm`) to an internal **`21.25 × 11.25 × 10.00 mm`** slip-fit cradle (`0.125 mm` per-side clearance around the measured `21.0 × 11.0 mm` flat-can DC motor) and added `2 × 0.48 mm` bed-flat Z-shims (`MotorShim_0p5` $\rightarrow$ `motor_shim_x2.stl` on Plate 4 `2_black`), aligning `10.0 mm` (`0` shims $\rightarrow$ `Z = 19.75 mm`), `9.0 mm` (`1` shim $\rightarrow$ `Z = 19.73 mm`), and `8.0 mm` (`2` shims $\rightarrow$ `Z = 19.71 mm`) motor heights within `≤ 0.04 mm` of the `Driveshaft` axis (`0.000 mm³` motor/tab/shim overlap).
  - Added symmetric front solder-tab relief (`BayTub_N25WireFront`, `Y = -92..+92`), driver-side upper wire return (`BayTub_N25WireSideL`), open-top rear wire exit (`BayTub_N25WireRear`), reinforced `BayTub_RadOverflow` (`r = 9.0`) and `BayTub_MCBail` (`0.55 mm` solid strap), and capped `BayTub_N25Front/Rear/WallL/R`, `BayTub_WirePartition` (`Y = -80..-58`), and `BayTub_WireOuterWall` (`Y = -167.5..-152.0`) at `Z = 422.0` below `BayTub_WireTunnel`'s `45°` gable shoulder (`0.000 mm³` `BayTub|EngineBlock` overlap, `floating == []`, `cantilevers == []`).

### Changed
- **53-STL / 73-Piece 9-Plate Bambu Project & 67-Solid STEP Assembly (`mustang/make_project.sh`, `mustang/merge_3mf.py`, `.claude/skills/print-pipeline/SKILL.md`)**:
  - Expanded the print manifest to **`53` STLs (`73` pieces across `9` plates: `5` Burgundy, `26` Black, `35` Silver, `6` Red, `1` Blue)** with `SMALL_PART_BRIM` (`4 mm` `outer_only` brim, `20–25 mm/s` wall speeds) on `pinion_gear.stl` and all 4 `motor_coupler_*.stl` variants (`28` brimmed STLs total).
  - Regenerated `output/stl/` (`53` STLs, `0` non-manifold edges, `48` support-free with `floating == []` and `cantilevers == []`), `output/stl_assembled/` (`67` parts), `output/mustang_67_fastback.blend` (`4` studio cameras preserved), `output/mustang_67_fastback_1-24.3mf` (**`0` warnings across all `9` plates** in Bambu Studio `02.08.02.61` `--slice 0`), and `output/step/*.step` + `output/mustang_67_fastback.step` (**`67` valid closed OpenCascade STEP solids**, `exit_code == 0`).

---

## [v2.8.0] - 2026-11-02 — Plate 5 Small-Part Reliability Overhaul, Horizontal Driveshaft, 9-Plate Split & Outer-Only Brims

### Fixed
- **Horizontal Bed-Flat Octagonal `Driveshaft` (`mustang/engine_bay.py`, `mustang/export.py`, `mustang/interior.py`, `mustang/details.py`)**:
  - Re-engineered `Driveshaft` (`driveshaft.stl`) from a `105.50 mm` vertical needle (`RY_UP_FROM_POS_X`, `13.95 mm²` ring bed contact) to print horizontally flat (`UPSIDE_DOWN`, `+Z_car` flat on `Z = 0`) using a 40-vertex bed-flat octagonal shaft (`h_shaft = 44.0` real mm = `4.40 mm` across flats), coupler (`hy = 52.0`, `hz_top = 44.0`, `hz_bot = 53.0`), and `45°` teardrop-crowned `Driveshaft_DBore` (`3.20 mm` D-bore), lofting into the `10`-tooth conical bevel pinion (`X = 3470..3514`).
  - Reduced `driveshaft.stl` print height by **`95.4%`** (`105.50 × 5.20 × 4.85 mm` vs `5.20 × 5.20 × 105.50 mm`) and expanded `Z = 0` flat bed contact area by **`13.9×`** (`193.65 mm²` vs `13.95 mm²`, `floating == []`, `cantilevers == []`, `non_manifold == 0`).
  - Widened `Tub_ShaftTunnel` in `interior.py` and `Cut_DiffShaftWeb` in `details.py` from `Y = ±50.0` to `Y = ±53.0` real mm (`Y = -2.65..+2.65 mm` print, preserving a solid **`1.05 mm` partition wall** against the driver-side wire conduit) and verified **`0.000 mm³`** overlap across a full `360°` shaft spin (`0°..345°` step `15°`).
- **7-Layer Stepped `GrilleSurround` Bottom Horizontal Bar (`mustang/details.py`)**:
  - Eliminated the vanishing `0.045 mm` (`0` sliced layers) bottom chrome bar on `grille_surround.stl` by stepping `Grille` (`floor .. floor + 0.45` outer flange + `Grille_Step` `floor + 0.40 .. floor + 0.90` inside `grille_poly(FIT + SURROUND_W + 0.08)`), starting `GrilleSurround` deeper at `floor + 0.48`, and shifting `GrilleSurround_Skin` forward (`-8.0` real mm = `0.40 mm` proud shark-nose lip).
  - `grille_surround.stl` (`11.06 × 57.65 × 3.92 mm`, `129.46 mm²` bed contact) now slices a continuous **`0.941 mm` (`7` layers at `0.12 mm`)** bottom horizontal bar with **`0.000 mm³`** static and `0°..42°` `Hood` sweep overlap.
- **Stabilized `Exhaust_L/R` Oval Base Foot & `45°` Tapered Tip Sleeve (`mustang/details.py`)**:
  - Added a concealed oval muffler-outlet base (`Exhaust_L/R_Base`, `X = 3880..3922` tucked below `REAR_FLOOR_Z - 8.0`) and `45°` self-supporting tapered tip sleeve (`Exhaust_L/R_Tip`) on `exhaust_x2.stl` (`7.57 × 6.20 × 28.27 mm`), expanding `Z = 0` bed contact area by **`3.33×`** (`20.29 mm²` vs `6.09 mm²`, `floating == []`, `cantilevers == []`).

### Changed
- **9-Plate Split (`3_silver` + `3_silver_small`) & Per-Object Outer-Only Brims (`mustang/make_project.sh`, `mustang/merge_3mf.py`, `.claude/skills/print-pipeline/SKILL.md`)**:
  - Split `3_silver` (`29` pieces) into **Plate 5 (`3_silver`, `9` larger chrome pieces: `rim_x4`, `bumper_front`, `grille_surround`, `exhaust_x2`, `driveshaft`, `max_z = 28.16 mm` vs `105.44 mm`)** and **Plate 6 (`3_silver_small`, `20` miniature chrome pieces: `corral_emblem`, `fog_lamp_x2`, `headlight_x2`, `park_light_x2`, `taillight_bezel_r_x3`, `taillight_bezel_l_x3`, `gas_cap`, `backup_light_x2`, `mirror`, `vent_window_r`, `vent_window_l`, `axle_gear`, `max_z = 4.40 mm` / `36` layers)**, expanding the Bambu `.3mf` project to **`9` plates** (`64` Bambu objects / `66` pieces).
  - Added per-object `SMALL_PART_BRIM` (`4 mm` `outer_only` brim, `0.08 mm` gap, `25/40 mm/s` outer/inner walls, `20 mm/s` small perimeters), `SLENDER_BAR_BRIM` (`3 mm` brim, `0.1 mm` gap, `30/45 mm/s` walls), and `TALL_PIPE_BRIM` (`5 mm` brim, `0.08 mm` gap, `25/40 mm/s` walls) across `23` small/slender STLs on `2_black`, `3_silver`, `3_silver_small`, and `4_red`, alongside global `reduce_crossing_wall = "1"` and `initial_layer_speed = "25"` in `complete_settings`.
  - Regenerated all `47` print STLs, `65` assembled STLs, `65` STEP solids + `output/mustang_67_fastback.step` (with exact faceted `raw_solid` fallback in `mustang/make_step.py` whenever OpenCascade `UnifySameDomain` leaves a non-valid wire, ensuring all `65` STEP solids pass `BRepCheck_Analyzer` with `exit_code == 0`), `output/mustang_67_fastback.blend`, and `output/mustang_67_fastback_1-24.3mf`, verified with **`0` warnings across all `9` plates** in Bambu Studio `02.08.02.61` CLI (`--slice 0`, `6,197` brim extrusion moves on Plate 6 and `1,410` on Plate 5).

---

## [v2.7.1] - 2026-11-02 — Zero-Cantilever Door Cards, Unsevered Console Shifter & Slicer Overhang Verification

### Fixed
- **Zero-Cantilever Support-Free Door Cards & Contoured `45°` Mortise-and-Tenon Interlock (`mustang/doors.py`)**:
  - Resolved Bambu Studio's `floating cantilever` warnings on `door_card_r.stl` and `door_card_l.stl` on Plate 4 (`2_black`, `enable_support = 0`), caused by the 6 central protruding pads (`PAD_Y_CARD = 710.5`) holding the surrounding `560.63 mm²` horizontal door-card perimeter (`y_out = 694.5`) `0.80 mm` (`6–7` layers) in mid-air above the build plate, alongside a `0.85 mm` horizontal `DoorCardTrim` step and a horizontal `DoorCard_VentSlot` ceiling.
  - Replaced the 6 discrete pads with a continuous bed-flat contoured rear boss (`PAD_Y_CARD = 704.5`, **`990.80 mm²` flat `Z = 0` bed contact area** — **`4.06×` larger** than the `244.1 mm²` 6-pad footprint) that expands outward at a `45°` self-supporting bevel (`bevel_card = 34.0` to `CARD_EDGE_Y = 670.5`) and mates into a contoured `45°` mortise bay (`Door_L/R_CardBay`, `BAY_Y_DOOR = 706.5`) inside `Door_L/R` (`door_card_r.stl` / `door_card_l.stl`: `50.55 × 26.56 × 5.43 mm`, `2,483.7 mm³`, `floating == []`, `cantilevers == []`).
  - Added a symmetric upper central tongue (`MIRROR_BOSS_X = (1975.0, 2025.0)`, `MIRROR_BOSS_Z = 852.0`) inside `Door_L/R_CardBay` — preserving full solid wall thickness behind `DoorMirrorSlot_L` and exact `L/R` mirror symmetry — paired with a self-supporting `32.3°` gable keyway (`_card_mirror_key` $\rightarrow$ `DoorCard_L/R_MirrorKey`) with a `+45°` upward-facing lower ramp on `DoorCard_L/R`.
  - Tapered the back of `DoorCardTrim_L/R` at `45°` flush with `DoorCard`'s rear bevel (`0.000 mm` overhanging step) and sloped `DoorCard_L/R_VentSlot` continuously along `DoorVent`'s tumblehome angle, preserving full 5-direction positive mechanical lock (`149.712 mm³` outboard `-Y`, `2.075 / 2.048 mm³` fore/aft `±X`, `3.052 / 3.777 mm³` vertical `±Z`, `0.866 mm³` vent inboard `+Y`, and `0.000 mm³` static/swing overlap across `0°..65°`).
- **Unsevered Automatic Console T-Shifter Collar & Stalk (`mustang/interior.py`, `mustang/build.py`)**:
  - Resolved Bambu Studio's `floating regions` warning on `interior_tub.stl` (`z_stl = 12.40 mm`), where applying `Tub_ShiftSlot` (`DIFFERENCE` at `z = 514..538`) after `Tub_ShifterCollar` and `Tub_Shifter` severed the shifter base down to a `0.041 mm` sub-nozzle sliver dropped by Arachne.
  - Moved `Tub_ShifterCollar` (`z0 = 510.0`), `Tub_Shifter` (`z0 = 510.0`), and `Tub_ShifterKnob` into `late_pieces` in `interior.tub_parts()` and unioned them after `cuts` in `build.py` so the shifter rises uncut (`Ø 1.40–2.40 mm` solid neck) out of the recessed selector gate floor above `Tub_ShaftTunnel` (`z <= 495.0`) (`interior_tub.stl`: `66,849.2 mm³`, `floating == []`, `cantilevers == []`).
- **Slicer-Grade Sub-Nozzle Neck & Perimeter Cantilever Detection (`mustang/printcheck.py`, `mustang/export.py`)**:
  - Added `_overhang_hazards(bm)` and `floating_cantilevers(bm)` to `printcheck.py` and `cantilevers` reporting to `export.run()`, catching both horizontal cantilevers projecting `>= 0.80 mm` past lower-layer support and sub-nozzle (`< 0.20 mm` minor-axis width) boolean necks inside `floating_starts(bm)`.
  - Regenerated all `47` print STLs, `65` assembled STLs, `65` STEP solids + `output/mustang_67_fastback.step`, `output/mustang_67_fastback.blend`, and `output/mustang_67_fastback_1-24.3mf`, verified with **`0` warnings across all `8` plates** in Bambu Studio `02.08.02.61` CLI (`--slice 0`).

---

## [v2.7.0] - 2026-10-17 — Heavy-Duty `3.24 mm` Live Axle, Reinforced Kingpin Knuckles, Counterbore Rim Hubs & `12`-Spline Bead-Lock Tires

### Changed
- **Heavy-Duty Rear Live Axle & Close-Running Chassis Bearings (`mustang/wheels.py`, `mustang/details.py`, `mustang/engine_bay.py`)**:
  - Upgraded `AXLE_FLATS` from `2.30 * K` (`2.76 mm`) to **`2.70 * K` (`3.24 mm` across flats / `Ø 3.507 mm` across corners)**, increasing `Axle_R` cross-sectional area from `6.31 mm²` to **`8.70 mm²` (`+37.8%` volume: `510.71 mm³`)** and torsional/bending stiffness ($I \propto d^4$) by **`+90.1%`** to eliminate rear axle twist or deflection under `N25` gearmotor torque.
  - Tightened `AXLE_HOLE_R` in `details.py` to `1.535 * K` (`Ø 3.684 mm` close-running bearing bore around `Ø 3.507 mm` axle corners = **`0.088 mm` radial bearing clearance**, reducing radial play by **`52.6%`** vs the `0.187 mm` baseline) and widened `Chassis_BossR` to `|Y| = 612.0` real mm (`61.20 mm` bearing span) so the rear axle bosses sit `0.90 mm` from the inner rim hub faces.
  - Updated `AxleGear_Bore` (`r_oct = 33.20 / cos(pi/8)`, `3.32 mm` across flats) and extended the `AxleGear` hub collar (`y = 21.5..54.5` real mm, `r = 70.0` real mm; `axle_gear.stl`: `32.16 mm³`), increasing rotational spline lock on `Axle_R` by **`+73.8%` (`0.278 mm³` vs `0.160 mm³` at `22.5°`)** with `0.000 mm³` static overlap.
- **Reinforced Front Steering Knuckles & Kingpin Posts (`mustang/wheels.py`, `mustang/details.py`)**:
  - Upgraded front `Chassis_Kingpin_L/R` posts to `r = 19.0` real mm (`Ø 1.90 mm`), `Chassis_KingpinBase_L/R` (`r = 28.0` real mm), and `Chassis_KingpinArm_L/R` (`Y = ±614.0` real mm).
  - Reinforced `Knuckle_L/R` (`knuckle_l.stl`, `knuckle_r.stl`: **`163.70 mm³`**, **`+44.1%` volume** vs `113.64 mm³` baseline): thickened kingpin barrel (`Ø 3.60 mm` OD) with a close-running `Ø 2.05 mm` bore (`0.075 mm` radial clearance, `0.775 mm` barrel wall, **`1.069 mm³`** radial retention lock), widened steering arm (`3.20 mm × 2.16 mm`), bed-coplanar underside (`z_bot = 14.88 mm` = `297.6` real mm so the entire knuckle prints flat on `Z = 0` with `floating == []`), and added an integral root boss (`r = 2.08 mm`) plus inboard wheel stop collar (`Knuckle_L/R_HubCollar`, `r = 2.40 mm` at `|Y| = 31.30..33.80 mm`) that absorbs lateral cornering thrust directly against the inner rim hub face.
- **High-Torque `29.1×` Octagonal Rim Hub Lock & Internal `45°` Counterbore Axial Stop (`mustang/wheels.py`)**:
  - Thickened the rear hub boss of `Rim_*` (`rim_x4.stl`: **`1,942.78 mm³`**, up from `1,850.25 mm³`) to `r = 3.15 * K` (`Ø 7.56 mm` OD at the back face, `>2.14 mm` solid hub wall) and calibrated `HUB_HOLE_R = 1.365 * K` (`Ø 3.276 mm` cylindrical bore across the `3.24 mm` flats / `3.507 mm` corners of `Axle_R` and `Knuckle_L/R`), increasing the 8-corner press-fit lock from `0.090 mm³` to **`2.621 mm³` per wheel (`29.1×` stronger)**.
  - Added an internal `45°` conical counterbore axial stop shoulder (`HUB_CAP_BORE_R = 1.05 * K = 1.26 mm` from `y = w - 0.42 * K` to `w - 0.08 * K`) inside the closed outer end of the rim hub bore, stopping the axle tip at exact track width (`3.343 mm³` inboard push resistance at `0.40 mm` shift) while keeping the outer Torq-Thrust center cap solid.
- **Dual-Flange Bead-Lock & `12`-Spline Anti-Slip Tire-to-Rim Interface (`mustang/wheels.py`)**:
  - Upgraded the `Rim_*` barrel and `Tire_*` inner bore (`tire_x4.stl`: `5,660.17 mm³`, `FIT_GAP = 0.08 mm`) with a mid-barrel circumferential bead-lock crown (`RIM_BEAD_R = 8.38 * K = 10.056 mm`) and **12 longitudinal anti-slip drive splines (`TIRE_SPLINES = 12`, `TIRE_SPLINE_AMP = ±0.288 mm` radial amplitude)** with `45°` self-supporting lead-in ramps (`floating == []` on both `rim_x4.stl` and `tire_x4.stl`).
  - Eliminates tire rotational slip on the rim under `N25` acceleration/braking (**`17.505 mm³` tooth interference at `15°` relative twist** vs `0.000 mm³` on the smooth cylindrical baseline) and locks the tire axially in both directions (**`11.347 mm³` outboard** and **`1.950 mm³` inboard** retention at `0.40 mm` axial shift vs `0.000 mm³` inboard previously), while maintaining **`0.000 mm³` static overlap**.

---

## [v2.6.0] - 2026-10-17 — Authentic 1967 Twin-Cowl Dashboard, Waterfall Console, T-Handle Shifter & 3-Spoke Steering Wheel

### Changed
- **Smooth Dashboard & Continuous Lofted Twin-Cowl Upper Brow (`mustang/interior.py`, `mustang/materials.py`)**:
  - Replaced the 7 separate boxy dash cowl/cheek/pipe solids (`Tub_DashPad`, `Tub_DashHood`, `Tub_DashCheek`) with a single continuous 33-station lofted twin-cowl visor pad (`_dash_brow_loft` $\rightarrow$ `Tub_DashBrow`) that arches over the driver instrument cluster (`Y = -558..-92, Z_peak = 884`) and passenger cowl (`Y = +96..+558, Z_peak = 876`) while dipping smoothly over the center radio stack (`Z = 834`).
  - Filleted the lower dashboard knee roll (`F.rounded_poly`) and split the horizontal chrome fascia trim around the center console (`Tub_DashTrimL`, `Tub_DashTrimR`), adding the sloped brushed-aluminum passenger glovebox door (`Tub_ConsoleDeckGlove`) and Mustang emblem plaque (`Tub_DashTrimEmblem`).
- **Authentic 1967 5-Pod Deep-Set Instrument Cluster (`mustang/interior.py`)**:
  - Replaced the 3 equal-sized flat gauge holes with the authentic 1967 5-pod deep-set instrument layout (`Tub_GaugeBezel0..4`, `Tub_Gauge0..4`): two large outer speedometer and tachometer pods (`dy = ±130, z = 794, r = 44`) flanking three smaller upper auxiliary gauges (`dy = -56, 0, +56, z = 828..832, r = 21.5`) framed through the top opening of the steering wheel.
- **Full-Length Swept Waterfall Center Console, Radio/Tambour Fascia & Selector Gate (`mustang/interior.py`, `mustang/materials.py`)**:
  - Replaced the flat floor brick (`X = 2070..2680`) with a continuous waterfall center console (`_waterfall_console_parts` $\rightarrow$ `Tub_Console`) sweeping from beneath the center dash (`X = 1996, Z = 758`) down the sloped radio/tambour fascia (`X = 2004..2145`) and along the floor tunnel (`X = 2145..2770, Z = 522..538`).
  - Added twin chrome perimeter rails (`Tub_ConsoleTrimRailL/R`), a brushed-aluminum waterfall/shifter deck (`Tub_ConsoleDeckMain`), flush-contoured chrome cross-bars (`Tub_ConsoleTrimRadioTop/Bot/TambourBot/ShiftRear`), two tapered round chrome radio knobs (`Tub_ConsoleTrimKnobL/R`) and dial window (`Tub_ConsoleTrimDial`), 7 flush-contoured tambour door ribs (`Tub_ConsoleTrimRib0..6`), a raised chrome selector bezel (`Tub_ConsoleTrimGate`) with `PRND21` indicator strip (`Tub_ConsoleDeckPRND`) and recessed gate slot (`Tub_ShiftSlot` at `Z >= 514`, clearing `Tub_ShaftTunnel` at `Z <= 495`), twin seatbelt buckle pockets (`Tub_ConsoleTrimBuckle0..1`, `Tub_BucklePocket0..1`), and rear compartment latch (`Tub_ConsoleTrimLatch`).
- **Forward-Swept Automatic T-Handle Shifter (`mustang/interior.py`)**:
  - Replaced the vertical stick-and-ball shifter with a tapered chrome base collar (`Tub_ShifterCollar`), a forward-swept curved chrome stalk (`Tub_Shifter`, `(2238, 0, 508)` $\rightarrow$ `(2186, 0, 624)`), and a horizontal chrome T-bar handle (`Tub_ShifterKnob`, `Y = -46..+46`) with a monotonically draining underside (`floating == []` in `interior_tub.stl`, `66,848.1 mm³`, `0` non-manifold edges).
- **Authentic 1967 3-Spoke Perforated Brushed-Chrome Steering Wheel (`mustang/interior.py`, `mustang/materials.py`)**:
  - Replaced the 3 solid black box spokes (`0°, 120°, 240°`) with an all-quad manifold mesh generator (`_perforated_spoke`) producing 3 tapered brushed-aluminum spokes (`SteeringWheel_Spoke0..2`) in the authentic 1967 Y-layout (`6 o'clock` vertical bottom spoke at `90°` + `2:20` and `9:40` upper-side spokes at `-16°` and `196°`), each perforated with 3 circular lightening holes (`r = 0.42, 0.35, 0.28 mm` print) with outer tips tucked cleanly inside the rim cross-section, plus a chrome horn button/ring (`SteeringWheel_HornRing`), vinyl hub (`SteeringWheel_Hub`), and tapered column collar (`SteeringWheel_Collar`) (`steering_wheel.stl`: `198.4 mm³`, `0` non-manifold edges, `floating == []`).
- **Sculpted Bucket Seats & Comfort-Weave Cushion Contours (`mustang/interior.py`)**:
  - Added rounded front cushion noses (`Tub_SeatInsert*`), 7-station lofted wrap-around thigh bolsters (`Tub_SeatBolster*`) and backrest bolsters (`Tub_BackBolster*`), subtle comfort-weave pleats (`Tub_Pleat*`, `Tub_BackPleat*`), and rounded fastback rear seat cushions (`0.0 mm³` door-swing overlap across `0°..55°`).

---

## [v2.5.0] - 2026-10-17 — Architecture #1 Full 1:20 RC Dynamic Control System & 4-Act 3D Simulation

### Added
- **Front Ackermann-Style Kingpin Steering (`mustang/wheels.py`, `mustang/details.py`, `mustang/build.py`)**:
  - Replaced the static front axle with independent left and right steering knuckles (`Knuckle_L`, `Knuckle_R` $\rightarrow$ `knuckle_l.stl`, `knuckle_r.stl`, `113.6 mm³` each) that pivot `±15°` around integral vertical kingpin posts (`Chassis_Kingpin_L/R`, `X = 792.0, |Y| = 596.0`) supported by `Chassis_KingpinArm_L/R`.
  - Added `SteeringLink` (`steering_link.stl`, `290.5 mm³`) spanning `Y = -596.0..+596.0` at `X = 728.0` across `Chassis_SteeringShelf`, engaging both knuckle steering arms and carrying a top center slot (`SteeringLink_ServoSlot`) driven directly by the `1.7g` micro servo horn (`±0.83 mm` lateral translation $\rightarrow$ `±15°` wheel steer).
  - Widened front wheel track to `FRONT_WHEEL_Y = 32.2 * K` (`38.64 mm`) and deepened front wheel wells to `FRONT_WELL_INNER_Y = 23.4 * K` (`28.08 mm`) with scalloped chassis clearance cuts (`Cut_ChassisSteerF_L/R`, `Cut_ChassisSteerR_L/R`) for `0.0 mm³` tire-to-fender/chassis interference across `-15°..+15°`.
- **Front `1.7g` Micro Servo Cradle (`mustang/engine_bay.py`, `mustang/details.py`)**:
  - Narrowed front radiator/battery bay floor (`BAY_HALF = 544.0`, `BOSS_X0 = 682.0`) and added `BayTub_ServoBed`, `BayTub_ServoFront`, `BayTub_ServoRear`, `BayTub_ServoWallL`, `BayTub_ServoWallR`, and bottom slot `BayTub_ServoHornSlot` (`X = 520..680, Y = -140..+140`) to house a standard `1.7g` micro digital servo (`13.5 × 6.2 × 16.0 mm`) behind the radiator.
  - Extended `Cut_BossSlotF` (`X = 676.0 - c .. 858.0 + c`) for vertical drop-in assembly of the chassis steering shelf and servo horn linkage.
- **Divided Rear `BootTub` Electronics & Battery Compartments (`mustang/engine_bay.py`)**:
  - Added longitudinal bulkhead `BootTub_Divider` (`Y = -40..+10`) and battery retention rails `BootTub_BatRail0/1`, partitioning `BootTub` (`boot_tub.stl`, `3,050.7 mm³`) into a **Left Receiver + 5A Brushed ESC Bay (`Y = -430..-40`, `19.5 × 26.5 mm`)** and a **Right 1S/2S LiPo Battery Tray (`Y = +10..+430`, `21.0 × 26.5 mm`)**.
- **4-Act 3D Assembly, 360° Orbit & Dynamic Drive Simulation (`192 Frames @ 24 fps`, `1280×720`)**:
  - Built and rendered a 4-Act procedural animation (`Act 1`: 6-wave piece-by-piece assembly of all 65 printed parts + 6 color-coded 3D RC electronics modules; `Act 2`: `360°` turntable orbit with `Hood`, `Doors`, and `TrunkLid` opening/closing; `Act 3`: `+15°` Left / `-15°` Right front steering sweep; `Act 4`: `156.72 mm` forward S-turn acceleration with synchronized wheel/driveshaft rotation followed by `89.08 mm` reverse backing up).
- **Modular Documentation Suite & Visual Showcase (`README.md`, `docs/*.md`, `docs/images/*`)**:
  - Streamlined `README.md` into a visual-first project showcase featuring `docs/images/rc_simulation.gif`, `docs/images/rc_simulation.mp4`, `docs/images/showcase_360.mp4`, `docs/images/rc_simulation_storyboard.jpg`, and a 4-step Print & Operate quickstart.
  - Added [`docs/design-thinking-and-verification.md`](docs/design-thinking-and-verification.md) (complete design thinking trade-offs, 4-stage bevel gear analysis, partitioned wire conduit architecture, and zero-overlap verification metrics), [`docs/printing-and-rc-guide.md`](docs/printing-and-rc-guide.md) (47-STL manifest, Option A 2.4GHz Hobby RC & Option B 433MHz RF Keyfob wiring diagrams, and Shapr3D STEP CAD workflow), and [`docs/reference-media.md`](docs/reference-media.md) (83-photo & 2-video Vanguard `Stock #2229` camera calibration index).

### Changed
- **`mustang/export.py`, `mustang/printcheck.py`, `mustang/make_project.sh`, `mustang/animate.py`**:
  - Registered `knuckle_r`, `knuckle_l`, and `steering_link` in `export.PARTS` (`45` part entries + `2` inlays = `47` STL files making `66` total printed pieces; `printcheck.run()["parts"] == 65`), added `("Knuckle", "Rim")` to `printcheck.PRESS_FITS`, added `Knuckle_L/R` to `export.HINGED` and `animate.bake_showcase()`, and updated `2_black` plate group in `make_project.sh`.

---

## [v2.4.0] - 2026-10-16 — Partitioned Motor-to-Battery Wire Conduit & Mechanical Door Interlocks

### Added
- **Approach A Partitioned Motor-to-Battery Wire Conduit (`mustang/engine_bay.py`, `mustang/interior.py`, `mustang/details.py`, `mustang/materials.py`)**:
  - Created a continuous, fully enclosed driver-side floor wire channel (`Y = -154.0..-74.0` real / `Y = -7.70..-3.70 mm` print, `4.00 × 5.05 mm` clear interior cross-section) isolated from the rotating `Driveshaft` tunnel (`Y = -50.0..+50.0`) by a solid `1.20 mm` partition wall (`Y = -74.0..-50.0`):
    1. `BayTub_N25WireFront`, `BayTub_N25WireRear`, `BayTub_WirePartition`, `BayTub_WireOuterWall`, and `BayTub_WireTunnel` (`X = 486..1655`).
    2. `Cut_FirewallWireWeb` (`X = 1600..1680`) through the body firewall web.
    3. Widened `Tub_Tunnel` (`Y = -168..+168`) with `Tub_WireTunnel` (`X = 1615..3425`) under the cabin floor and fold-down cargo shelf.
    4. `Cut_WireTunnel` (`X = 3400..4015, Z = 598..688`) through the rear seat-back bulkhead and under-floor web.
    5. `BootTub_WireEntry` (`X = 3960..4050`) opening directly into the left Receiver/ESC compartment of `BootTub`.
- **Mechanical `DoorVent` & `DoorCard` Interlocks (`mustang/doors.py`, `mustang/build.py`)**:
  - **Door Card 6-Bay Mortise-and-Tenon Interlock**: Added 6 recessed mortise bays (`Door_L/R_CardBay0..5`, `1.20 mm` deep) inside the inner face of `Door_L/R` and 6 matching raised boss pads (`DoorCard_L/R_Pad0..5`, `1.10 mm` proud, `0.25 mm` perimeter clearance) on the back of `DoorCard_L/R`, providing `166.7 mm³` outboard engagement and positive fore-aft (`5.9 mm³`) and vertical (`8.6 mm³`) shear lock.
  - **Captured Vent Window Sill U-Channel**: Extended the front and rear lower legs of `DoorVent_L/R` downward by `24.0 mm` real (`1.20 mm` print) as integral mounting tenons seated inside matching sill mortise slots in both `Door_L/R` (`Door_VentSlot`) and `DoorCard_L/R` (`DoorCard_VentSlot`), mechanically capturing `DoorVent_L/R` when `DoorCard_L/R` is installed (`0.0 mm³` static overlap across `0°..55°` door swing).

---

## [v2.3.0] - 2026-10-16 — Enlarged `N25` Motor Cradle, 4-Stage Bevel Drivetrain & 6-Point V8 Mounts

### Added
- **4-Stage Mechanical Rear Axle Drivetrain (`mustang/engine_bay.py`, `mustang/details.py`, `mustang/export.py`)**:
  - Added `AxleGear` (`axle_gear.stl`, `31.1 mm³`), a `12`-tooth crown bevel gear (`pitch Ø 8.8 mm`, octagonal center bore keyed to `Axle_R`) that meshes at `90°` with `Driveshaft`'s `10`-tooth rear conical bevel pinion (`1.20 : 1` gear reduction) and front D-bore coupler (`Driveshaft_DBore`, keyed to the `N25` `Ø 3.0 mm` / `2.5 mm` flat D-shaft).
  - Added `Cut_ChassisAxlePinion` and `Cut_ChassisAxleGear` clearance pockets inside the rear differential housing of `Chassis`.
- **Enlarged `EngineBlock` Cavity & 6-Point Structural Mounts (`mustang/engine_bay.py`)**:
  - Expanded `Engine_N25Cavity` (`p_wide` `324 mm` real / `16.2 mm` print width, `X = 842..1412`) so the blue 289 V8 `EngineBlock` drops cleanly over the `N25` motor (`0.0 mm³` interference).
  - Added 6 structural engine mounts (`Engine_MountF-1/1`, `Engine_MountR-1/1`, `Engine_BellhousingMount-1/1`), full-length bottom cradle rails (`Engine_CradleRail-1/1`, `Engine_BellhousingRail-1/1`) providing `356.35 mm²` flat Z-floor contact (`X = 43.3..79.0 mm`, CoM inside support polygon), and `BayTub_EngineGuideL/R` lateral locating ribs (`32.8 mm³` lateral lock, `111.7 mm³` fore-aft lock).

---

## [v2.2.0] - 2026-10-16 — Full-Chrome Window Perimeter Surround & 144-Frame 360° Showcase Animation

### Added
- **Full-Chrome Side Window & Quarter Louver Trim (`mustang/details.py`, `mustang/doors.py`, `mustang/materials.py`)**:
  - Mapped `Cut_WindowOpen` to `Chrome`, added `DoorBeltTrim_L/R` (`X = 1785..2784, width = 17.0`) along the door window sills, extended `drip_rail` (`DRIP_RAIL = (-2.0, 22.0, 0.38)`) around the rear quarter window pillar (`X = 2887.0`) and quarter sill (`X = 2804.0`), thickened `DoorVent_L/R` (`VENT_FRAME = 18.0, VENT_T = 1.25`), and raised `Add_WindshieldTrim` and `Add_RearGlassTrim` (`0.38 mm` proud).
- **144-Frame 360° Showcase Animation (`mustang/animate.py`, `mustang/readme_images.sh`)**:
  - Updated `animate.py` (`FRAMES = END = 144`, `24 fps`, Cycles Metal GPU with `use_persistent_data = True`) to key `Hood` (`42°`), `Door_L/R` (`55°`), and `TrunkLid` (`-40°`) across a full `360°` camera orbit, and updated `readme_images.sh` frame indices (`1, 28, 40, 68, 88`).

---

## [v2.1.0] - 2026-10-15 — Authentic 1967 Front Fascia, Deep Headlight Buckets & Metal GPU Rendering

### Added
- **1967 V-Prow Nose Rake & Recessed `7"` Sealed-Beam Headlight Buckets (`mustang/body.py`, `mustang/details.py`, `mustang/materials.py`)**:
  - Updated `body.rake(x, z, y)` with `v_prow`, `fender_setback`, and `w_tip` to match the 1967 Mustang's forward-jutting center grille prow and recessed outer fender tips (photos `(4)`, `(6)`, `(18)`, `(32)`, `(33)`).
  - Replaced shallow headlight recesses with deep body-coloured fender buckets (`headlight_bucket_cutter`, `HEADLIGHT_R = 86.0`, `HEADLIGHT_Y = 718.0`, `HEADLIGHT_Z = 684.0`, `HEADLIGHT_DEPTH = 5.4 mm`), wrapped `GrilleSurround` (`GRILLE_DEPTH = 3.2 mm`, `GrilleSurround_Skin`) inside the bucket mouths, and added fluted `SealedBeam` lens shading in `materials.py`.

---

## [v2.0.0] - 2026-10-15 — 1:20 Scale Upgrade, Torq-Thrust Rims, Fold-Down Cargo Deck & Opening Trunk

### Changed
- **Scale Upgrade from `1:24` to `1:20` (`mustang/body.py`, `mustang/build.py`, `mustang/wheels.py`, `mustang/features.py`, `mustang/studio.py`)**:
  - Changed `body.SCALE` from `1.0 / 24.0` to `1.0 / 20.0` (`K = 1.2` linear scale factor, `1.728×` volume; assembled car dimensions `226 × 91 × 66 mm`), increasing ray-cast envelopes (`far = 300.0` in `features.py`) and studio camera distances proportionally.
- **Refined Proportions, 5-Spoke Torq-Thrust Rims, Fold-Down Sport Deck & Opening `TrunkLid`**:
  - Softened rear quarter lower tuck (`QUARTER_TUCK = 3760.0, QUARTER_TUCK_SLOPE = 0.72, QUARTER_TUCK_CAP = (165.0, 215.0)`), upgraded C-pillar louvers from `9` to `11` slots (`louver_slots`), and deepened door side scoops (`1.35 mm`).
  - Sculpted crowned 5-spoke American Racing Torq-Thrust mag spokes with filleted windows (`wheels.py`, photos `(30)–(31)`).
  - Added sculpted front/rear seat bolsters and the 1967 Fastback fold-down rear cargo shelf (`Tub_CargoShelf` + `Tub_SeatTrimCargo0..4` in `interior.py`, photos `(45)–(58)`).
  - Added hinged `TrunkLid` (`trunk_lid.stl`, `-40°` opening around `X = 3985.0, Z = 1094.0`), rear `BootTub` (`boot_tub.stl`), `N25` motor cradle in `BayTub`, and `Driveshaft` (`driveshaft.stl`).

---

## [v1.1.0] - 2026-10-15 — Vanguard Stock #2229 Full Reference Media Expansion

### Added
- Expanded `origin_images/` from 21 dealer photos to **83 high-resolution photos (`(1)`–`(83)`)**, **2 walkaround/inspection videos (`1967-ford-mustang-fastback-video.mp4`, `vanguard_30_sec_about_us.mp4`)**, and `vanguard_2229_manifest.json` covering exterior trim, wheels, interior sport deck, trunk bay, engine bay, and chassis undercarriage.

---

## [v1.0.0] - 2026-10-14 — Baseline 1:24 Procedural Printable Model

### Added
- Initial procedural Blender codebase (`mustang/body.py`, `features.py`, `details.py`, `bumpers.py`, `doors.py`, `engine_bay.py`, `interior.py`, `wheels.py`, `materials.py`, `printcheck.py`, `export.py`, `studio.py`, `animate.py`, `make_project.sh`, `merge_3mf.py`, `bambu_presets.py`, `check_plates.py`, `inspect_3mf.py`, `make_step.py`, `readme_images.sh`) at `1:24` scale (`40` STL entries, `60` pieces in 5 PLA colours) with opening hood and doors, static axles, Bambu Studio X2D project builder, and OpenCascade STEP CAD exporter.

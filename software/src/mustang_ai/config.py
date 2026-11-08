"""Hardware pinout, safety thresholds, and runtime configuration for the 1:20 Mustang AI Edition (`v3.3.0`)."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

ALLOWED_EMOJIS: tuple[str, ...] = (
    "CRUISE",
    "HAPPY",
    "WINK",
    "LAUGH",
    "COOL_SHADES",
    "HEART_EYES",
    "SURPRISED",
    "THINKING",
    "CONFUSED",
    "SLEEPY",
    "ANGRY_REV",
    "ALERT_STOP",
    "LOOK_LEFT",
    "LOOK_RIGHT",
    "SPEAKING",
)

CORE_12_EMOJIS: tuple[tuple[str, str], ...] = (
    ("CRUISE", "CRUISE READY"),
    ("HAPPY", "PURE V8 JOY!"),
    ("WINK", "YOU GOT IT!"),
    ("LAUGH", "HAHA NICE ONE!"),
    ("COOL_SHADES", "BORN TO RUN 67"),
    ("HEART_EYES", "FOLLOWING YOU"),
    ("SURPRISED", "WHOA NELLY!"),
    ("THINKING", "PLOTTING PATH"),
    ("CONFUSED", "WHERE'D U GO?"),
    ("SLEEPY", "IDLE ZZZ..."),
    ("ANGRY_REV", "289 V8 ROAR!"),
    ("ALERT_STOP", "BRAKE <120MM!"),
)

ALLOWED_MANEUVERS: tuple[str, ...] = (
    "circle_left",
    "circle_right",
    "figure_eight",
    "slalom",
    "spin_wiggle",
    "u_turn_3pt",
    "patrol",
)


def resolve_repo_root(start: pathlib.Path | None = None) -> pathlib.Path:
    """Resolve the repository root directory reliably across source checkouts and installed virtualenvs."""
    env_root = os.environ.get("MUSTANG_REPO_ROOT", "").strip()
    if env_root:
        candidate = pathlib.Path(env_root).expanduser().resolve()
        if candidate.is_dir():
            return candidate

    anchor = (start or pathlib.Path(__file__)).resolve()
    search_start = anchor if anchor.is_dir() else anchor.parent
    for parent in (search_start, *search_start.parents):
        if (parent / "mustang").is_dir() and (parent / "software").is_dir():
            return parent
    for parent in (search_start, *search_start.parents):
        if (parent / "pyproject.toml").is_file() and parent.name == "software" and parent.parent.is_dir():
            return parent.parent
    cwd = pathlib.Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / "mustang").is_dir() and (parent / "software").is_dir():
            return parent
    return search_start.parents[2] if len(search_start.parents) > 2 else cwd


def load_gemini_api_key() -> str:
    """Resolve `GEMINI_API_KEY` from environment variables or `.env` files (`~/.env`, `<repo>/.env`, `software/.env`)."""
    for env_var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val

    repo_root = resolve_repo_root()
    candidates = [
        pathlib.Path.home() / ".env",
        repo_root / ".env",
        repo_root / "software" / ".env",
    ]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.removeprefix("export ").strip()
                v = v.strip().strip("'").strip('"')
                if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v:
                    return v
        except Exception:
            continue
    return ""


@dataclass(frozen=True, slots=True)
class RadxaPinConfig:
    """40-pin GPIO header & bus mapping for Radxa Zero 3W (RK3566)."""

    # 1.28-inch Round GC9A01 240x240 RGB IPS TFT (SPI3_M0, Harness H2)
    spi_bus: int = 3
    spi_device: int = 0
    spi_speed_hz: int = 40_000_000
    gc9a01_dc_pin: int = 105      # Physical Pin 18 (GPIO3_B1)
    gc9a01_rst_pin: int = 106     # Physical Pin 22 (GPIO3_B2)
    gc9a01_bl_pin: int = 110      # Physical Pin 16 (GPIO3_B6)

    # DRV8833 Dual H-Bridge -> N25 100 RPM Gearmotor (Harnesses H3-C & H4-A)
    motor_in1_pwm_chip: int = 0   # Physical Pin 32 (PWM8_M0)
    motor_in1_pwm_chan: int = 0
    motor_in2_pwm_chip: int = 1   # Physical Pin 33 (PWM9_M0)
    motor_in2_pwm_chan: int = 0
    motor_pwm_freq_hz: int = 20_000

    # 1.7g Digital Micro Servo (Steering Knuckle_L/R via SteeringLink, Harness H4-B)
    servo_pwm_chip: int = 2       # Physical Pin 7 (PWM14_M0)
    servo_pwm_chan: int = 0
    servo_pwm_freq_hz: int = 50
    servo_min_pulse_us: int = 1000
    servo_center_pulse_us: int = 1500
    servo_max_pulse_us: int = 2000
    max_steering_deg: float = 15.0

    # VL53L1X Time-of-Flight Laser Rangefinder (I2C3_M0, Lower Front Valance, Harness H4-C)
    i2c_bus: int = 3              # Physical Pin 3 (SDA) / Pin 5 (SCL)
    vl53l1x_addr: int = 0x29
    tof_poll_hz: int = 50
    emergency_stop_mm: int = 120         # <20 ms hardware reflex brake threshold
    caution_slow_mm: int = 260           # Proportional speed cap zone (120..260 mm)
    caution_max_throttle: float = 0.35   # Maximum forward throttle in caution zone
    bypass_reverse_target_mm: int = 240  # Target clearance reached during auto-reverse (~150 mm back-up)
    deadman_timeout_sec: float = 0.100   # 100 ms Deadman Watchdog on stale ControlIntent

    # Person-Following Standoff & PD Control Parameters (Function 3)
    follow_standoff_mm: int = 350        # Ideal standoff distance when following a person
    follow_approach_mm: int = 450        # Distance above which the car drives forward to catch up
    follow_backup_mm: int = 220          # Personal-space buffer: car gently reverses if person steps <220 mm
    follow_kp_steer: float = 0.42        # Proportional steering gain (deg per deg of visual bearing error)
    follow_kd_steer: float = 0.08        # Derivative damping gain
    follow_lost_timeout_sec: float = 1.50

    # I2S3_M0 Audio Bus (INMP441 Mic H1-B + MAX98357A 3.2W Class-D Amp H3-A/B)
    alsa_capture_device: str = "hw:0,0"
    alsa_playback_device: str = "hw:0,1"
    audio_sample_rate_hz: int = 16_000
    audio_channels: int = 1
    audio_chunk_samples: int = 640       # 40 ms frames at 16 kHz
    barge_in_rms_threshold: float = 0.55  # Loud "Stop!" overrides half-duplex speaker mute


@dataclass(frozen=True, slots=True)
class PiperTTSConfig:
    """Local neural TTS (`piper-tts` ONNX) hosted on Radxa Zero 3W & Local Mac (`~25 MB` RAM, `16 kHz` PCM16)."""

    voice_name: str = "en_US-amy-low"
    piper_bin: str = "piper"
    onnx_model_path: str = "/opt/mustang/models/en_US-amy-low.onnx"
    sample_rate_hz: int = 16_000
    length_scale: float = 0.95
    ram_footprint_mb: int = 25


@dataclass(frozen=True, slots=True)
class CameraConfig:
    """OV5647 Wide-Angle / Fisheye MIPI CSI-2 camera settings inside WaymoPod (Harness H1-A)."""

    v4l2_device: str = "/dev/video0"
    width: int = 640
    height: int = 480
    fps: int = 15
    fov_diagonal_deg: float = 160.0
    jpeg_quality: int = 78
    fx: float = 215.0
    fy: float = 215.0
    cx: float = 320.0
    cy: float = 240.0


@dataclass(frozen=True, slots=True)
class GeminiERConfig:
    """Gemini Robotics ER 2.0 streaming configuration (`gemini-robotics-er-2-streaming-preview`)."""

    primary_model: str = "gemini-robotics-er-2-streaming-preview"
    fallback_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    thinking_budget: int = 0
    video_stream_hz: float = 5.0
    control_loop_hz: float = 15.0
    system_instruction: str = (
        "You are Eleanor, an embodied 1:20 1967 Ford Mustang Fastback AI muscle car "
        "running on a Radxa Zero 3W with a roof-mounted 160-degree OV5647 fisheye camera, "
        "a sub-surface 1.28-inch round GC9A01 rear window HUD, an INMP441 microphone, "
        "local Piper ONNX TTS voice synthesis over a MAX98357A speaker, and a front VL53L1X "
        "laser rangefinder. Keep spoken replies punchy, witty, and expressive, synchronize "
        "every reply with a fun emoji via `speak_with_emoji`, trigger tricks via "
        "`execute_maneuver`, and track people via `set_follow_person_mode`."
    )
    pins: RadxaPinConfig = field(default_factory=RadxaPinConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    tts: PiperTTSConfig = field(default_factory=PiperTTSConfig)

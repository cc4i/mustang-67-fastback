"""`1.28"` Round `GC9A01` `240×240` SPI rear window HUD HAL backends (`SimGC9A01Display` & `RadxaGC9A01Display`)."""

from __future__ import annotations

import math
import pathlib
import time

from PIL import Image, ImageDraw, ImageFont

from mustang_ai.config import ALLOWED_EMOJIS, CORE_12_EMOJIS, RadxaPinConfig
from mustang_ai.protocol.messages import HUDFrameState


class SimGC9A01Display:
    """Vector HUD compositor and RGB565 serializer for the `240×240` circular `GC9A01` screen (`Harness H2`)."""

    WIDTH = 240
    HEIGHT = 240

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        self.pins = pins or RadxaPinConfig()
        self._last_frame: Image.Image | None = None
        self.last_rgb565_bytes: bytes = b""
        self.frames_pushed: int = 0

    @staticmethod
    def image_to_rgb565_bytes(img: Image.Image) -> bytes:
        """Convert a `240×240` RGB PIL image into `115,200` big-endian `RGB565` bytes."""
        rgb = img.convert("RGB").resize((SimGC9A01Display.WIDTH, SimGC9A01Display.HEIGHT))
        raw = rgb.tobytes()
        out = bytearray(SimGC9A01Display.WIDTH * SimGC9A01Display.HEIGHT * 2)
        idx = 0
        for i in range(0, len(raw), 3):
            r = raw[i]
            g = raw[i + 1]
            b = raw[i + 2]
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[idx] = (rgb565 >> 8) & 0xFF
            out[idx + 1] = rgb565 & 0xFF
            idx += 2
        return bytes(out)

    @staticmethod
    def _draw_heart(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple[int, int, int]) -> None:
        r = max(4, size // 2)
        draw.ellipse((cx - size, cy - r, cx, cy + r // 2), fill=color)
        draw.ellipse((cx, cy - r, cx + size, cy + r // 2), fill=color)
        draw.polygon([(cx - size, cy), (cx + size, cy), (cx, cy + size + 2)], fill=color)

    @staticmethod
    def _draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r_outer: int, color: tuple[int, int, int]) -> None:
        r_in = max(2, r_outer // 3)
        pts = [
            (cx, cy - r_outer),
            (cx + r_in, cy - r_in),
            (cx + r_outer, cy),
            (cx + r_in, cy + r_in),
            (cx, cy + r_outer),
            (cx - r_in, cy + r_in),
            (cx - r_outer, cy),
            (cx - r_in, cy - r_in),
        ]
        draw.polygon(pts, fill=color)

    def render_image(self, state: HUDFrameState) -> Image.Image:
        """Render a `240×240` circular HUD frame supporting all 12 core fun emojis + telemetry."""
        emo = (state.emoji or "CRUISE").strip().upper()
        if emo not in ALLOWED_EMOJIS:
            emo = "CRUISE"

        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (6, 10, 18))
        draw = ImageDraw.Draw(img)
        cx = self.WIDTH // 2

        is_alert = state.alert_override or emo == "ALERT_STOP" or state.tof_mm < self.pins.emergency_stop_mm
        ring_palette = {
            "CRUISE": (0, 212, 255),
            "HAPPY": (52, 245, 165),
            "WINK": (255, 205, 45),
            "LAUGH": (255, 190, 30),
            "COOL_SHADES": (0, 230, 255),
            "HEART_EYES": (255, 65, 155),
            "SURPRISED": (255, 175, 0),
            "THINKING": (150, 115, 255),
            "CONFUSED": (255, 155, 60),
            "SLEEPY": (90, 135, 210),
            "ANGRY_REV": (255, 75, 25),
            "ALERT_STOP": (255, 45, 40),
            "LOOK_LEFT": (0, 212, 255),
            "LOOK_RIGHT": (0, 212, 255),
            "SPEAKING": (255, 145, 0),
        }
        ring_color = (255, 45, 40) if is_alert else ring_palette.get(emo, (0, 212, 255))

        draw.ellipse((4, 4, 236, 236), outline=(28, 44, 68), width=4)
        draw.ellipse((8, 8, 232, 232), outline=ring_color, width=3)

        steer_norm = max(-1.0, min(1.0, state.steering_deg / max(1.0, self.pins.max_steering_deg)))
        arc_center = 270.0 + steer_norm * 35.0
        draw.arc((14, 14, 226, 226), start=arc_center - 12, end=arc_center + 12, fill=(52, 245, 165), width=5)

        eye_shift_x = int(steer_norm * 18.0)
        if emo == "LOOK_LEFT":
            eye_shift_x = -20
        elif emo == "LOOK_RIGHT":
            eye_shift_x = 20

        eye_y = 88
        lx = cx - 42 + eye_shift_x
        rx = cx + 42 + eye_shift_x

        if is_alert or emo == "ALERT_STOP":
            for ex in (lx, rx):
                draw.rounded_rectangle((ex - 20, eye_y - 20, ex + 20, eye_y + 20), radius=8, fill=(255, 50, 45))
                draw.ellipse((ex - 6, eye_y - 6, ex + 6, eye_y + 6), fill=(255, 240, 240))
            draw.polygon([(cx, 40), (cx - 14, 64), (cx + 14, 64)], outline=(255, 210, 60), fill=(255, 60, 40))
        elif emo == "HEART_EYES":
            self._draw_heart(draw, lx, eye_y - 4, 20, (255, 55, 140))
            self._draw_heart(draw, rx, eye_y - 4, 20, (255, 55, 140))
            self._draw_star(draw, cx, 52, 7, (255, 180, 220))
        elif emo == "COOL_SHADES":
            draw.line((lx - 28, eye_y - 16, rx + 28, eye_y - 16), fill=(220, 235, 255), width=4)
            for ex in (lx, rx):
                draw.rounded_rectangle(
                    (ex - 26, eye_y - 16, ex + 26, eye_y + 18),
                    radius=9,
                    fill=(14, 32, 54),
                    outline=(0, 230, 255),
                    width=3,
                )
                draw.line((ex - 16, eye_y + 10, ex + 8, eye_y - 10), fill=(190, 245, 255), width=3)
        elif emo == "WINK":
            draw.arc((lx - 20, eye_y - 8, lx + 20, eye_y + 16), start=190, end=350, fill=ring_color, width=5)
            draw.rounded_rectangle((rx - 20, eye_y - 26, rx + 20, eye_y + 24), radius=10, fill=ring_color)
            draw.ellipse((rx - 6, eye_y - 8, rx + 6, eye_y + 4), fill=(245, 252, 255))
            self._draw_star(draw, rx + 26, eye_y - 24, 9, (255, 230, 90))
        elif emo == "LAUGH":
            draw.line((lx - 18, eye_y - 12, lx + 14, eye_y), fill=ring_color, width=5)
            draw.line((lx - 18, eye_y + 12, lx + 14, eye_y), fill=ring_color, width=5)
            draw.line((rx + 18, eye_y - 12, rx - 14, eye_y), fill=ring_color, width=5)
            draw.line((rx + 18, eye_y + 12, rx - 14, eye_y), fill=ring_color, width=5)
            draw.ellipse((lx - 26, eye_y + 6, lx - 16, eye_y + 18), fill=(0, 225, 255))
            draw.ellipse((rx + 16, eye_y + 6, rx + 26, eye_y + 18), fill=(0, 225, 255))
        elif emo == "HAPPY":
            for ex in (lx, rx):
                draw.arc((ex - 22, eye_y - 18, ex + 22, eye_y + 22), start=195, end=345, fill=ring_color, width=6)
        elif emo == "SURPRISED":
            for ex in (lx, rx):
                draw.ellipse((ex - 22, eye_y - 24, ex + 22, eye_y + 24), outline=ring_color, width=4)
                draw.ellipse((ex - 5, eye_y - 5, ex + 5, eye_y + 5), fill=(255, 250, 220))
        elif emo == "THINKING":
            draw.rounded_rectangle((lx - 18, eye_y - 14, lx + 18, eye_y + 14), radius=8, fill=ring_color)
            draw.rounded_rectangle((rx - 20, eye_y - 26, rx + 20, eye_y + 24), radius=10, fill=ring_color)
            draw.ellipse((lx - 4, eye_y - 8, lx + 6, eye_y + 2), fill=(245, 250, 255))
            draw.ellipse((rx - 2, eye_y - 14, rx + 8, eye_y - 4), fill=(245, 250, 255))
            for dx, r_dot in ((-14, 3), (0, 4), (16, 5)):
                draw.ellipse((cx + dx - r_dot, 46 - r_dot, cx + dx + r_dot, 46 + r_dot), fill=(200, 180, 255))
        elif emo == "CONFUSED":
            for ex in (lx, rx):
                draw.rounded_rectangle((ex - 18, eye_y - 18, ex + 18, eye_y + 18), radius=8, fill=ring_color)
                draw.ellipse((ex - 5, eye_y - 5, ex + 5, eye_y + 5), fill=(245, 250, 255))
            draw.line((lx - 20, eye_y - 28, lx + 18, eye_y - 22), fill=(255, 210, 120), width=4)
            draw.line((rx - 18, eye_y - 20, rx + 20, eye_y - 30), fill=(255, 210, 120), width=4)
            draw.text((cx - 4, 38), "?", fill=(255, 220, 110), font=ImageFont.load_default())
        elif emo == "SLEEPY":
            for ex in (lx, rx):
                draw.line((ex - 20, eye_y, ex + 20, eye_y), fill=ring_color, width=5)
                draw.arc((ex - 18, eye_y - 6, ex + 18, eye_y + 12), start=10, end=170, fill=ring_color, width=3)
            draw.text((rx + 8, 44), "Zzz", fill=(150, 195, 255), font=ImageFont.load_default())
        elif emo == "ANGRY_REV":
            for ex, sign in ((lx, 1), (rx, -1)):
                draw.rounded_rectangle((ex - 20, eye_y - 22, ex + 20, eye_y + 20), radius=8, fill=(255, 70, 20))
                draw.line((ex - 22, eye_y - 26 - sign * 6, ex + 22, eye_y - 20 + sign * 8), fill=(255, 210, 40), width=5)
                draw.ellipse((ex - 5, eye_y - 4, ex + 5, eye_y + 6), fill=(255, 245, 200))
        else:
            for ex in (lx, rx):
                draw.rounded_rectangle((ex - 20, eye_y - 28, ex + 20, eye_y + 28), radius=10, fill=ring_color)
                draw.ellipse((ex - 5, eye_y - 6, ex + 5, eye_y + 4), fill=(240, 252, 255))

        bar_count = 13
        bar_spacing = 11
        start_x = cx - ((bar_count - 1) * bar_spacing) // 2
        wave_y = 148
        amp = max(
            0.08,
            min(
                1.0,
                state.voice_rms
                if state.voice_rms > 0.05
                else abs(state.throttle) * 0.6 + 0.16,
            ),
        )
        phase = state.timestamp_s * 8.0
        for idx in range(bar_count):
            bx = start_x + idx * bar_spacing
            env = math.cos(((idx - (bar_count - 1) / 2.0) / (bar_count / 2.0)) * (math.pi / 2.0))
            bh = int(4 + 22 * amp * max(0.15, env) * (0.65 + 0.35 * math.sin(phase + idx * 0.7)))
            draw.rounded_rectangle(
                (bx - 3, wave_y - bh, bx + 3, wave_y + bh),
                radius=2,
                fill=(0, 235, 195) if not is_alert else (255, 80, 60),
            )

        font = ImageFont.load_default()
        clean_msg = (state.caption or emo).strip().upper()[:16]
        msg_bbox = draw.textbbox((0, 0), clean_msg, font=font)
        msg_w = msg_bbox[2] - msg_bbox[0]
        draw.text((cx - msg_w // 2, 182), clean_msg, fill=(235, 245, 255), font=font)

        telemetry_str = f"TOF {state.tof_mm:4d}MM | STR {state.steering_deg:+4.0f}D"
        tel_bbox = draw.textbbox((0, 0), telemetry_str, font=font)
        tel_w = tel_bbox[2] - tel_bbox[0]
        draw.text((cx - tel_w // 2, 202), telemetry_str, fill=(135, 175, 210), font=font)

        self._last_frame = img
        return img

    def render_and_push(self, state: HUDFrameState) -> int:
        img = self.render_image(state)
        self.last_rgb565_bytes = self.image_to_rgb565_bytes(img)
        self.frames_pushed += 1
        return len(self.last_rgb565_bytes)

    def last_rgb_image(self) -> Image.Image:
        if self._last_frame is None:
            default_state = HUDFrameState(
                timestamp_s=time.monotonic(),
                emoji="CRUISE",
                caption="CRUISE READY",
                tof_mm=850,
                steering_deg=0.0,
            )
            return self.render_image(default_state)
        return self._last_frame

    def render_emoji_contact_sheet(self, path: str | pathlib.Path) -> pathlib.Path:
        """Render a `4×3` contact sheet (`960×720`) showcasing all 12 expressive `GC9A01` fun emojis."""
        cols, rows = 4, 3
        sheet = Image.new("RGB", (cols * self.WIDTH, rows * self.HEIGHT), (6, 10, 18))
        for idx, (emo, caption) in enumerate(CORE_12_EMOJIS):
            r, c = divmod(idx, cols)
            tof_sample = 92 if emo == "ALERT_STOP" else (345 if emo == "HEART_EYES" else 520)
            steer_sample = -12.0 if emo == "COOL_SHADES" else (8.0 if emo == "WINK" else 0.0)
            state = HUDFrameState(
                timestamp_s=1.0 + idx * 0.25,
                emoji=emo,
                caption=caption,
                tof_mm=tof_sample,
                steering_deg=steer_sample,
                throttle=0.55 if emo in ("COOL_SHADES", "ANGRY_REV") else 0.25,
                voice_rms=0.72 if emo in ("LAUGH", "HAPPY", "WINK", "ANGRY_REV") else 0.20,
                alert_override=(emo == "ALERT_STOP"),
            )
            frame = self.render_image(state)
            sheet.paste(frame, (c * self.WIDTH, r * self.HEIGHT))
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target)
        return target


class RadxaGC9A01Display(SimGC9A01Display):
    """Physical `SPI3` (`/dev/spidev3.0` @ `40 MHz`) `GC9A01` display driver on Radxa Zero 3W (`Harness H2`)."""

    def __init__(self, pins: RadxaPinConfig | None = None) -> None:
        super().__init__(pins=pins)
        self._spi = None
        try:
            import spidev  # type: ignore[import-not-found]

            spi = spidev.SpiDev()
            spi.open(self.pins.spi_bus, self.pins.spi_device)
            spi.max_speed_hz = self.pins.spi_speed_hz
            spi.mode = 0
            self._spi = spi
            self._init_gc9a01_registers()
        except Exception:
            self._spi = None

    def _init_gc9a01_registers(self) -> None:
        if self._spi is None:
            return
        init_seq = [
            (0xEF, b""),
            (0xEB, b"\x14"),
            (0xFE, b""),
            (0xEF, b""),
            (0x36, b"\x48"),
            (0x3A, b"\x05"),
            (0x21, b""),
            (0x11, b""),
            (0x29, b""),
        ]
        for cmd, payload in init_seq:
            self._spi.xfer2([cmd] + list(payload))

    def render_and_push(self, state: HUDFrameState) -> int:
        count = super().render_and_push(state)
        if self._spi is not None:
            chunk = 4096
            payload = self.last_rgb565_bytes
            for offset in range(0, len(payload), chunk):
                self._spi.xfer2(list(payload[offset : offset + chunk]))
        return count

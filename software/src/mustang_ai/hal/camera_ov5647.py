"""`OV5647` `160°` Fisheye Camera HAL backends (`SimFisheyeCamera` & `RadxaOV5647`, Harness `H1-A`)."""

from __future__ import annotations

import io
import math
import time
from typing import Callable, Literal

from PIL import Image, ImageDraw

from mustang_ai.config import CameraConfig
from mustang_ai.protocol.messages import VisionFrameMetrics


def _compute_vision_metrics_from_rgb(
    rgb_bytes: bytes,
    config: CameraConfig,
    frame_seq: int,
    target_box_2d: tuple[int, int, int, int] | None = None,
    target_mode: str = "body_legs_torso",
) -> VisionFrameMetrics:
    """Shared pixel-level ROI obstacle clearance and equidistant fisheye person bearing extractor."""
    w, h = config.width, config.height
    frame = Image.frombytes("RGB", (w, h), rgb_bytes)
    y0, y1 = int(h * 0.46), int(h * 0.74)
    left_roi = frame.crop((int(w * 0.06), y0, int(w * 0.44), y1))
    right_roi = frame.crop((int(w * 0.56), y0, int(w * 0.94), y1))

    def _obstacle_clutter(patch: Image.Image) -> float:
        raw = patch.tobytes()
        total = 0.0
        n = max(1, len(raw) // 3)
        for i in range(0, len(raw), 3):
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            total += abs(r - 36) * 1.4 + abs(g - 42) + abs(b - 50)
        return total / n

    left_clear = max(1.0, 255.0 - _obstacle_clutter(left_roi))
    right_clear = max(1.0, 255.0 - _obstacle_clutter(right_roi))
    preferred_dir: Literal[-1, 1] = -1 if left_clear >= right_clear else 1

    # Auto-detect bright/teal person silhouette in frame if no explicit hint box is supplied
    box = target_box_2d
    if box is None:
        # Fast scan on 8x8 pixel grid for synthetic/high-visibility person target (RGB ~ (40, 215, 170))
        min_x, max_x, min_y, max_y = w, -1, h, -1
        for py in range(int(h * 0.12), int(h * 0.76), 8):
            row_offset = py * w * 3
            for px in range(16, w - 16, 8):
                idx = row_offset + px * 3
                r, g, b = rgb_bytes[idx], rgb_bytes[idx + 1], rgb_bytes[idx + 2]
                if g > 175 and b > 130 and r < 95:
                    if px < min_x:
                        min_x = px
                    if px > max_x:
                        max_x = px
                    if py < min_y:
                        min_y = py
                    if py > max_y:
                        max_y = py
        if max_x > min_x and max_y > min_y:
            box = (
                int(min_y * 1000 / h),
                int(min_x * 1000 / w),
                int(max_y * 1000 / h),
                int(max_x * 1000 / w),
            )

    detected = False
    bearing_deg = 0.0
    cx_norm = 0.0
    cy_norm = 0.0
    height_norm = 0.0
    clean_box: tuple[int, int, int, int] | None = None

    if box is not None and len(box) == 4:
        ymin, xmin, ymax, xmax = [max(0, min(1000, int(v))) for v in box]
        if xmax > xmin and ymax > ymin:
            detected = True
            clean_box = (ymin, xmin, ymax, xmax)
            u_px = ((xmin + xmax) * 0.5 / 1000.0) * w
            v_px = ((ymin + ymax) * 0.5 / 1000.0) * h
            cx_norm = max(-1.0, min(1.0, (u_px - config.cx) / (w * 0.5)))
            cy_norm = max(-1.0, min(1.0, (v_px - config.cy) / (h * 0.5)))
            height_norm = max(0.0, min(1.0, (ymax - ymin) / 1000.0))
            theta_rad = (u_px - config.cx) / max(1.0, config.fx)
            bearing_deg = round(math.degrees(theta_rad), 2)

    return VisionFrameMetrics(
        timestamp_s=time.monotonic(),
        frame_seq=frame_seq,
        rgb_bytes=rgb_bytes,
        left_clearance_score=round(left_clear, 2),
        right_clearance_score=round(right_clear, 2),
        preferred_bypass_dir=preferred_dir,
        person_detected=detected,
        person_bearing_deg=bearing_deg,
        person_box_2d=clean_box,
        person_cx_norm=round(cx_norm, 4),
        person_cy_norm=round(cy_norm, 4),
        person_height_norm=round(height_norm, 4),
        target_kind=target_mode,
    )


def _encode_jpeg_with_banner(
    rgb_bytes: bytes,
    config: CameraConfig,
    tof_mm: int,
    steer_deg: float,
    emoji: str,
    mode: str,
) -> bytes:
    img = Image.frombytes("RGB", (config.width, config.height), rgb_bytes)
    draw = ImageDraw.Draw(img)
    banner = f"TOF:{tof_mm:4d}MM STR:{steer_deg:+5.1f}D EMO:{emoji[:10]} MODE:{mode[:12]}"
    draw.rectangle((8, 8, 460, 28), fill=(10, 14, 22))
    draw.text((14, 12), banner[:62], fill=(0, 225, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=config.jpeg_quality)
    return buf.getvalue()


class SimFisheyeCamera:
    """Synthetic `640×480` `160°` fisheye camera (`Harness H1-A`) for unit tests and `VirtualArena`."""

    def __init__(
        self,
        config: CameraConfig | None = None,
        frame_provider: Callable[[], bytes] | None = None,
    ) -> None:
        self.config = config or CameraConfig()
        self._frame_provider = frame_provider
        self._frame_seq: int = 0
        self._obstacle_side: str | None = None
        self._person_box_2d: tuple[int, int, int, int] | None = None

    def set_scene(
        self,
        obstacle_side: str | None = None,
        person_box_2d: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Configure synthetic left/right obstacle cone and person bounding box (`[ymin, xmin, ymax, xmax]`)."""
        self._obstacle_side = obstacle_side
        self._person_box_2d = person_box_2d

    def capture_frame(self) -> bytes:
        self._frame_seq += 1
        if self._frame_provider is not None:
            return self._frame_provider()

        w, h = self.config.width, self.config.height
        img = Image.new("RGB", (w, h), (18, 24, 34))
        draw = ImageDraw.Draw(img)
        horizon_y = int(h * 0.46)
        draw.rectangle((0, horizon_y, w, h), fill=(36, 42, 50))
        draw.line((w // 2 - 40, horizon_y, 40, h), fill=(90, 210, 255), width=3)
        draw.line((w // 2 + 40, horizon_y, w - 40, h), fill=(90, 210, 255), width=3)

        if self._obstacle_side == "left":
            draw.polygon([(140, 220), (85, 345), (195, 345)], fill=(235, 65, 45))
        elif self._obstacle_side == "right":
            draw.polygon([(500, 220), (445, 345), (555, 345)], fill=(235, 65, 45))

        if self._person_box_2d is not None:
            ymin, xmin, ymax, xmax = self._person_box_2d
            x0, x1 = int(xmin * w / 1000.0), int(xmax * w / 1000.0)
            y0, y1 = int(ymin * h / 1000.0), int(ymax * h / 1000.0)
            draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=(40, 215, 170), outline=(220, 255, 245), width=2)

        hood_poly = [
            (int(w * 0.16), h),
            (int(w * 0.28), int(h * 0.78)),
            (int(w * 0.50), int(h * 0.74)),
            (int(w * 0.72), int(h * 0.78)),
            (int(w * 0.84), h),
        ]
        draw.polygon(hood_poly, fill=(107, 15, 26), outline=(185, 40, 55))
        return img.tobytes()

    def extract_vision_metrics(
        self,
        rgb_bytes: bytes,
        target_box_2d: tuple[int, int, int, int] | None = None,
        target_mode: str = "body_legs_torso",
    ) -> VisionFrameMetrics:
        effective_box = target_box_2d if target_box_2d is not None else self._person_box_2d
        return _compute_vision_metrics_from_rgb(
            rgb_bytes=rgb_bytes,
            config=self.config,
            frame_seq=self._frame_seq,
            target_box_2d=effective_box,
            target_mode=target_mode,
        )

    def encode_telemetry_jpeg(
        self,
        rgb_bytes: bytes,
        tof_mm: int,
        steer_deg: float,
        emoji: str,
        mode: str,
    ) -> bytes:
        return _encode_jpeg_with_banner(rgb_bytes, self.config, tof_mm, steer_deg, emoji, mode)


class RadxaOV5647:
    """Physical `OV5647` V4L2 (`/dev/video0`) MIPI CSI-2 camera driver for Radxa Zero 3W (`Harness H1-A`)."""

    def __init__(self, config: CameraConfig | None = None) -> None:
        self.config = config or CameraConfig()
        self._frame_seq: int = 0
        self._cap = None
        self._fallback_sim = SimFisheyeCamera(self.config)
        try:
            import cv2  # type: ignore[import-not-found]

            cap = cv2.VideoCapture(self.config.v4l2_device)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
                cap.set(cv2.CAP_PROP_FPS, self.config.fps)
                self._cap = cap
        except Exception:
            self._cap = None

    def capture_frame(self) -> bytes:
        self._frame_seq += 1
        if self._cap is not None:
            try:
                import cv2  # type: ignore[import-not-found]

                ok, frame = self._cap.read()
                if ok and frame is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb).resize((self.config.width, self.config.height))
                    return img.tobytes()
            except Exception:
                pass
        return self._fallback_sim.capture_frame()

    def extract_vision_metrics(
        self,
        rgb_bytes: bytes,
        target_box_2d: tuple[int, int, int, int] | None = None,
        target_mode: str = "body_legs_torso",
    ) -> VisionFrameMetrics:
        return _compute_vision_metrics_from_rgb(
            rgb_bytes=rgb_bytes,
            config=self.config,
            frame_seq=self._frame_seq,
            target_box_2d=target_box_2d,
            target_mode=target_mode,
        )

    def encode_telemetry_jpeg(
        self,
        rgb_bytes: bytes,
        tof_mm: int,
        steer_deg: float,
        emoji: str,
        mode: str,
    ) -> bytes:
        return _encode_jpeg_with_banner(rgb_bytes, self.config, tof_mm, steer_deg, emoji, mode)

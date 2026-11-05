"""2D Bicycle-Kinematics `VirtualArena` Simulator (`virtual_arena.py`) for the 1:20 Mustang AI Edition (`v3.2.0`).

Models the physical `1:20` Mustang (`226 × 91 × 66 mm`, wheelbase `L = 138.0 mm`, max speed `550 mm/s`),
ray-casts synthetic `VL53L1X` ToF laser range against obstacles and a walking person, renders
rich `640×480` `160°` equidistant fisheye camera frames (including 3D-projected Slalom Cones `CONE 1..4`,
perspective road lane markings, and recognizable visual objects for multimodal Q&A), and renders a
live 2D Top-Down Track & Slalom Course Radar (`render_topdown_map_image`).
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from mustang_ai.config import CameraConfig
from mustang_ai.features.maneuver_obstacle import MANEUVER_LIBRARY
from mustang_ai.protocol.messages import CompiledActuatorCommand

SHOWCASE_OBJECT_CATALOG: dict[str, str] = {
    "stop_sign": "Red Octagonal STOP Sign",
    "traffic_cone": "Orange & White Traffic Cone",
    "soccer_ball": "Black & White Soccer Ball",
    "coffee_mug": "Steaming Hot Coffee Mug",
    "checkered_flag": "Black & White Checkered Racing Flag",
    "person": "Walking Person in Teal Jacket",
}


@dataclass(slots=True)
class ArenaObstacle:
    """Circular or box obstacle placed at `(x_mm, y_mm)` in the 2D virtual arena."""

    x_mm: float
    y_mm: float
    radius_mm: float = 55.0
    color: tuple[int, int, int] = (235, 65, 45)


@dataclass(slots=True)
class CourseMarker:
    """Visual slalom cone or maneuver gate marker placed on the 2D track (does not block ToF laser)."""

    x_mm: float
    y_mm: float
    label: str
    kind: str = "slalom_cone"


class VirtualArena:
    """2D physical arena simulator with ray-cast `VL53L1X` ToF, `OV5647` `160°` fisheye view, and 2D Track Radar."""

    WHEELBASE_MM = 138.0
    FRONT_VALANCE_OFFSET_MM = 113.0
    MAX_SPEED_MM_S = 550.0

    def __init__(
        self,
        camera_config: CameraConfig | None = None,
        car_x_mm: float = 0.0,
        car_y_mm: float = 0.0,
        car_heading_rad: float = 0.0,
    ) -> None:
        self.camera_config = camera_config or CameraConfig()
        self.car_x_mm: float = car_x_mm
        self.car_y_mm: float = car_y_mm
        self.car_heading_rad: float = car_heading_rad
        self.last_steer_deg: float = 0.0
        self.obstacles: list[ArenaObstacle] = []
        self.course_markers: list[CourseMarker] = []
        self.planned_path_xy_mm: list[tuple[float, float]] = []
        self.active_maneuver_name: str = ""
        self.showcase_object: str | None = None
        self.person_xy_mm: tuple[float, float] | None = None
        self.person_radius_mm: float = 65.0
        self.trajectory_xy_mm: list[tuple[float, float]] = [(car_x_mm, car_y_mm)]
        self.min_obstacle_clearance_mm: float = 4000.0

    def add_obstacle(self, x_mm: float, y_mm: float, radius_mm: float = 55.0) -> None:
        self.obstacles.append(ArenaObstacle(x_mm=x_mm, y_mm=y_mm, radius_mm=radius_mm))

    def set_person_position(self, x_mm: float | None, y_mm: float | None = None) -> None:
        if x_mm is None or y_mm is None:
            self.person_xy_mm = None
        else:
            self.person_xy_mm = (float(x_mm), float(y_mm))

    def set_showcase_object(self, kind: str | None) -> dict[str, object]:
        """Place a recognizable visual object directly in front of the Mustang's `OV5647` camera for multimodal Q&A."""
        clean = (kind or "").strip().lower()
        if not clean or clean in ("none", "clear"):
            self.showcase_object = None
            return {"showcase_object": None, "description": "Cleared visual object"}
        if clean == "person":
            self.showcase_object = "person"
            px = self.car_x_mm + 420.0 * math.cos(self.car_heading_rad)
            py = self.car_y_mm + 420.0 * math.sin(self.car_heading_rad)
            self.set_person_position(px, py)
            return {"showcase_object": "person", "description": SHOWCASE_OBJECT_CATALOG["person"]}
        if clean not in SHOWCASE_OBJECT_CATALOG:
            clean = "stop_sign"
        self.showcase_object = clean
        return {"showcase_object": clean, "description": SHOWCASE_OBJECT_CATALOG[clean]}

    def setup_maneuver_course(self, maneuver_name: str, speed_scale: float = 0.90) -> None:
        """Reset track origin, pre-compute the planned maneuver path, and place visual Slalom Cones / Pylons."""
        name = (maneuver_name or "").strip().lower()
        self.active_maneuver_name = name
        self.car_x_mm = 0.0
        self.car_y_mm = 0.0
        self.car_heading_rad = 0.0
        self.last_steer_deg = 0.0
        self.trajectory_xy_mm = [(0.0, 0.0)]
        self.obstacles.clear()
        self.course_markers.clear()
        self.planned_path_xy_mm = [(0.0, 0.0)]

        steps = MANEUVER_LIBRARY.get(name)
        if not steps:
            return

        # Pre-simulate the ideal trajectory of the maneuver to draw the dashed target path and position cones
        sim_x, sim_y, sim_h = 0.0, 0.0, 0.0
        dt = 0.05
        scale = max(0.4, min(1.0, float(speed_scale)))
        phase_boundaries_xy: list[tuple[float, float]] = []
        for st in steps:
            n_ticks = max(1, int(round(st.duration_sec / dt)))
            v = st.throttle * scale * self.MAX_SPEED_MM_S
            sr = math.radians(st.steering_deg)
            for _ in range(n_ticks):
                sim_x += v * math.cos(sim_h) * dt
                sim_y += v * math.sin(sim_h) * dt
                sim_h += (v / self.WHEELBASE_MM) * math.tan(sr) * dt
                self.planned_path_xy_mm.append((round(sim_x, 1), round(sim_y, 1)))
            phase_boundaries_xy.append((sim_x, sim_y))

        if name == "slalom":
            # Place 4 numbered Slalom Cones inside each weave lobe so the car weaves left-right-left-right around them
            for idx, (bx, by) in enumerate(phase_boundaries_xy[:4]):
                # Offset each cone toward the centerline opposite the lobe peak so the path wraps cleanly around it
                cone_offset_y = 68.0 if idx % 2 == 0 else -68.0
                self.course_markers.append(
                    CourseMarker(
                        x_mm=round(bx, 1),
                        y_mm=round(by + cone_offset_y, 1),
                        label=f"CONE {idx + 1}",
                        kind="slalom_cone",
                    )
                )
        elif name == "circle_left":
            self.course_markers.append(CourseMarker(x_mm=0.0, y_mm=-260.0, label="APEX L", kind="pylon"))
        elif name == "circle_right":
            self.course_markers.append(CourseMarker(x_mm=0.0, y_mm=260.0, label="APEX R", kind="pylon"))
        elif name == "figure_eight":
            self.course_markers.append(CourseMarker(x_mm=0.0, y_mm=-240.0, label="LOOP L", kind="pylon"))
            self.course_markers.append(CourseMarker(x_mm=240.0, y_mm=240.0, label="LOOP R", kind="pylon"))
        elif name == "u_turn_3pt":
            self.course_markers.append(CourseMarker(x_mm=260.0, y_mm=0.0, label="U-TURN GATE", kind="slalom_cone"))
        elif name == "spin_wiggle":
            self.course_markers.append(CourseMarker(x_mm=160.0, y_mm=-95.0, label="STAGE L", kind="slalom_cone"))
            self.course_markers.append(CourseMarker(x_mm=160.0, y_mm=95.0, label="STAGE R", kind="slalom_cone"))
        elif name == "patrol":
            self.course_markers.append(CourseMarker(x_mm=340.0, y_mm=-90.0, label="WP 1", kind="slalom_cone"))
            self.course_markers.append(CourseMarker(x_mm=620.0, y_mm=90.0, label="WP 2", kind="slalom_cone"))

    def step_kinematics(self, dt_sec: float, cmd: CompiledActuatorCommand) -> None:
        """Advance `(x_mm, y_mm, heading_rad)` using the bicycle kinematic model."""
        if cmd.emergency_brake or cmd.watchdog_tripped:
            v_mm_s = 0.0
        else:
            v_mm_s = float(cmd.applied_throttle) * self.MAX_SPEED_MM_S

        self.last_steer_deg = float(cmd.applied_steering_deg)
        steer_rad = math.radians(self.last_steer_deg)
        self.car_x_mm += v_mm_s * math.cos(self.car_heading_rad) * dt_sec
        self.car_y_mm += v_mm_s * math.sin(self.car_heading_rad) * dt_sec
        self.car_heading_rad += (v_mm_s / self.WHEELBASE_MM) * math.tan(steer_rad) * dt_sec
        self.trajectory_xy_mm.append((round(self.car_x_mm, 2), round(self.car_y_mm, 2)))
        if len(self.trajectory_xy_mm) > 360:
            self.trajectory_xy_mm = self.trajectory_xy_mm[-360:]

        for obs in self.obstacles:
            center_dist = math.hypot(obs.x_mm - self.car_x_mm, obs.y_mm - self.car_y_mm) - obs.radius_mm
            if center_dist < self.min_obstacle_clearance_mm:
                self.min_obstacle_clearance_mm = max(0.0, center_dist)

    def compute_tof_distance_mm(self) -> int:
        """Ray-cast the front `VL53L1X` laser cone (`±14°` half-angle) from the front valance."""
        sensor_x = self.car_x_mm + self.FRONT_VALANCE_OFFSET_MM * math.cos(self.car_heading_rad)
        sensor_y = self.car_y_mm + self.FRONT_VALANCE_OFFSET_MM * math.sin(self.car_heading_rad)
        best_mm = 1800.0

        targets: list[tuple[float, float, float]] = [
            (obs.x_mm, obs.y_mm, obs.radius_mm) for obs in self.obstacles
        ]
        if self.person_xy_mm is not None:
            targets.append((self.person_xy_mm[0], self.person_xy_mm[1], self.person_radius_mm))

        for tx, ty, radius in targets:
            dx = tx - sensor_x
            dy = ty - sensor_y
            cos_h = math.cos(self.car_heading_rad)
            sin_h = math.sin(self.car_heading_rad)
            fwd_mm = dx * cos_h + dy * sin_h
            lat_mm = -dx * sin_h + dy * cos_h
            if fwd_mm <= 0.0:
                continue
            cone_half_width = radius + fwd_mm * math.tan(math.radians(14.0))
            if abs(lat_mm) <= cone_half_width:
                surf_dist = max(15.0, math.hypot(fwd_mm, lat_mm) - radius)
                if surf_dist < best_mm:
                    best_mm = surf_dist

        return int(round(max(15.0, min(4000.0, best_mm))))

    def _draw_striped_cone(
        self,
        draw: ImageDraw.ImageDraw,
        cx: int,
        base_y: int,
        half_w: int,
        cone_h: int,
        label: str = "",
    ) -> None:
        """Draw a 3D-projected orange traffic/slalom cone with white reflective stripes."""
        top_w = max(4, half_w // 4)
        top_y = base_y - cone_h
        # Base plate
        draw.polygon(
            [
                (cx - int(half_w * 1.25), base_y + 4),
                (cx + int(half_w * 1.25), base_y + 4),
                (cx + int(half_w * 1.05), base_y - 3),
                (cx - int(half_w * 1.05), base_y - 3),
            ],
            fill=(30, 34, 42),
            outline=(255, 120, 40),
        )
        # Main orange cone trapezoid
        draw.polygon(
            [
                (cx - half_w, base_y),
                (cx + half_w, base_y),
                (cx + top_w, top_y),
                (cx - top_w, top_y),
            ],
            fill=(255, 95, 20),
            outline=(255, 220, 190),
        )
        # Two white reflective horizontal bands
        for band_t0, band_t1 in ((0.28, 0.44), (0.62, 0.76)):
            y0 = int(base_y - cone_h * band_t0)
            y1 = int(base_y - cone_h * band_t1)
            w0 = int(half_w - (half_w - top_w) * band_t0)
            w1 = int(half_w - (half_w - top_w) * band_t1)
            draw.polygon(
                [(cx - w0, y0), (cx + w0, y0), (cx + w1, y1), (cx - w1, y1)],
                fill=(248, 250, 255),
            )
        if label:
            font = ImageFont.load_default()
            draw.rectangle((cx - 28, top_y - 18, cx + 28, top_y - 3), fill=(14, 20, 32), outline=(255, 160, 60))
            draw.text((cx - 22, top_y - 16), label[:8], fill=(255, 225, 110), font=font)

    def _draw_showcase_object(self, draw: ImageDraw.ImageDraw, w: int, h: int, kind: str) -> None:
        """Render a high-contrast visual object in front of the Mustang's hood for multimodal Gemini ER Q&A."""
        cx = w // 2
        font = ImageFont.load_default()
        if kind == "stop_sign":
            # Metal post
            draw.rectangle((cx - 7, 215, cx + 7, 360), fill=(170, 180, 195), outline=(90, 100, 115), width=2)
            # Outer white octagon & inner bright red octagon
            r_out = 78
            r_in = 70
            cy = 155
            oct_out = [
                (
                    int(cx + r_out * math.cos(math.radians(22.5 + 45 * i))),
                    int(cy + r_out * math.sin(math.radians(22.5 + 45 * i))),
                )
                for i in range(8)
            ]
            oct_in = [
                (
                    int(cx + r_in * math.cos(math.radians(22.5 + 45 * i))),
                    int(cy + r_in * math.sin(math.radians(22.5 + 45 * i))),
                )
                for i in range(8)
            ]
            draw.polygon(oct_out, fill=(250, 250, 255), outline=(40, 40, 50))
            draw.polygon(oct_in, fill=(225, 22, 28))
            # Draw bold vector "STOP" letters across the octagon center
            # S
            draw.line(
                [(cx - 26, cy - 20), (cx - 48, cy - 20), (cx - 48, cy), (cx - 26, cy), (cx - 26, cy + 20), (cx - 48, cy + 20)],
                fill=(255, 255, 255),
                width=6,
            )
            # T
            draw.line([(cx - 18, cy - 20), (cx + 4, cy - 20)], fill=(255, 255, 255), width=6)
            draw.line([(cx - 7, cy - 20), (cx - 7, cy + 20)], fill=(255, 255, 255), width=6)
            # O
            draw.ellipse((cx + 10, cy - 20, cx + 32, cy + 20), outline=(255, 255, 255), width=6)
            # P
            draw.line(
                [(cx + 40, cy + 20), (cx + 40, cy - 20), (cx + 56, cy - 20), (cx + 56, cy), (cx + 40, cy)],
                fill=(255, 255, 255),
                width=6,
            )

        elif kind == "traffic_cone":
            self._draw_striped_cone(draw, cx=cx, base_y=345, half_w=68, cone_h=190, label="TRAFFIC CONE")

        elif kind == "soccer_ball":
            r = 68
            cy = 265
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(245, 248, 252), outline=(20, 24, 30), width=4)
            # Center black pentagon
            pent = [
                (int(cx + 26 * math.cos(math.radians(-90 + 72 * i))), int(cy + 26 * math.sin(math.radians(-90 + 72 * i))))
                for i in range(5)
            ]
            draw.polygon(pent, fill=(20, 24, 30))
            for i in range(5):
                ang = math.radians(-90 + 72 * i)
                px = int(cx + 56 * math.cos(ang))
                py = int(cy + 56 * math.sin(ang))
                draw.line([pent[i], (px, py)], fill=(20, 24, 30), width=4)
                draw.ellipse((px - 12, py - 12, px + 12, py + 12), fill=(20, 24, 30))

        elif kind == "coffee_mug":
            # Cup handle
            draw.arc((cx + 35, 215, cx + 88, 295), start=-70, end=70, fill=(245, 245, 250), width=10)
            # Mug body
            draw.rounded_rectangle((cx - 55, 195, cx + 55, 330), radius=14, fill=(245, 245, 250), outline=(80, 90, 110), width=3)
            # Dark coffee rim
            draw.ellipse((cx - 52, 185, cx + 52, 212), fill=(75, 42, 24), outline=(230, 230, 240), width=3)
            # Rising steam waves
            for sx in (cx - 24, cx, cx + 24):
                draw.line([(sx, 172), (sx - 8, 150), (sx + 8, 128), (sx, 108)], fill=(210, 225, 245), width=3)
            draw.text((cx - 28, 255), "COFFEE", fill=(75, 42, 24), font=font)

        elif kind == "checkered_flag":
            # Flagpole
            draw.rectangle((cx - 75, 110, cx - 65, 350), fill=(210, 220, 235), outline=(90, 100, 115), width=2)
            # 6x4 black and white checkered pattern
            fx0, fy0, sq = cx - 65, 118, 24
            for row in range(4):
                for col in range(6):
                    color = (20, 22, 26) if (row + col) % 2 == 0 else (248, 250, 255)
                    draw.rectangle(
                        (fx0 + col * sq, fy0 + row * sq, fx0 + (col + 1) * sq, fy0 + (row + 1) * sq),
                        fill=color,
                    )
            draw.rectangle((fx0, fy0, fx0 + 6 * sq, fy0 + 4 * sq), outline=(255, 215, 60), width=2)

    def render_fisheye_rgb(self) -> bytes:
        """Render a `640×480` RGB frame projecting road lines, slalom cones, obstacles, walking person, and showcase object."""
        cfg = self.camera_config
        w, h = cfg.width, cfg.height
        img = Image.new("RGB", (w, h), (22, 32, 48))
        draw = ImageDraw.Draw(img)
        horizon_y = int(h * 0.45)

        # Sky gradient band & asphalt tarmac
        draw.rectangle((0, 0, w, horizon_y), fill=(26, 38, 58))
        draw.rectangle((0, horizon_y, w, h), fill=(42, 48, 58))

        cos_h = math.cos(self.car_heading_rad)
        sin_h = math.sin(self.car_heading_rad)

        # Perspective road lane edges & dashed yellow centerline shifting with heading/lateral offset
        vanish_x = int(cfg.cx - cfg.fx * math.atan2(sin_h, max(0.25, cos_h)) * 0.55)
        vanish_x = max(120, min(w - 120, vanish_x))
        draw.polygon(
            [(vanish_x - 55, horizon_y), (vanish_x + 55, horizon_y), (w - 10, h), (10, h)],
            fill=(50, 56, 66),
        )
        draw.line((vanish_x - 55, horizon_y, 18, h), fill=(230, 238, 250), width=4)
        draw.line((vanish_x + 55, horizon_y, w - 18, h), fill=(230, 238, 250), width=4)
        for seg in range(5):
            t0 = (seg + 0.1) / 5.0
            t1 = (seg + 0.65) / 5.0
            y0 = int(horizon_y + (h - horizon_y) * (t0**1.35))
            y1 = int(horizon_y + (h - horizon_y) * (t1**1.35))
            x0 = int(vanish_x + (w // 2 - vanish_x) * t0)
            x1 = int(vanish_x + (w // 2 - vanish_x) * t1)
            draw.line((x0, y0, x1, y1), fill=(255, 205, 55), width=3)

        # Project course markers (Slalom Cones CONE 1..4 / Pylons) back-to-front by distance
        visible_markers: list[tuple[float, float, CourseMarker]] = []
        for mk in self.course_markers:
            dx = mk.x_mm - self.car_x_mm
            dy = mk.y_mm - self.car_y_mm
            fwd = dx * cos_h + dy * sin_h
            lat = -dx * sin_h + dy * cos_h
            if 45.0 <= fwd <= 1500.0:
                visible_markers.append((fwd, lat, mk))
        visible_markers.sort(key=lambda item: item[0], reverse=True)

        for fwd, lat, mk in visible_markers:
            theta_rad = math.atan2(lat, fwd)
            if abs(math.degrees(theta_rad)) > 78.0:
                continue
            u_px = int(round(cfg.cx + cfg.fx * theta_rad))
            scale_f = min(1.8, max(0.28, 320.0 / max(90.0, fwd)))
            base_y = int(min(h * 0.76, horizon_y + 28 + 135.0 * scale_f))
            half_w = int(max(12.0, min(52.0, 28.0 * scale_f)))
            cone_h = int(max(28.0, min(125.0, 74.0 * scale_f)))
            self._draw_striped_cone(draw, cx=u_px, base_y=base_y, half_w=half_w, cone_h=cone_h, label=mk.label)

        # Project physical obstacles into lower driving ROI (y = 220..345)
        for obs in self.obstacles:
            dx = obs.x_mm - self.car_x_mm
            dy = obs.y_mm - self.car_y_mm
            fwd = dx * cos_h + dy * sin_h
            lat = -dx * sin_h + dy * cos_h
            if fwd <= 40.0 or fwd > 1600.0:
                continue
            theta_rad = math.atan2(lat, fwd)
            if abs(math.degrees(theta_rad)) > 78.0:
                continue
            u_px = int(round(cfg.cx + cfg.fx * theta_rad))
            half_w = int(max(24.0, min(110.0, (obs.radius_mm / max(120.0, fwd)) * cfg.fx * 1.6)))
            draw.rectangle(
                (max(0, u_px - half_w), int(h * 0.48), min(w - 1, u_px + half_w), int(h * 0.72)),
                fill=obs.color,
                outline=(255, 225, 210),
                width=2,
            )

        # Project walking person as a high-visibility teal person figure (RGB = (40, 215, 170))
        if self.person_xy_mm is not None and self.showcase_object is None:
            dx = self.person_xy_mm[0] - self.car_x_mm
            dy = self.person_xy_mm[1] - self.car_y_mm
            fwd = dx * cos_h + dy * sin_h
            lat = -dx * sin_h + dy * cos_h
            if fwd > 50.0:
                theta_rad = math.atan2(lat, fwd)
                if abs(math.degrees(theta_rad)) <= 75.0:
                    u_px = int(round(cfg.cx + cfg.fx * theta_rad))
                    box_w = int(max(36.0, min(140.0, (120.0 / max(150.0, fwd)) * cfg.fx)))
                    x0 = max(20, u_px - box_w // 2)
                    x1 = min(w - 20, u_px + box_w // 2)
                    y0, y1 = int(h * 0.22), int(h * 0.68)
                    draw.rounded_rectangle(
                        (x0, y0, x1, y1),
                        radius=8,
                        fill=(40, 215, 170),
                        outline=(220, 255, 245),
                        width=2,
                    )

        # If a showcase visual object is active, draw it prominently in front of the hood
        if self.showcase_object and self.showcase_object != "person":
            self._draw_showcase_object(draw, w=w, h=h, kind=self.showcase_object)

        # 1967 Mustang Fastback Burgundy Hood with twin white LeMans stripes
        hood_poly = [
            (int(w * 0.16), h),
            (int(w * 0.28), int(h * 0.78)),
            (int(w * 0.50), int(h * 0.74)),
            (int(w * 0.72), int(h * 0.78)),
            (int(w * 0.84), h),
        ]
        draw.polygon(hood_poly, fill=(107, 15, 26), outline=(185, 40, 55))
        draw.polygon(
            [(int(w * 0.44), h), (int(w * 0.46), int(h * 0.75)), (int(w * 0.485), int(h * 0.75)), (int(w * 0.475), h)],
            fill=(235, 240, 248),
        )
        draw.polygon(
            [(int(w * 0.525), h), (int(w * 0.515), int(h * 0.75)), (int(w * 0.54), int(h * 0.75)), (int(w * 0.56), h)],
            fill=(235, 240, 248),
        )
        return img.tobytes()

    def render_clean_camera_jpeg(self, quality: int = 88) -> bytes:
        """Encode the clean `640×480` `OV5647` camera view (without HUD text overlay) for Gemini ER visual Q&A."""
        cfg = self.camera_config
        img = Image.frombytes("RGB", (cfg.width, cfg.height), self.render_fisheye_rgb())
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def render_topdown_map_image(
        self,
        *,
        width: int = 560,
        height: int = 320,
        active_maneuver: str = "",
        phase_caption: str = "",
        tof_mm: int = 1800,
        steer_deg: float = 0.0,
        throttle: float = 0.0,
    ) -> Image.Image:
        """Render a `560×320` Top-Down 2D Track & Slalom Course Radar showing planned curve, cones, car & laser."""
        img = Image.new("RGB", (width, height), (12, 18, 28))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        # Header banner inside map
        m_label = (active_maneuver or self.active_maneuver_name or "FREE DRIVE").upper()
        header = f"2D TRACK RADAR | COURSE: {m_label} | {phase_caption or 'READY'} | STEER: {steer_deg:+.1f} DEG"
        draw.rectangle((0, 0, width, 24), fill=(18, 28, 44))
        draw.text((8, 6), header[:76], fill=(0, 225, 255), font=font)

        pad_x, pad_y0, pad_y1 = 16, 32, height - 24
        map_w = width - 2 * pad_x
        map_h = pad_y1 - pad_y0
        draw.rectangle((pad_x, pad_y0, pad_x + map_w, pad_y1), fill=(16, 23, 34), outline=(38, 58, 86))

        # Compute bounding box across planned path, trajectory, course markers, and current car pose
        all_pts: list[tuple[float, float]] = (
            [(0.0, 0.0), (self.car_x_mm, self.car_y_mm), (850.0, 0.0)]
            + self.planned_path_xy_mm
            + self.trajectory_xy_mm[-120:]
            + [(m.x_mm, m.y_mm) for m in self.course_markers]
            + [(o.x_mm, o.y_mm) for o in self.obstacles]
        )
        if self.person_xy_mm is not None:
            all_pts.append(self.person_xy_mm)

        min_x = min(p[0] for p in all_pts) - 180.0
        max_x = max(p[0] for p in all_pts) + 220.0
        min_y = min(min(p[1] for p in all_pts) - 180.0, -320.0)
        max_y = max(max(p[1] for p in all_pts) + 180.0, 320.0)
        span_x = max(600.0, max_x - min_x)
        span_y = max(450.0, max_y - min_y)

        def world_to_px(wx: float, wy: float) -> tuple[int, int]:
            u = int(pad_x + ((wx - min_x) / span_x) * map_w)
            # +Y is right of initial heading (downward on screen when +X is rightward)
            v = int(pad_y0 + ((wy - min_y) / span_y) * map_h)
            return max(pad_x + 3, min(pad_x + map_w - 3, u)), max(pad_y0 + 3, min(pad_y1 - 3, v))

        # Grid lines every 200 mm
        start_gx = int(min_x // 200) * 200
        for gx in range(start_gx, int(max_x) + 200, 200):
            ux, _ = world_to_px(float(gx), 0.0)
            draw.line((ux, pad_y0, ux, pad_y1), fill=(24, 35, 50))
        _, uy0 = world_to_px(0.0, 0.0)
        draw.line((pad_x, uy0, pad_x + map_w, uy0), fill=(34, 50, 72), width=1)

        # Planned target path (dashed gold/amber curve)
        if len(self.planned_path_xy_mm) >= 2:
            plan_px = [world_to_px(px, py) for px, py in self.planned_path_xy_mm]
            for i in range(0, len(plan_px) - 1, 2):
                draw.line([plan_px[i], plan_px[i + 1]], fill=(255, 195, 55), width=2)

        # Actual driven trajectory trail (bright neon cyan)
        if len(self.trajectory_xy_mm) >= 2:
            traj_px = [world_to_px(px, py) for px, py in self.trajectory_xy_mm]
            draw.line(traj_px, fill=(0, 225, 255), width=3)

        # VL53L1X +/-14 deg front laser cone
        cx_px, cy_px = world_to_px(self.car_x_mm, self.car_y_mm)
        ray_len_mm = min(480.0, float(tof_mm))
        l_ang = self.car_heading_rad - math.radians(14.0)
        r_ang = self.car_heading_rad + math.radians(14.0)
        lx_px, ly_px = world_to_px(
            self.car_x_mm + ray_len_mm * math.cos(l_ang),
            self.car_y_mm + ray_len_mm * math.sin(l_ang),
        )
        rx_px, ry_px = world_to_px(
            self.car_x_mm + ray_len_mm * math.cos(r_ang),
            self.car_y_mm + ray_len_mm * math.sin(r_ang),
        )
        cone_outline = (255, 75, 65) if tof_mm < 180 else (45, 145, 110)
        draw.polygon([(cx_px, cy_px), (lx_px, ly_px), (rx_px, ry_px)], outline=cone_outline)

        # Course markers (Slalom Cones CONE 1..4 / Pylons)
        for mk in self.course_markers:
            mx, my = world_to_px(mk.x_mm, mk.y_mm)
            draw.ellipse((mx - 9, my - 9, mx + 9, my + 9), fill=(255, 100, 20), outline=(255, 250, 240), width=2)
            draw.ellipse((mx - 4, my - 4, mx + 4, my + 4), fill=(255, 255, 255))
            draw.text((mx - 18, my - 21), mk.label, fill=(255, 215, 90), font=font)

        # Physical Obstacles
        for obs in self.obstacles:
            ox, oy = world_to_px(obs.x_mm, obs.y_mm)
            draw.ellipse((ox - 11, oy - 11, ox + 11, oy + 11), fill=(235, 65, 45), outline=(255, 210, 195), width=2)
            draw.text((ox - 12, oy - 23), "OBS", fill=(255, 120, 105), font=font)

        # Walking person marker
        if self.person_xy_mm is not None:
            px, py = world_to_px(self.person_xy_mm[0], self.person_xy_mm[1])
            draw.ellipse((px - 9, py - 9, px + 9, py + 9), fill=(40, 215, 170), outline=(225, 255, 245), width=2)
            draw.text((px - 18, py - 22), "PERSON", fill=(52, 245, 165), font=font)

        # Oriented 1967 Mustang Fastback silhouette (length 22px, width 12px) + steered front wheels
        cos_c = math.cos(self.car_heading_rad)
        sin_c = math.sin(self.car_heading_rad)

        def car_corner(lx: float, ly: float) -> tuple[int, int]:
            rx = cx_px + lx * cos_c - ly * sin_c
            ry = cy_px + lx * sin_c + ly * cos_c
            return int(round(rx)), int(round(ry))

        body_poly = [car_corner(14, -7), car_corner(14, 7), car_corner(-12, 7), car_corner(-12, -7)]
        draw.polygon(body_poly, fill=(165, 24, 42), outline=(255, 225, 230))
        # Center racing stripe pointing forward
        draw.line([car_corner(-10, 0), car_corner(14, 0)], fill=(255, 255, 255), width=2)
        # Steered front wheels
        wheel_ang = self.car_heading_rad + math.radians(steer_deg * 2.0)
        w_dx = int(round(5.0 * math.cos(wheel_ang)))
        w_dy = int(round(5.0 * math.sin(wheel_ang)))
        for wy_off in (-8.0, 8.0):
            wx, wy = car_corner(9.0, wy_off)
            draw.line((wx - w_dx, wy - w_dy, wx + w_dx, wy + w_dy), fill=(52, 245, 165), width=3)

        footer = (
            f"Pose: X={self.car_x_mm:+6.1f}mm Y={self.car_y_mm:+6.1f}mm Hdg={math.degrees(self.car_heading_rad):+5.1f}deg | "
            f"Gold=Planned Path  Cyan=Driven Trail  Orange=Slalom Cones"
        )
        draw.text((8, height - 18), footer[:88], fill=(175, 205, 235), font=font)
        return img

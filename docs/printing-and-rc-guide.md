# 3D Printing, Assembly, CAD (Shapr3D) & RC Electronics Guide

> **Quick Links**: [Back to Main README](../README.md) | [Engineering Design Thinking & Verification](design-thinking-and-verification.md) | [Reference Photo & Camera Index](reference-media.md) | [Changelog](../CHANGELOG.md)

---

## 1. Bambu Studio Print Profile & 5-Colour Filament Palette

[`mustang/make_project.sh`](../mustang/make_project.sh) generates the multi-plate Bambu Studio project (`output/mustang_67_fastback_1-24.3mf`) with pre-configured object orientations, Arachne wall generation, and support overrides:

* **Target Printer & Nozzle**: Bambu Lab X2D (`256 × 256 × 256 mm` bed), `0.4 mm` nozzle.
* **Layer Profile**: `0.12mm High Quality`, Bambu PLA Basic, `wall_generator: arachne` on all objects so fine chrome trim, louvers, and gear teeth resolve cleanly.
* **Tree Supports (`tree(auto)`, build plate only)**: Enabled automatically on `body.stl`, `hood.stl`, `trunk_lid.stl`, `engine_block.stl`, and `bumper_rear.stl` via [`mustang/merge_3mf.py`](../mustang/merge_3mf.py). All other 42 STLs print support-free.

### Complete 47-STL / 66-Piece Colour & Plate Breakdown

| Plate Group | PLA Colour | Hex | STL Files Included (`output/stl/`) | Pieces |
| :--- | :--- | :---: | :--- | :---: |
| **`1_body`** | **Burgundy** (+ **Black** Inlays) | `#6B0F1A` / `#1A1A1A` | `body.stl` + multi-colour inlays `windshield.stl` & `rear_glass.stl` | `3` |
| **`1_hood`** | **Burgundy** | `#6B0F1A` | `hood.stl`, `trunk_lid.stl` | `2` |
| **`1_doors`** | **Burgundy** | `#6B0F1A` | `door_l.stl`, `door_r.stl` | `2` |
| **`2_black`** | **Black** | `#1A1A1A` | `chassis.stl`, `tire_x4.stl`, `grille.stl`, `diff_cover.stl`, `axle.stl`, `knuckle_r.stl`, `knuckle_l.stl`, `steering_link.stl`, `interior_tub.stl`, `steering_wheel.stl`, `door_card_r.stl`, `door_card_l.stl`, `bay_tub.stl`, `valve_cover_r.stl`, `valve_cover_l.stl`, `air_cleaner.stl`, `brace.stl`, `hood_prop.stl`, `boot_tub.stl` | `22` |
| **`3_silver`** | **Silver / Chrome** | `#C8C8CC` | `rim_x4.stl`, `grille_surround.stl`, `corral_emblem.stl`, `fog_lamp_x2.stl`, `headlight_x2.stl`, `park_light_x2.stl`, `taillight_bezel_r_x3.stl`, `taillight_bezel_l_x3.stl`, `gas_cap.stl`, `exhaust_x2.stl`, `backup_light_x2.stl`, `mirror.stl`, `vent_window_r.stl`, `vent_window_l.stl`, `driveshaft.stl`, `axle_gear.stl` | `29` |
| **`3_bumper`** | **Silver / Chrome** | `#C8C8CC` | `bumper_front.stl`, `bumper_rear.stl` | `2` |
| **`4_red`** | **Red** | `#B01010` | `taillight_lens_r_x3.stl`, `taillight_lens_l_x3.stl` | `6` |
| **`5_blue`** | **Ford Engine Blue** | `#2B59C3` | `engine_block.stl` (hollowed underside N25 shroud with 6-point mounts) | `1` |
| **Total** | **5 PLA Colours** | — | **47 STL Files (`45` parts + `2` glass inlays)** | **66** |

---

## 2. Step-by-Step Physical & RC Assembly

![Full RC System Cutaway](images/rc_full_system_cutaway.jpg)

1. **Step 1 — Front Kingpin Steering & Rear Bevel Live Axle (`Chassis`)**:
   - Press the 4 tires (`tire_x4.stl`) over the 4 chrome 5-spoke rims (`rim_x4.stl`) from the inboard side so each rim's flared outer lip seats flush in the tire bead pocket.
   - Drop `Knuckle_L` and `Knuckle_R` onto the vertical front kingpin posts (`Chassis_Kingpin_L/R`) and snap `SteeringLink` onto both knuckle steering pins across `Chassis_SteeringShelf`.
   - Hold `AxleGear` (`12`-tooth crown bevel gear) inside the rear differential cavity (`Cut_ChassisAxleGear`), slide the octagonal `Axle_R` shaft through the rear chassis bosses and through `AxleGear`'s octagonal bore, snap `DiffCover` underneath, and press the 4 wheel assemblies onto the front knuckle stubs and rear axle ends.
2. **Step 2 — Front `BayTub`, Rear `BootTub` & RC Electronics Installation**:
   - Seat `BayTub` (front engine liner) and `BootTub` (rear trunk liner) onto the chassis.
   - **Front Steering Servo**: Seat a `1.7g` micro servo (`13.5 × 6.2 × 16.0 mm`) into `BayTub_ServoBed` behind the radiator so its horn pin drops through `BayTub_ServoHornSlot` directly into the center slot (`SteeringLink_ServoSlot`) of `SteeringLink`.
   - **N25 Drive Motor & Driveshaft**: Press the front D-bore coupler of `Driveshaft` (`driveshaft.stl`) onto the `Ø 3.0 mm` D-shaft of your `N25` gearmotor (`10 × 12 × 24 mm`), slide the driveshaft rearward through the firewall/floor tunnel so its `10`-tooth rear bevel pinion meshes with `AxleGear`, and snap the `N25` motor body into `BayTub_N25Bed`.
   - **Floor Wire Conduit & Trunk Bay**: Thread the 3-wire servo lead and 2-wire motor lead through the enclosed driver-side floor wire conduit (`Y = -7.70..-3.70 mm`, separated from the spinning driveshaft by a `1.20 mm` wall) into `BootTub`. Place the Receiver + 5A Brushed ESC into the left bay of `BootTub` and the 1S/2S LiPo battery into the right bay between `BootTub_BatRail0/1`.
3. **Step 3 — 289 V8 Engine Shroud & Cabin Interior**:
   - Glue `ValveCover_L`, `ValveCover_R`, and `AirCleaner` onto the blue `EngineBlock`. Lower `EngineBlock` over the `N25` motor; its 6 structural mounts and bottom cradle rails lock between `BayTub_EngineGuideL/R` with zero motor interference.
   - Plug `SteeringWheel` into the dashboard and slide `InteriorTub` over the dual center floor tunnels.
4. **Step 4 — Body Shell, Interlocking Doors, Hood & Trunk Lid**:
   - Install the grille, grille surround, corral emblem, headlights, fog lights, park lights, taillights, backup lights, gas cap, and front/rear bumpers onto `Body`.
   - **Door Mechanical Interlocks**: Seat the bottom tenon of `DoorVent_L/R` into `Door_VentSlot` and press the 6 raised pads (`DoorCard_Pad0..5`) on the back of `DoorCard_L/R` into the 6 mortise bays (`Door_CardBay0..5`) on the inner face of `Door_L/R`. This locks both the door card and the chrome vent window into the door.
   - Hinge `Door_L` and `Door_R` on short lengths of `1.75 mm` filament, seat the `Body` onto the chassis bosses, drop the `Hood` and `TrunkLid` hinge pegs into their body slots, and clip `Brace` across the shock towers.

---

## 3. RC Remote Controller Options & Electrical Wiring Diagrams

### Option A: Proportional Hobby RC (`2.4GHz Receiver + 5A Micro Brushed ESC + 1.7g Servo`)
Best for smooth variable-speed throttle, crawling, and proportional left/right front steering.

```mermaid
flowchart LR
    Tx["2.4GHz Transmitter<br/>(Wheel + Trigger)"] -. "2.4GHz Radio" .-> Rx["2.4GHz Micro Receiver<br/>(Left BootTub Bay)"]
    LiPo["1S 3.7V or 2S 7.4V LiPo<br/>(Right BootTub Bay)"] --> Sw["Power Switch"]
    Sw --> ESC["5A Bi-Directional Brushed ESC<br/>(Left BootTub Bay)"]
    ESC -- "5V BEC + CH2 Signal" --> Rx
    Rx -- "CH1 PWM (3-Wire via Floor Conduit)" --> Servo["1.7g Micro Servo<br/>(Front BayTub_ServoBed)"]
    ESC -- "M+ / M- (2-Wire via Floor Conduit)" --> Cap["0.1µF (104) Ceramic Cap"]
    Cap --> N25["N25 Gearmotor<br/>(Front BayTub_N25Bed)"]
```

### Option B: Ultra-Simple 4-Wire Keyfob Controller (`433MHz RF Mini H-Bridge`)
Best for push-button **Forward / Stop / Reverse** operation of the `N25` motor with zero programming and no separate ESC:

```text
  [433MHz Keyfob Remote]
     ( ▲ ) Forward
     ( ■ ) Stop
     ( ▼ ) Reverse
       │
       ⋮  433.92 MHz RF Signal
       ▼
  ┌────┴───────────────────────────────────┐
  │  ANT (17.3 cm helical wire, leave free)│
  │                                        │
  │   433MHz RF Mini H-Bridge Receiver     │
  │   (3.3V - 12V DC, 1.5A - 2A Peak)      │
  │                                        │
  │    VIN+      GND       M+        M-    │
  └─────┼─────────┼─────────┼─────────┼────┘
        │         │         │         │
   [SW1]│ (Switch)│         │         │
        │         │         ├────┬────┤
       (+)       (-)        │   ─┴─   │
  ┌─────┴─────────┴─────┐   │   ─┬─   │ 0.1µF (104) Ceramic Cap
  │  DC Battery Pack    │   │    │    │ (RF brush-noise filter)
  │  • 1S LiPo (3.7V)   │   │  ┌─┴─┐  │
  │  • 3x AAA  (4.5V)   │   └──┤ + ├─┐│
  │  • 4x AAA  (6.0V)   │      │N25│ ││
  └─────────────────────┘      │Mtr│ ││
                               └─┬─┘ ││
                                 └───┴┘
```

| Board Pad | Connected Component | Wire Convention | Electrical Notes |
| :--- | :--- | :--- | :--- |
| **`VIN+` / `V+`** | Battery Positive (`+`) via Switch `SW1` | Red | `3.3V – 12V DC` input (match N25 voltage rating, typically `3.7V–6V` at `100–300 RPM`) |
| **`GND` / `V-`** | Battery Negative (`-`) | Black | Common ground reference |
| **`M+` / `OUT1`** | N25 Motor Terminal 1 | Yellow / White | Swap `M+` and `M-` if Forward/Reverse direction is inverted |
| **`M-` / `OUT2`** | N25 Motor Terminal 2 | Blue / Green | Solder a `0.1µF (104)` ceramic capacitor across motor tabs to suppress brush RF noise |

---

## 4. CAD Editing in Shapr3D (`.step` Solids vs `.stl` Meshes)

Because binary `.stl` files (`output/stl_assembled/_mustang_assembled_all_parts.stl`) contain only unnamed triangle soup, importing an STL into **Shapr3D** labels every body as a generic reference *"Meshed Object"* that cannot be boolean-edited or measured.

Use [`mustang/make_step.py`](../mustang/make_step.py) to generate closed OpenCascade B-Rep **STEP solids** with exact Blender object names and sRGB print colours:

```bash
uv run mustang/make_step.py
```

| CAD Workflow in Shapr3D | File(s) to Import | Object Names & Advantages |
| :--- | :--- | :--- |
| **Fast Subsystem Editing (Recommended)** | Individual files from `output/step/*.step` (e.g. `chassis.step`, `baytub.step`, `boottub.step`, `axle_r.step`, `axlegear.step`, `driveshaft.step`) | Loads in `< 2 seconds`; parts land in their exact assembled car coordinates as editable CAD solids named `Chassis`, `BayTub`, `BootTub`, `Axle_R`, `AxleGear`, `Driveshaft`. |
| **Full 65-Part Car Assembly** | `output/mustang_67_fastback.step` (`~756 MB`) | Single assembly containing all `65` named, coloured B-Rep solids under the root `mustang_67_fastback` tree. |

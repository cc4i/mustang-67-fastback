# Changelog

All notable changes and architectural upgrades to the procedural 1967 Ford Mustang Fastback (`e-Mustang`) project are documented in this file.

> **Documentation & Changelog Rule**: Whenever any geometry module (`mustang/*.py`), scale constant (`body.SCALE`), part list (`export.PARTS` / `INLAYS`), Bambu pipeline (`make_project.sh` / `merge_3mf.py`), or animation/simulation script is updated, `README.md`, `AGENTS.md`, and `CHANGELOG.md` must be audited and updated in lockstep in the same turn.

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

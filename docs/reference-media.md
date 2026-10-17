# Vanguard Stock #2229 Reference Photos, Videos & Blender Camera Index

> **Quick Links**: [Back to Main README](../README.md) | [Engineering Design Thinking & Verification](design-thinking-and-verification.md) | [Printing, CAD & RC Wiring Guide](printing-and-rc-guide.md) | [Changelog](../CHANGELOG.md)

`origin_images/` holds **83 high-resolution (`1920×1440`) dealer photos** (`1967-ford-mustang-fastback.jpeg` and `(1)` through `(83)`), one `564×564` collage, **two walkaround/inspection videos** (`1967-ford-mustang-fastback-video.mp4` and `vanguard_30_sec_about_us.mp4`), and `vanguard_2229_manifest.json` from Vanguard Motor Sales (`Stock #2229`).

The `Cam_P*` cameras in `output/mustang_67_fastback.blend` reproduce the matching dealer photos so any Cycles render (`studio.render("Cam_P1", "tmp/renders/p1.png")`) can be overlaid directly onto the real photograph. `Cam_P1`, `Cam_P2`, `Cam_P3`, and `Cam_P5` are solver-fitted to landmark coordinates on the car; the remaining cameras are hand-matched.

> **Note**: A car facing right in a photo shows its passenger (`+Y`, right) side. The red boxes drawn on `(2)` and `(6)` are earlier review annotations marking areas that were corrected in `v2.0.0–v2.1.0`.

| Photo / Media (`origin_images/`) | View / Angle | Primary Geometry Modelled & Verified Against This Shot | Matched Blender Camera |
| :--- | :--- | :--- | :---: |
| `1967-ford-mustang-fastback.jpeg` | Front 3/4, driver side, elevated | Overall fastback stance, roof line, hood spear, front 3/4 comparison (`front34_driver.jpg`) | — |
| `(1)` | Straight side profile, passenger side | Wheelbase, fastback roof sweep, side window & vent window silhouettes, rocker trim | `Cam_P1` |
| `(2)` | Rear 3/4, passenger side | Rear quarter hip, lower quarter skirt tuck, side scoop, `11`-slot C-pillar louvers | `Cam_P2` |
| `(3)` | Straight rear | Set-back tail panel, 3-bar taillights, rear bumper blade, dual exhaust tips, `TrunkLid` shut lines | `Cam_P3` |
| `(4)`, `(20)` | Straight front (identical files) | V-prow grille mouth, chrome surround, corral & running horse, `7"` headlights, front bumper | `Cam_P4` |
| `(5)` | Rear 3/4, driver side | Driver-side rear quarter, fastback backlight curve, tail panel | `Cam_P5` |
| `(6)` | Front 3/4, driver side, low | Front bumper corner, V-prow fender eyebrows, recessed hood turn-signal scallops | `Cam_P6` |
| `(7)` | Dashboard & cabin front | Twin-cowl dashboard, 3-spoke dish steering wheel, center console | — |
| `(8)` | Passenger door open | Door opening, chrome vent window frame, latch, door card, scuff plate (`door_open.jpg`) | `Cam_P8` |
| `(9)` | Front bucket seats | Sculpted bucket seat side bolsters, center console | — |
| `(10)` | Rear seat | Rear bench bolsters, fastback fold-down partition | — |
| `(11)` | Front, hood open | Hood hinges, open engine bay from the front (`hood_open.jpg`) | — |
| `(12)` | Hood underside | Hood underside structural bracing & prop cup | — |
| `(13)` | Engine bay from above | Oval Cobra air cleaner, plug wires, radiator, battery, shock-tower export brace (`engine_bay.jpg`) | — |
| `(14)` | Engine bay, passenger front corner | Finned Cobra valve covers, alternator, factory bay layout | `Cam_P14` |
| `(15)` | Front 3/4, driver side | Front fascia, fender emblem script | — |
| `(16)` | Door & side scoop close-up, passenger side | Door handle, `1.35 mm` deep side scoop cove, rocker molding | — |
| `(17)`, `(19)` | Rear 3/4, driver side (identical files) | Rear quarter and tail panel | — |
| `(18)` | Front corner close-up, passenger side | Swept-back headlight bucket mouth, bumper end wing, fender badge | — |
| `(21)` | Front 3/4, passenger side | Passenger-side front 3/4 comparison (`front34_passenger.jpg`) | — |
| `(22)`–`(29)` | Exterior walkaround & greenhouse close-ups | Full-chrome side window perimeter (`Cut_WindowOpen`), `DoorBeltTrim_L/R`, extended `drip_rail` | — |
| `(30)`–`(31)` | Wheel & tire close-ups | Crowned 5-spoke American Racing Torq-Thrust rims, deep dish lip, lug nuts | — |
| `(32)`–`(33)` | Front fascia & headlight close-ups | `5.4 mm` deep recessed `7"` sealed-beam headlight buckets & `GrilleSurround_Skin` | — |
| `(34)`–`(44)` | Exterior details, badging & louvers | Hood turn-signal indicator scallops, `11`-slot C-pillar louvers, rear gas cap, chrome trim | — |
| `(45)`–`(58)` | Cabin interior & rear sport deck | 1967 Fastback fold-down rear cargo shelf (`Tub_CargoShelf`), 5 chrome cargo strips, door cards | — |
| `(59)`–`(66)` | Open trunk & rear decklid | Hinged `TrunkLid`, underside X-ribs, weatherstrip channel, rear `BootTub` geometry | — |
| `(67)`–`(83)` | Undercarriage, drivetrain & dual exhaust | Chassis rails, 9-inch Ford rear differential housing (`Chassis_Diff` + `DiffCover`), dual exhaust tips | — |
| `1967-ford-mustang-fastback-video.mp4` | Full 12m21s walkaround, V8 & test-drive video | Proportions in motion, paint/chrome reflections, panel shut-line fit | — |
| `a59e01860f8284d51b12875cc909b3b0.jpg` | Collage: front 3/4 and rear 3/4, driver side | Overall posture check | — |

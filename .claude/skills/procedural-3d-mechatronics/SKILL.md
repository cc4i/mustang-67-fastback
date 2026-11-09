---
name: procedural-3d-mechatronics
description: Standard operating workflow, project template layout, 10 engineering rules (R1..R10), and 5 pre-print verification gates (G1..G5) for turning any creative product idea into a 100% procedural Blender Python 3D model, Shapr3D STEP assembly, Bambu Studio 2-stage .3mf print project, and physical RC/AI mechatronics build.
---

# Universal Idea-to-Physical-Build Workflow (`procedural-3d-mechatronics`)

Use this skill whenever starting a new 3D-printable model, RC vehicle, robot, or AI-embodied device from an initial idea, or when iterating on CAD geometry, slicer plates, and physical print feedback.

---

## 1. Standard Repository Template Layout (`<project-slug>/`)

Scaffold every procedural 3D mechatronics repository with this structure:

```text
<project-slug>/
├── AGENTS.md                        # Master architecture, coordinate conventions (+X, +Y, +Z), R1..R10 rules & G1..G5 gates
├── CLAUDE.md -> AGENTS.md           # Symlink for Claude Code / Gemini / Antigravity
├── README.md                        # Visual showcase, 4-Act animation preview, quick-start commands & 4-step assembly
├── CHANGELOG.md                     # Versioned upgrade history ([vX.Y.Z]) with verified metrics
├── origin_images/                   # Reference photos, turnaround drawings, videos & caliper notes
├── cad/                             # 100% Procedural Blender Python CAD (zero hand-sculpted meshes)
│   ├── paths.py                     # Canonical paths for ROOT, OUTPUT, TMP, ORIGIN_IMAGES
│   ├── body.py                      # Outer shell lofted from station tables + SCALE + surface BVH tree
│   ├── features.py                  # Reusable CAD primitives: ray-cast strips, 45° gables, octagonal splines, bevel gears
│   ├── chassis_and_tubs.py          # Baseplate, sub-frame tubs, 45° mortise-and-tenon locks & wire conduits
│   ├── drivetrain_and_linkages.py   # Motors, multi-fit couplers, shafts, XY-printed gears, double-shear knuckles/hinges
│   ├── avionics_ai.py               # SBC/camera/HUD/speaker/LiPo pockets + _v_* Calipers-First virtual BOM envelopes
│   ├── materials.py                 # Name-prefix material & 5-colour filament mapping
│   ├── build.py                     # Non-destructive MANIFOLD boolean tree builder
│   ├── printcheck.py                # Automated Pre-Print Gates G1..G5 (manifold, overlaps, mirror, BOM fit, overhangs)
│   ├── export.py                    # Print-orientation table PARTS, export.run() (bed-flat) & export.run_assembled()
│   ├── make_project.sh              # Builds BOTH 3-Plate Minimal Mule .3mf & Full Multi-Colour .3mf via Bambu CLI
│   ├── merge_3mf.py                 # Per-object tree supports, outer_only small-part brims & 20-25 mm/s speed overrides
│   ├── make_step.py                 # OpenCascade B-Rep exporter -> named, colour-coded .step solids for Shapr3D
│   └── animate.py                   # 4-Act 3D Fly-In Assembly, 360° Turntable, Kinematic Sweep & Drive Simulation (.mp4)
├── software/                        # Standalone Python runtime (zero bpy dependency; runs on Mac/Linux & SBC)
│   ├── pyproject.toml
│   ├── src/<pkg>/
│   │   ├── protocol/                # @runtime_checkable HAL protocols & frozen dataclass messages
│   │   ├── hal/                     # Paired Sim* (offline) & Hardware* (SBC GPIO/I2C/SPI/I2S/CSI) drivers
│   │   ├── runtime/                 # 100 ms Deadman Watchdog, <20 ms reflex brake & state bus
│   │   ├── features/                # Voice/HUD, action macros, obstacle bypass & person/target tracking
│   │   ├── simulator/               # 2D/3D VirtualArena physics & sensor ray-caster + live browser workbench
│   │   └── cli/doctor.py            # Interactive H1..Hn cable harness bench diagnostic CLI
│   └── tests/                       # Offline pytest suite verifying all HAL contracts, watchdog & VirtualArena
├── docs/
│   ├── build-workflow-and-rules.md          # Portable 7-phase process, R1..R10 rules & G1..G5 gates
│   ├── printing-and-assembly-guide.md       # Plate manifest, +Z/-Z assembly steps, wiring diagrams & Shapr3D guide
│   ├── design-thinking-and-verification.md  # Engineering rationale, cross-section math & G1..G5 verification matrix
│   └── ai-hardware-and-software-guide.md    # Calipers-First BOM shopping list, pin-by-pin H1..Hn tables & 3-tier software
├── output/                          # Git-ignored deliverables: .blend, stl/, stl_assembled/, step/, .3mf (Mule + Full), .mp4
└── tmp/                             # Git-ignored scratch renders, slice logs & JSON verification reports
```

---

## 2. Seven-Phase Execution Pipeline (`Phase 0` to `Phase 6`)

### Phase 0: Idea Intake & Calipers-First BOM Grill (Before Writing Code)
1. **Lock Scale & Printer Profile**: Confirm target scale (`SCALE = 1/N` or overall `L × W × H mm`), build plate (`256 × 256 mm`), nozzle (`0.4 mm`), layer height (`0.12 mm`), and filament palette (`<= 5` colours).
2. **Lock Moving Degrees of Freedom (DoF)**: List every hinged closure, steerable joint, rotating shaft, and gear reduction stage.
3. **Rule R1 (Calipers-First Real-BOM Lock)**: Never size pockets from bare IC or active screen dimensions. Define a `_v_*` 3D bounding-box table (`(name, center_mm, size_mm, rot_deg)`) using **real physical breakout board + solder header + lens barrel + ribbon/wire-bend dimensions** (e.g., `35 × 20 × 8 mm` 2S LiPo, `16 × 11.5 × 4 mm` 5V BEC, `35.6 × 35.6 × 3.2 mm` display carrier PCB, `Ø 14.0 mm` M12 lens barrel + `16.0 mm` MIPI CSI ribbon).

### Phase 1: Part Decomposition & 2-Stage Print Split (`Mule-Before-Shell`)
1. **Declare `export.PARTS` Orientation Upfront**: Assign every part's bed rotation (`IDENTITY`, `UPSIDE_DOWN`, `RX_UP_FROM_NEG_Y`, `RY_UP_FROM_POS_X`) and filament colour before modelling geometry.
2. **Rule R2 (Mandatory 2-Stage Print Split)**:
   - **Stage A - Minimal Functional Mule (`.3mf`, 2-3 zero-support plates, `< 3 hrs` print)**: Chassis, inner tubs/cradles, drivetrain gears/shafts/couplers, steering linkages, wheels, and sensor pods.
   - **Stage B - Full Multi-Colour Shell & Cosmetic Trim (`.3mf`, 8-9 plates)**: Outer body shell, hinged doors/hood/lids, and cosmetic details, printed only after Stage A passes physical bench testing.

### Phase 2: Print-Orientation-First Procedural Blender CAD (`cad/*.py`)
Enforce Rules `R3..R7` on every CAD module:
- **Rule R3 (XY Perimeter Load & Minimum Wall Thicknesses)**:
  - Orient gear teeth, spline bores, 3-lobe crush bores, and clevis eyelets flat in the **`XY` plane** so continuous Arachne perimeters carry hoop and shear loads.
  - Orient long shafts and tie-rods **horizontally flat on `Z = 0`** using octagonal cross-sections.
  - Enforce structural floors (`0.4 mm` nozzle): **`>= 1.50-1.80 mm` (`4` walls)** on rim lips, motor couplers (`Ø 6.20 mm` OD), and gear collars (`Ø 5.80-7.00 mm`); **`>= 1.0-1.2 mm` (`2-3` walls)** on clevis eyelets around `>= Ø 1.50 mm` pins; **`>= 3.40 mm` across flats** on drive axles with **8-lobe octagonal hub bores**; **`>= 3.4 × 2.1 mm`** on tie-rod beams; **solid tooth-root cores** on bevel pinions; and **stress-relieved circular front bores** under crown-gear tooth valleys.
- **Rule R4 (Zero Radial Undercut & Hand-Slide Fits)**:
  - Never put closed radial snap-fit undercuts on rigid PLA/PETG rims or housings (`0` undercut). Use **`0.20-0.22 mm`/side clearance**, a `45°` entry chamfer, and **open-ended axial drive keys** for hand-slide assembly (`0.07-0.08 mm`/side for close-running bearings and spline sockets).
- **Rule R5 (`45°` Self-Supporting Internal Cavities)**:
  - Every horizontal tunnel, wire conduit, and bottom mortise socket on support-free parts must terminate in a **`45°` gable roof or `<= 30°` conical bevel** (`nz > -0.95`) with zero horizontal steps `> 0.20 mm` above `Z = 0`.
- **Rule R6 (Positive Sub-Frame Mortise-and-Tenon Interlocks & Double-Shear Pins)**:
  - Lock every inner tub/sub-frame (`BayTub`, `InteriorTub`, `DoorCard`) onto the base `Chassis` or `Door` in `X`, `Y`, and `Z` using **`45°` gable-roofed mortise-and-tenon bosses** and recessed solid servo/motor floors.
  - Capture kingpins and load-bearing pivots at both bottom and top (**double shear**).
- **Rule R7 (Open-Bottom U-Channels & Partitioned Wire Conduits)**:
  - Use open-bottom `45°` gable U-channels for driveshafts/linkages so sub-assemblies push straight together along `+Z` or `-Z` without threading long shafts through closed holes, isolated by a solid `>= 1.0 mm` partition wall from enclosed wire conduits.

### Phase 3: 5-Gate Automated Pre-Print Verification Loop (`printcheck.py`)
Block export until all 5 headless Blender/Slicer checks pass simultaneously:
- **`G1` (Manifold & Single-Shell Gate)**: `problems == {}` (`non_manifold_edges == 0`, `boundary_edges == 0`, `shells == 1`).
- **`G2` (Static & Mirror Clearance Gate)**: `overlaps_with_body == {}`, `part_overlaps == {}`, `mirror_mismatches == {}`.
- **`G3` (Virtual Real-BOM Fit Gate)**: `verify_virtual_hardware() == {}` (`0.000 mm³` overlap across all `_v_*` real-BOM hardware boxes).
- **`G4` (Kinematic & 3D Straight-Line Insertion Gate)**: `0.000 mm³` collision across all hinge/steering/gear sweeps and straight-line `+Z/-Z` assembly trajectories.
- **`G5` (Overhang & Slicer Gate)**: `floating == []` and `cantilevers == []` on all support-free STLs, plus `0` warnings from `BambuStudio --slice 0`.

### Phase 4: Dual Slicer (`.3mf`), Shapr3D (`.step`) & Simulation (`.mp4`) Export
- **Rule R8 (Small-Part Plate Isolation & Outer Brims)**: Isolate miniature gears, couplers, and trims onto a dedicated low-Z plate (`max_z <= 10.5 mm`) with `brim_type: outer_only` (`3-5 mm`), `20-25 mm/s` wall speeds, and `reduce_crossing_wall: 1`.
- Export both the **Stage A Minimal Mule `.3mf`** and **Stage B Full `.3mf`**, generate named/coloured OpenCascade **`.step` solids** (`make_step.py`) for **Shapr3D**, and render the 4-Act assembly/kinematic simulation `.mp4`.

### Phase 5: Progressive Physical Print, Bench Bring-Up & Guidance
- Run offline `pytest` + `VirtualArena` simulation first, then run `doctor --harness {H1..Hn}` on the bench.
- Print and assemble the **Stage A Minimal Functional Mule** using `docs/printing-and-assembly-guide.md` to verify wheel fit, steering throw, drivetrain torque, sub-frame locks, and battery/PCB fit before printing Stage B.

### Phase 6: Physical-to-Digital Closed Feedback Loop
- **Rule R9 (Audit-Before-Action)**: When the user reports physical print/assembly issues or photos, measure the exact failure cross-section in print mm and present a **numbered Root-Cause & Fix Table** for user approval before editing CAD code.
- **Rule R10 (Gate Ratchet & Lockstep Docs)**: Every physical fix must add a permanent check to `printcheck.py` / `verify_virtual_hardware()`, regenerate STLs / `.3mf` / `.step`, and update `README.md`, `AGENTS.md`, `CHANGELOG.md`, and `docs/*.md` in lockstep.

# AGENTS.md

A printable and RC-ready **1:20** (`body.SCALE = 1/20`) 1967 Ford Mustang Fastback (`e-Mustang`) built procedurally in Blender from the Python modules in `mustang/`. It is modelled on the 83 dealer photos and 2 walkaround videos in `origin_images/` (Vanguard Motor Sales `Stock #2229`); `docs/reference-media.md` has a table of which photo shows what, `docs/printing-and-rc-guide.md` covers the 47-STL print manifest, RC wiring and Shapr3D STEP import, `docs/design-thinking-and-verification.md` documents the engineering trade-offs and verification metrics, and `CHANGELOG.md` tracks the upgrade history from `v1.0.0` (the 1:24 baseline) onward.

The project root holds only sources and top-level docs (`README.md`, `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`), with deep-dive guides in `docs/`. Every generated build artifact goes into one of three folders:
- `output/` holds the deliverables: STLs, STEP files, the Bambu `.3mf`, the MP4 and the scene `.blend`.
- `tmp/` holds scratch: renders, comparison sheets, animation/simulation frames (`tmp/anim_frames`, `tmp/sim_frames`), probe scripts, JSON verification reports (`printcheck_report.json`, `export_report.json`, `rc_control_report.json`, `door_interlock_report.json`, `n25_drivetrain_report.json`, `axle_wheel_strength_report.json`) and backups.
- `docs/images/` holds the tracked showcase media referenced by `README.md` and `docs/*.md`; `mustang/readme_images.sh` rebuilds the photo-vs-model pairs from `tmp/anim_frames`.

`mustang/paths.py` names the first two. Git tracks the sources, the docs (with `docs/images/`) and `origin_images/`; `.gitignore` excludes `output/` and `tmp/`. The saved `.blend` is therefore not versioned, even though it holds cameras no code recreates (see Architecture), so copy it into `tmp/` before changing those cameras.

## Space and naming

- Dimension tables are in real-car millimetres. `body.SCALE` (`1.0 / 20.0`) converts them, so the scene is in print millimetres (`1 BU = 1 mm`, assembled car `226 × 91 × 66 mm`). Modules that define print-space clearances or offsets relative to the original 1:24 baseline multiply them by `K = body.SCALE / (1.0 / 24.0) = 1.2`. Each module's docstring says which unit it uses.
- `+X` points rearward, `+Y` is the passenger (right) side, and the car is left-hand drive. A `_L`/`_R` suffix is the side, except `Axle_R` and `Bumper_R`, where `R` means rear.
- Object names are the interface between modules. `materials.py` assigns render materials by name prefix (first match wins, and `_check_order` asserts that no prefix is shadowed). `export.PARTS` (`45` entries) and `export.INLAYS` (`2` entries) map object names to `47` STL files (`66` total printed pieces) and print colours (`export.print_colour` gives a copy such as `Rim_FL` the colour of its listed sibling, and stops the assembled export if an object matches none). `printcheck.mirror_mismatches` pairs `Name_L*` with `Name_R*`. `make_project.sh` groups parts by STL file name. If you rename or add an object, update all four (`materials.py`, `export.py`, `printcheck.py`, `make_project.sh`).

## Architecture

- `build.main()` deletes and rebuilds the collections `Body`, `Wheels`, `Parts`, `Accessories` and `Cutters`. Geometry functions return `(part, union pieces, cut pieces)`. `build.py` links the pieces into `Cutters` as hidden objects and attaches live `MANIFOLD` boolean modifiers to them. Nothing is applied, and boolean order matters: recesses come before the details raised inside them, and `body_late_unions` come after the body cutters that would otherwise remove them.
- The body is a loft through the station cross-section tables in `body.py` (including the 1967 V-prow nose rake in `body.rake`), with subdivision baked in at level 3, then the quarter corners are extended and tucked (`QUARTER_TUCK = 3760.0, SLOPE = 0.72`). `features.py` makes cutters and strips that follow the skin by ray-casting outlines onto the body's BVH tree (`far = 300.0`). The bumpers hug the shell as it was *before* the quarters tuck under (the `shell` tree).
- A boolean carries the cutter's material onto the faces it creates. That is how recesses read black and `Add_*` / `Cut_WindowOpen` / `DoorBeltTrim_*` trim reads chrome in renders (`materials.CUTTER_MATERIALS`). The print colour comes only from separate parts, plus the black glass inlays exported as extra parts of the body object (`export.INLAYS`). Chrome `Add_*` trim therefore renders chrome but prints in the body colour.
- **Hinged & pivoting assemblies (`export.HINGED = ("Hood", "TrunkLid", "Door_L", "Door_R", "Knuckle_L", "Knuckle_R")`)**:
  - `Hood` (`+42°` on Y around `X = 1495.0, Z = 955.0`), `TrunkLid` (`-40°` on Y around `X = 3985.0, Z = 1094.0`), `Door_L/R` (`+55°` on Z around `X = 1768.0`), and front steering `Knuckle_L/R` (`±15°` on Z around `Chassis_Kingpin_L/R` at `X = 792.0, |Y| = 596.0`) are modelled in their closed / neutral (`0°`) pose.
  - Their origins sit on the hinge/kingpin axis, and their riders are parented to them:
    - `Door_L/R` carry `DoorCard_L/R` (whose 6 raised pads `DoorCard_*_Pad0..5` interlock with `Door_*_CardBay0..5`, with card cutters parented to `DoorCard`), `DoorVent_L/R` (whose lower tenons are captured inside the `Door_*_VentSlot` + `DoorCard_*_VentSlot` sill U-channel, with pane cutters parented to `DoorVent`), `Mirror_L`, and door feature cutters.
    - `Knuckle_L/R` carry `Rim_FL/FR` and `Tire_FL/FR`.
  - `export.run()` and `animate.bake_showcase()` reset all `HINGED` objects to `(0, 0, 0)` before evaluating or exporting.
- **RC drivetrain and electronics bays** (servo steering through `SteeringLink` and `Knuckle_L/R`, the `N25` gearmotor → `Driveshaft` → bevel `AxleGear` on the octagonal `Axle_R`, the press-fit rim hubs and splined tires, the driver-side wire conduit, and the divided `BootTub` ESC/LiPo bay) are built in `engine_bay.py`, `details.py` and `wheels.py`; their dimensions and rationale are in `docs/printing-and-rc-guide.md` and `docs/design-thinking-and-verification.md`.
- The saved `.blend` holds things no code creates: the photo-matched cameras `Cam_P*` in the `Studio` collection (camera N matches `origin_images/1967-ford-mustang-fastback (N).jpeg`), plus assorted inspection cameras. `studio.setup()` recreates only the objects in `studio.OWNED`. `studio.look()` reapplies the world, cove and light settings without touching any camera.
- `animate.setup()` bakes modifier-applied `SC_*` copies into a `Showcase` collection (reusing the single `"Smooth by Angle"` node group) and hides the build collections. `build.main()` reverses that, so run `animate.setup()` again after every rebuild before rendering the animation.

## Running code

Every module imports `bpy`, so it runs only inside Blender. Put `mustang/` on `sys.path` first. Enable Apple Metal GPU (`prefs.compute_device_type = 'METAL'`, `scene.cycles.device = 'GPU'`) for fast Cycles renders.

- **Headless** (renders, long jobs, parallel work on `tmp/` copies of the `.blend`):
  `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python tmp/job.py`, where `job.py` inserts the `mustang` path, runs `build.main()`, the checks and the export, and writes its results to a JSON file in `tmp/`. To work on the saved scene instead, pass `output/mustang_67_fastback.blend` before `--python`. The headless animation render command is in the `animate.py` docstring.
- **Live GUI via the Blender MCP**: `build.py` reloads its own submodules but not itself, `export`, `studio` or `animate`. Pop all of them from `sys.modules` before importing. The MCP link times out on long calls, so schedule long work with `bpy.app.timers.register(job)`, have `job` write a status JSON to `tmp/`, and poll that file from the shell. macOS App Nap throttles GUI timers while the Mac is idle, so run long renders headless.
- **Outside Blender**: `check_plates.py`, `inspect_3mf.py`, `merge_3mf.py` and `bambu_presets.py` run on the system `python3`, which has no numpy. numpy exists only in Blender's bundled python (`/Applications/Blender.app/Contents/Resources/<version>/python/bin/python3.13`). `make_step.py` runs with `uv run`, which fetches the OpenCascade bindings pinned in its header.

## Checks

There is no test suite. These checks stand in for it:

- `printcheck.run()` on the built scene (`65` parts across `Body`, `Wheels`, `Parts`): `problems`, `overlaps_with_body`, `mirror_mismatches` and `part_overlaps` must all be empty (`{}`), and `body.shells` must be `1`. Intended exceptions are declared at the top of `printcheck.py` (`ASYMMETRIC_PAIRS = ("ValveCover",)`, `ONE_SIDED = ("Mirror", "DoorMirrorSlot", "Axle", "Bumper")`, `PRESS_FITS = (("Axle", "Rim"), ("Knuckle", "Rim"))`).
- **Kinematic & RC envelope checks**:
  - Step `Hood` (`0°..42°`), `TrunkLid` (`0°..-40°`), and `Door_L/R` (`0°..55°`) through their opening ranges and verify `0.0 mm³` overlap against `Body`, `InteriorTub`, `BayTub`, and `BootTub`.
  - Step `Knuckle_L/R` (`-15°..+15°`) with coupled `SteeringLink` lateral shift (`Y = R_arm * sin(θ)`) and verify `0.0 mm³` overlap between steered `Tire_FL/FR`, `Rim_FL/FR`, `Knuckle_L/R`, `Body`, `Chassis`, and `BayTub` (`tmp/rc_control_report.json`).
  - Verify `0.0 mm³` static overlap between virtual RC electronics envelopes (`_v_servo`, `_v_n25`, `_v_esc`, `_v_lipo`, 5-wire gauge) and all printed parts.
- The report from `export.run()`: `non_manifold` must be `0` for every one of the `47` STLs, and `floating` must be empty except on the parts printed on supports (`body`, `hood`, `trunk_lid`, `engine_block`, `bumper_rear`; see `merge_3mf.OBJECT_SETTINGS`) or bridged internal roofs (`interior_tub`).
- `uv run mustang/make_step.py` must exit 0: every part a valid closed solid with its mesh's volume (`output/step/report.json` has the details).
- Lint (ruff is not installed): `cd mustang && uvx ruff check --no-cache --select E,F,W --ignore E731 --line-length 140 .`
- Visual check: render the matching `Cam_P*` or cutaway views and compare side by side with `origin_images/`.

## Print pipeline and CAD export

The STL → Bambu 3MF → slice workflow and the STL → STEP export for Shapr3D are in `.claude/skills/print-pipeline/SKILL.md`; keep that file in sync when `export.py`, `make_project.sh`, `merge_3mf.py`, `bambu_presets.py` or `make_step.py` change. The default project, `output/mustang_67_fastback_1-24.3mf`, is the file the user tunes and re-saves in the Bambu Studio GUI: write verification runs to `tmp/`, and regenerate the default only when asked.

## Documentation & Changelog Rule (Mandatory Moving Forward)

Whenever any change or upgrade is made to the model's geometry (`mustang/*.py`), scale (`body.SCALE`), part inventory (`export.PARTS` / `INLAYS`), print pipeline (`make_project.sh` / `merge_3mf.py`), or animation/simulation scripts (`animate.py` / `readme_images.sh`):
1. **Audit & Sync `README.md` and `AGENTS.md` in Lockstep**: Update scale figures, part/STL counts, feature descriptions, assembly steps, and verification checks in both `README.md` and `AGENTS.md` (`CLAUDE.md` symlinks to `AGENTS.md`) within the same turn so documentation never drifts from the code.
2. **Record Upgrade History in `CHANGELOG.md`**: Append a dated version entry (`[vX.Y.Z] - YYYY-MM-DD`) in `CHANGELOG.md` documenting what was added/changed, which modules and STL parts were affected, and the verified geometric/kinematic metrics (`printcheck.run()`, `export.run()`, and overlap checks).
3. **Refresh `docs/images/` When Animation Frames Change**: If `tmp/anim_frames/` is re-rendered or frame indices in `animate.py` change, update and rerun `mustang/readme_images.sh` so the tracked photo-vs-model pairs stay current.

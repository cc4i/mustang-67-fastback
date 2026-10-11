# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A printable 1:24 1967 Ford Mustang Fastback built procedurally in Blender from the Python modules in `mustang/`. It is modelled on the photos in `origin_images/`; `README.md` has a table of which photo shows what.

The project root holds only sources and docs. Every file you generate goes into one of two folders (`mustang/paths.py`):
- `output/` holds the deliverables: `stl/`, `stl_assembled/`, the Bambu project, the MP4, and the scene `mustang_67_fastback.blend`.
- `tmp/` holds scratch: renders, comparison sheets, animation frames, probe scripts, JSON status files and backups.

Git tracks the sources, the docs and `origin_images/`; `.gitignore` excludes `output/` and `tmp/`. The saved `.blend` is therefore not versioned, even though it holds cameras no code recreates (see Architecture), so copy it into `tmp/` before changing those cameras.

## Space and naming

- Dimension tables are in real-car millimetres. `body.SCALE` (1/24) converts them, so the scene is in print millimetres (1 BU = 1 mm). Clearances and offsets are usually given in print mm already. Each module's docstring says which unit it uses.
- +X points rearward, +Y is the passenger (right) side, and the car is left-hand drive. A `_L`/`_R` suffix is the side, except `Axle_R` and `Bumper_R`, where R means rear.
- Object names are the interface between modules. `materials.py` assigns render materials by name prefix (first match wins, and `_check_order` asserts that no prefix is shadowed). `export.PARTS` maps object names to STL files. `printcheck.mirror_mismatches` pairs `Name_L*` with `Name_R*`. `make_project.sh` groups parts by STL file name. If you rename or add an object, update all four.

## Architecture

- `build.main()` deletes and rebuilds the collections Body, Wheels, Parts, Accessories and Cutters. Geometry functions return `(part, union pieces, cut pieces)`. `build.py` links the pieces into Cutters as hidden objects and attaches live MANIFOLD boolean modifiers to them. Nothing is applied, and boolean order matters: recesses come before the details raised inside them, and `body_late_unions` come after the body cutters that would otherwise remove them.
- The body is a loft through the station cross-section tables in `body.py`, with subdivision baked in at level 3, then the quarter corners are extended and tucked. `features.py` makes cutters and strips that follow the skin by ray-casting outlines onto the body's BVH tree. The bumpers hug the shell as it was *before* the quarters tuck under (the `shell` tree).
- A boolean carries the cutter's material onto the faces it creates. That is how recesses read black and `Add_*` trim reads chrome in renders (`materials.CUTTER_MATERIALS`). The print colour comes only from separate parts, plus the black glass inlays exported as extra parts of the body object (`export.INLAYS`). Chrome `Add_*` trim therefore renders chrome but prints in the body colour.
- Hood and doors are modelled closed. Their origins sit on the hinge axis, and their riders (cards, vent windows, mirror, feature cutters) are parented to them, so you open one by setting `rotation_euler`. `export.run` resets them to closed before exporting.
- The saved `.blend` holds things no code creates: the photo-matched cameras `Cam_P*` in the Studio collection (camera N matches `origin_images/1967-ford-mustang-fastback (N).jpeg`), plus assorted inspection cameras. `studio.setup()` recreates only the objects in `studio.OWNED`. `studio.look()` reapplies the world, cove and light settings without touching any camera.
- `animate.setup()` bakes modifier-applied `SC_*` copies into a Showcase collection and hides the build collections. `build.main()` reverses that, so run `animate.setup()` again after every rebuild before rendering the animation.

## Running code

Every module imports `bpy`, so it runs only inside Blender. Put `mustang/` on `sys.path` first. A full build takes several minutes.

- **Headless** (renders, long jobs, parallel work on `tmp/` copies of the `.blend`):
  `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python tmp/job.py`, where `job.py` inserts the `mustang` path, runs `build.main()`, the checks and the export, and writes its results to a JSON file in `tmp/`. To work on the saved scene instead, pass `output/mustang_67_fastback.blend` before `--python`. The headless animation render command is in the `animate.py` docstring.
- **Live GUI via the Blender MCP**: `build.py` reloads its own submodules but not itself, `export`, `studio` or `animate`. Pop all of them from `sys.modules` before importing. The MCP link times out on long calls, so schedule long work with `bpy.app.timers.register(job)`, have `job` write a status JSON to `tmp/`, and poll that file from the shell. macOS App Nap throttles GUI timers while the Mac is idle, so run long renders headless.
- **Outside Blender**: `check_plates.py`, `inspect_3mf.py`, `merge_3mf.py` and `bambu_presets.py` run on the system `python3`, which has no numpy. numpy exists only in Blender's bundled python (`/Applications/Blender.app/Contents/Resources/<version>/python/bin/python3.13`).

## Checks

There is no test suite. These checks stand in for it:

- `printcheck.run()` on the built scene: `problems`, `overlaps_with_body`, `mirror_mismatches` and `part_overlaps` must all be empty. Intended exceptions are declared at the top of `printcheck.py` (`ASYMMETRIC_PAIRS`, `ONE_SIDED`, `PRESS_FITS`).
- For hood or door changes, also step the hood and doors through their opening range and check `printcheck.overlap_volume` against the Body, the interior tub and the bay parts.
- The report from `export.run()`: `non_manifold` must be 0 for every STL, and `floating` must be empty except on the parts printed on supports (body, hood, engine_block, bumper_rear; see `merge_3mf.OBJECT_SETTINGS`).
- Lint (ruff is not installed): `cd mustang && uvx ruff check --no-cache --select E,F,W --ignore E731 --line-length 140 .`
- Visual check: render the matching `Cam_P*` view and compare it side by side with its photo (`ffmpeg ... hstack` into `tmp/compare/`; PIL is not available).

## Print pipeline

1. In Blender: `export.run()` writes `output/stl/` (one STL per unique part, in print orientation, centred, on Z=0) plus `manifest.json`, and deletes stale STLs. `export.run_assembled()` writes `output/stl_assembled/` (every part in place on the car, for CAD viewing).
2. `mustang/make_project.sh [OUT.3mf]` runs the Bambu Studio CLI once per colour group and arranges each group on its own plates. `merge_3mf.py` then merges the groups, Bambu re-saves the result, and the script checks it against the manifest (every part placed `qty` times in its colour, inlays inside their host) and against the bed bounds (`check_plates.py`). A new part needs both an `export.PARTS` entry and an entry in one of the `build_group` lines, or the manifest check fails. The default output, `output/mustang_67_fastback_1-24.3mf`, is also the file the user tunes and re-saves in the Bambu Studio GUI. Write verification runs to `tmp/`, and regenerate the default only when asked.
3. The Bambu CLI ignores preset inheritance, which is why `bambu_presets.py` flattens the X2D / 0.12 mm / PLA presets. Per-object support and wall settings live in `merge_3mf.OBJECT_SETTINGS` and `ALL_OBJECT_SETTINGS`, not in the profile.
4. To slice: `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio --debug 2 --slice 0 --outputdir DIR --export-3mf sliced.3mf PROJECT.3mf`. Then read `DIR/result.json` (`sliced_plates[].warning_message`, print time, filament use).

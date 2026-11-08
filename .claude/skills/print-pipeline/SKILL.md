---
name: print-pipeline
description: Export the Mustang to STLs, build and check the Bambu Studio 3MF project, slice it, or convert the assembled STLs to STEP for Shapr3D. Use when running export.run()/run_assembled(), make_project.sh, merge_3mf.py, bambu_presets.py, slicing, or make_step.py, or when adding a part to the print manifest.
---

# Print pipeline and CAD export

The default project, `output/mustang_67_fastback_1-24.3mf`, is the file the user tunes and re-saves in the Bambu Studio GUI. Write verification runs to `tmp/`, and regenerate the default only when asked.

## Print pipeline

1. In Blender: `export.run()` writes `output/stl/` (`53` STLs: one per unique part and inlay, in print orientation, centred, on `Z=0`) plus `manifest.json`, and deletes stale STLs. `export.run_assembled()` writes `output/stl_assembled/` (`67` car parts in place on the car) plus a `manifest.json` of object names and print colours.
2. `mustang/make_project.sh [OUT.3mf]` runs the Bambu Studio CLI once per plate group (`1_body`, `1_hood`, `1_doors`, `2_black`, `3_silver`, `3_silver_small`, `3_bumper`, `4_red`, `5_blue`) and arranges each group on its own plates (`9` plates total, `73` printed pieces, isolating miniature chrome trims, bevel gears, and multi-fit motor couplers onto `3_silver_small`). `merge_3mf.py` then merges the groups, Bambu re-saves the result, and the script checks it against the manifest (every part placed `qty` times in its colour, inlays inside their host) and against the bed bounds (`check_plates.py`). A new part needs both an `export.PARTS` entry and an entry in one of the `build_group` lines, or the manifest check fails.
3. The Bambu CLI ignores preset inheritance, which is why `bambu_presets.py` flattens the X2D / 0.12 mm / PLA presets. Per-object support, outer-only brim, and gentle small-part wall speed overrides live in `merge_3mf.OBJECT_SETTINGS` (`body.stl`, `hood.stl`, `trunk_lid.stl`, `engine_block.stl`, `bumper_rear.stl` for tree supports; `SMALL_PART_BRIM` / `SLENDER_BAR_BRIM` / `TALL_PIPE_BRIM` for miniature and slender parts) and `ALL_OBJECT_SETTINGS` (`wall_generator: arachne`), while `complete_settings` enables `reduce_crossing_wall: 1` and `25 mm/s` first-layer speed.
4. To slice: `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio --debug 2 --slice 0 --outputdir DIR --export-3mf sliced.3mf PROJECT.3mf`. Then read `DIR/result.json` (`sliced_plates[].warning_message`, print time, filament use).
5. **Independent AI Edition (`v3.0.0`, no STEP export required)**: `mustang/ai_edition.build_and_export()` writes `output/ai_edition/mustang_67_ai_edition.blend` and `output/ai_edition/stl/` (`55` STLs / `75` printed pieces, adding `waymo_pod.stl` on `1_doors` and `gc9a01_bezel.stl` on `3_silver_small`), and `mustang/make_ai_project.sh` builds both the 9-plate Full Bambu Lab X2D project at `output/ai_edition/mustang_67_ai_edition_x2d.3mf` (`55` STLs / `75` pieces) and the 3-plate Minimal Hardware-Test Prototype project at `output/ai_edition/mustang_67_ai_edition_prototype_x2d.3mf` (`21` STLs / `28` pieces across 3 zero-support plates).

## CAD export

`uv run mustang/make_step.py`, run after `export.run_assembled()`, turns `output/stl_assembled/` into STEP for Shapr3D, which imports an STL only as a reference mesh it cannot measure or edit. It writes a solid per part into `output/step/` and the whole car as one assembly of named, coloured parts, `output/mustang_67_fastback.step`. Every triangle becomes a planar face and only exactly coplanar neighbours merge, so the files keep the full mesh detail.

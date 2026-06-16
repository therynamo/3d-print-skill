# Progress Tracker

> Live checkpoint state for the 3D Print Skill. Update this whenever a checkpoint
> is reached. See `PLAN.md` for the full phase definitions and "HOW TO RESUME".

**Current phase:** Phase 2 complete → Phase 3 next
**Status:** CHECKPOINT 2 passed

## Next action
Begin Phase 3 — Slice + adjustment engine. Create OrcaSlicer Tina 2S PLA/PETG
profiles (port from Wiibuilder/Cura TINA2S def), build `slice.py` (invoke
OrcaSlicer CLI, parse time/grams/layers, apply codified adjustment rules + consult
`lessons`), and finalize `references/adjustment-rules.md`. Verify CHECKPOINT 3:
slice a model -> valid gcode + summary; a >50deg overhang auto-enables supports
with an explanation.

## Phase 2 notes
- ingest.py: local path + direct http(s) file URL + zip extraction all work.
  Printables model pages need auth/API -> handled gracefully (asks for direct
  file/zip URL). Full Printables scraping = follow-up.
- prepare.py: trimesh bbox, Tweaker-3 auto-orient (-min sur), uniform scale-to-fit
  (1mm margin/side), OpenSCAD PNG thumbnail. Verified: demo STL fits; synthetic
  200x150x180 box scaled x0.49 to fit; thumbnails render correctly.
- **OpenSCAD gotcha:** the `openscad` cask is 2021.01 Intel-only -> "Bad CPU type"
  on M3. Use `openscad@snapshot` (universal). Now installed at /Applications/OpenSCAD.app.
- Tweaker-3 (GPL) fetched to ~/.3dprint/vendor (not committed); invoked via subprocess.

## Verified tool paths (this Mac)
- OrcaSlicer CLI: `/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer` (v2.3.2)
- OpenSCAD: `/Applications/OpenSCAD-2021.01.app/Contents/MacOS/OpenSCAD`
- venv: `~/dev/3d-print-skill/.venv` (trimesh, lxml, numpy, requests). Python 3.14.
- Runtime data: `~/.3dprint/` (history.db, work/, downloads/)
- **stl-thumb DROPPED** (not in Homebrew) → OpenSCAD renders all PNGs.

## Checkpoint log
- [x] CHECKPOINT 0 — scaffolding + symlink + initial commit (2026-06-16)
- [x] CHECKPOINT 1 — printer registry + DB + setup doctor (2026-06-16)
- [x] CHECKPOINT 2 — ingest + prepare (orient/scale/thumbnail) (2026-06-16)
- [ ] CHECKPOINT 1 — printer registry + DB
- [ ] CHECKPOINT 2 — ingest + prepare
- [ ] CHECKPOINT 3 — slice + adjustment engine
- [ ] CHECKPOINT 4 — OctoPrint upload + confirm + job logging
- [ ] CHECKPOINT 5 — text→3D
- [ ] CHECKPOINT 6 — outcome review loop
- [ ] CHECKPOINT 7 — polish + open-source packaging

## Notes / discoveries
- Tina 2S CONFIRMED specs (official guide): build vol **100(X)×105(Y)×100(Z) mm**,
  0.4 mm nozzle, nozzle max 245 °C, **heated bed max 60 °C**, flexible spring-steel
  plate, 3-pt auto-level, max 200 mm/s, Marlin (TMC2208). Bundled slicer = Wiibuilder
  (Cura-based, has TINA2S profile to port from).
- **PETG caveat:** bed can't exceed 60 °C → PETG needs glue stick + brim; flag as
  marginal/out-of-spec.
- **Baud unresolved:** Wiibuilder=115200, OctoPrint community=1,000,000. Verify.
- License = MIT. Install via Homebrew approved.
- OrcaSlicer CLI path: TBD (resolve in setup.py).

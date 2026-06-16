# Progress Tracker

> Live checkpoint state for the 3D Print Skill. Update this whenever a checkpoint
> is reached. See `PLAN.md` for the full phase definitions and "HOW TO RESUME".

**Current phase:** Phase 1 complete → Phase 2 next
**Status:** CHECKPOINT 1 passed

## Next action
Begin Phase 2 — Ingest + prepare. Build `ingest.py` (STL/3MF/.scad passthrough +
Printables/direct URL download + unzip) and `prepare.py` (trimesh bbox vs active
printer bed, auto scale-to-fit, Tweaker-3 auto-orient, OpenSCAD thumbnail). Vendor
Tweaker-3 into `vendor/`. Verify CHECKPOINT 2 with a known STL + a Printables URL.

## Verified tool paths (this Mac)
- OrcaSlicer CLI: `/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer` (v2.3.2)
- OpenSCAD: `/Applications/OpenSCAD-2021.01.app/Contents/MacOS/OpenSCAD`
- venv: `~/dev/3d-print-skill/.venv` (trimesh, lxml, numpy, requests). Python 3.14.
- Runtime data: `~/.3dprint/` (history.db, work/, downloads/)
- **stl-thumb DROPPED** (not in Homebrew) → OpenSCAD renders all PNGs.

## Checkpoint log
- [x] CHECKPOINT 0 — scaffolding + symlink + initial commit (2026-06-16)
- [x] CHECKPOINT 1 — printer registry + DB + setup doctor (2026-06-16)
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

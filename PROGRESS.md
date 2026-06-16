# Progress Tracker

> Live checkpoint state for the 3D Print Skill. Update this whenever a checkpoint
> is reached. See `PLAN.md` for the full phase definitions and "HOW TO RESUME".

**Current phase:** Phase 0 complete → awaiting go-ahead for Phase 1
**Status:** CHECKPOINT 0 passed (symlink resolves, initial commit 0372ffd)

## Next action
Begin Phase 1 — Environment + printer registry. Verify OrcaSlicer/OpenSCAD/
stl-thumb on PATH (install if missing), build `common.py` + `printers.py`, create
`~/.3dprint/history.db`, seed Tina 2S. Confirm real usable Z (100 vs 110 mm) and
the OrcaSlicer CLI binary path with the user before relying on them.

## Checkpoint log
- [x] CHECKPOINT 0 — scaffolding + symlink + initial commit (2026-06-16)
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

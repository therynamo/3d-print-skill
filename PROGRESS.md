# Progress Tracker

> Live checkpoint state for the 3D Print Skill. Update this whenever a checkpoint
> is reached. See `PLAN.md` for the full phase definitions and "HOW TO RESUME".

**Current phase:** Phase 3 complete → Phase 4 next
**Status:** CHECKPOINT 3 passed

## Next action
Begin Phase 4 — OctoPrint upload + confirm gate + job logging. Build `octoprint.py`
(upload sliced gcode to `/api/files/local` via X-Api-Key; NEVER auto-start a print —
require an explicit confirm before issuing the print command) and `jobs.py` (CRUD over
the `prints` table: list/show/update status). Verify CHECKPOINT 4: end-to-end on the
real Tina 2S — upload a calibration gcode, confirm, print, and log the job.

## Phase 3 notes
- **Slicer = PrusaSlicer** (2.9.5, universal at /Applications/PrusaSlicer.app/...).
  Chosen over OrcaSlicer for clean CLI: self-contained INI + `--export-gcode`.
- Profiles: `profiles/tina2s_pla.ini`, `tina2s_petg.ini`. PETG pins bed at 60C
  (out-of-spec) and forces a 5mm brim + glue-stick warning.
- **CLI override gotcha:** PrusaSlicer's named CLI flags don't cover every config
  key (booleans like `--support-material` take NO value -> "No such file: 1").
  slice.py instead writes a *merged effective INI* (profile + overrides, replacing
  existing keys to avoid "duplicate key name") and `--load`s that.
- **grams gotcha:** PrusaSlicer leaves `total filament used [g] = 0.00` unless
  `filament_density` is set. Added density (PLA 1.24, PETG 1.27); slice.py also
  derives grams = cm3 * density as a fallback.
- Adjustment engine (`references/adjustment-rules.md`): R1 supports (overhang
  severity = asin(-normal.z); >50deg & >=1cm2 -> support_material=1; also honors
  PrusaSlicer's own stability warning via a re-slice), R2/R3 brim (tall aspect>4 /
  footprint<10mm), R4 PETG warning. Lessons table layered on top.
- Verified: demo model (90deg overhang, 9.15cm2) auto-enabled supports w/ explanation;
  PLA 3h4m/23.91g/473 layers, PETG 3h30m/25.8g; print logged as row #1.

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
- [x] CHECKPOINT 3 — slice + adjustment engine (2026-06-16)
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

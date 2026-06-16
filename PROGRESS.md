# Progress Tracker

> Live checkpoint state for the 3D Print Skill. Update this whenever a checkpoint
> is reached. See `PLAN.md` for the full phase definitions and "HOW TO RESUME".

**Current phase:** Phase 7 complete → Phase 8 next
**Status:** CHECKPOINT 7 passed (CHECKPOINT 4 live print still pending hardware)

## Next action
Begin Phase 8 — Run the skills evaluation, generate HTML + JSON results, fix any
regressions, then SendUserFile the HTML + data to the user for mobile viewing.

## ACTION REQUIRED (you, the user) to finish CHECKPOINT 4
The OctoPrint bridge is built + unit-tested offline, but a real print needs your
credentials + the powered-on Tina 2S:
  1. Set `export OCTOPRINT_URL=...` and `export OCTOPRINT_API_KEY=...` (see setup.py).
  2. `python scripts/octoprint.py upload <gcode> --print-id N`   (stages, no print)
  3. After eyeballing, confirm, then: `python scripts/octoprint.py start <remote> --yes`
  4. `python scripts/octoprint.py status` to watch progress.

## Phase 7 notes
- Authored SKILL.md (frontmatter name=3d-print + description; hard confirm-gate rule;
  full pipeline; text-to-3D; review/learn; progressive disclosure), README.md, MIT
  LICENSE. Tweaker-3 GPL stays fetched-not-bundled (noted in both README + LICENSE).
- Verified all 9 scripts `--help` cleanly and the ~/.claude/skills/3d-print symlink
  resolves to SKILL.md.

## Phase 6 notes
- `review.py`: record (rating/notes/images + auto status done>=3/failed<3), learn
  (insert a lessons row scoped to printer+material, adjustment as key=value), lessons
  (list). The agent reads the recorded image paths to assess quality.
- Verified the full feedback loop: record outcome on #1 -> learn brim_width=6 for
  tina2s/PLA -> next slice.py auto-applied it ("Lesson: applied brim_width=6").

## Phase 5 notes
- `describe.py`: compile/preview harness for text->3D. The **agent** authors the
  OpenSCAD (parametric, mm); describe.py compiles -> STL, renders PNG via
  common.render_stl_png, reports dims. Accepts --code / --scad / stdin.
- Verified: "30mm cube with a 10mm hole" -> correct STL + preview PNG (hole visible).

## Phase 4 notes
- `octoprint.py`: upload / start / status. **upload never prints** (POST
  /api/files/local with select=true, print=false). **start** issues
  {"command":"select","print":true} and HARD-REQUIRES `--yes` -> refuses otherwise
  (gate verified offline before any network call). Both update prints.status +
  octoprint_job. Uses `requests` (already a dep).
- `jobs.py`: CRUD over prints — list/show/set-status/outcome (rating 1-5 + notes +
  images csv). Verified offline against row #1.
- Live end-to-end print is the only unverified piece; needs $OCTOPRINT_API_KEY + the
  physical printer. Steps written under "ACTION REQUIRED" above.

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

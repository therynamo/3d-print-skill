# 3D Print Skill — Build Plan

A reproducible Claude **skill** that lets any LLM agent take a printable input
(STL / 3MF / `.scad` / URL / natural-language description) and drive it all the
way to a confirmed print on the user's 3D printer: ingest → prepare → slice →
preview → **confirm** → upload to OctoPrint → log → later review outcome photos.

Open-source. Repo lives at `~/dev/3d-print-skill`, symlinked into
`~/.claude/skills/3d-print`.

---

## HOW TO RESUME (read this first after any context compaction)

1. Read this whole file.
2. Run `cat PROGRESS.md` for the current checkpoint and the exact next action.
3. Phases are sequential; each ends at a **CHECKPOINT** that must be verifiable
   (a command to run + expected result). Do not advance past a checkpoint until
   its verification passes. Update `PROGRESS.md` when a checkpoint is reached.
4. Never guess hardware/profile values — they are recorded in "Locked decisions".
   If something is missing, ask the user rather than inventing it.

---

## Locked decisions (from design interview, 2026-06-16)

| Topic | Decision |
|---|---|
| Packaging | Claude **skill** = `SKILL.md` + bundled CLI scripts (portable to any harness with shell) |
| Run host | The **Mac (M3 Ultra)**; reaches `octopi.local` over the network |
| Slicer | **OrcaSlicer CLI** (community pick for Mac + non-Bambu FDM). Tina 2S profile ported from known-good community Cura profile, validated with a calibration print |
| Text→3D | **OpenSCAD** (LLM authors parametric code → PNG preview → STL) |
| Print trigger | **Upload + explicit confirm** (agent never auto-starts) |
| Materials | **PLA default + PETG preset**; Tina 2S **has a heated bed** |
| URL sources | **Printables** + **any direct file URL** (.stl/.3mf/.zip) |
| Settings model | **One solid default profile** + codified rules for when to deviate (agent explains every deviation) |
| Oversize models | **Scale-to-fit automatically**, note it in the summary |
| Orientation | **Auto-orient** (Tweaker-3 `--minimize surfaces`), note it |
| Post-start | **Fire-and-forget**; log to SQLite. User later sends outcome photos → agent grades/triages/feeds back |
| Multi-printer | First-class: add / switch / retire; every job stamped with its printer; retiring preserves history |
| Credentials | **Env vars** `OCTOPRINT_URL`, `OCTOPRINT_API_KEY` (per-printer overrides resolved from DB) |

### Seeded printer
**Tina 2S** — bed `100×100×110 mm` (CONFIRM real usable Z; community Cura def is
100w×110d×~100h — flag mismatch before trusting), heated bed, single 0.4 mm
extruder, Marlin flavor, OctoPrint serial **1,000,000 baud**, materials PLA+PETG,
default printer.

---

## Toolchain (all local, open-source, installed on the Mac)

| Tool | Role | Install |
|---|---|---|
| OrcaSlicer (CLI) | slice → G-code | brew cask / appimage; CLI binary inside app bundle |
| OpenSCAD | text→model, PNG preview, STL export | `brew install --cask openscad` |
| Tweaker-3 | auto-orient STL | `pip` / vendored `MeshTweaker.py` (ChristophSchranz/Tweaker-3) |
| stl-thumb | headless STL/3MF → PNG thumbnail | `brew install stl-thumb` (fallback: OpenSCAD render) |
| trimesh (+lxml) | bbox check, scale-to-fit, reads STL **and** 3MF | `pip install trimesh lxml numpy` |
| requests | Printables/direct download, OctoPrint REST | `pip install requests` |

Decision: scripts in **Python** (one venv at `~/.3dprint/venv` or `pipx`), shelling
out to OrcaSlicer/OpenSCAD/stl-thumb. Record exact OrcaSlicer CLI invocation in
`references/octoprint-api.md` once verified on the machine.

---

## Repo / skill layout (target)

```
3d-print-skill/                      # repo root == skill root (SKILL.md here)
├── SKILL.md                         # trigger + orchestration + rules summary
├── PLAN.md                          # this file
├── PROGRESS.md                      # live checkpoint tracker
├── README.md                        # open-source readme (Phase 7)
├── LICENSE                          # (Phase 7)
├── requirements.txt
├── references/
│   ├── adjustment-rules.md          # full codified deviation rules
│   └── octoprint-api.md             # endpoints + verified CLI invocations
├── scripts/
│   ├── common.py                    # config/env, DB connection, printer resolution
│   ├── ingest.py                    # STL|3MF|URL|.scad → normalized model file
│   ├── describe.py                  # text → OpenSCAD → preview.png → STL
│   ├── prepare.py                   # bbox check, scale-to-fit, auto-orient, thumbnail
│   ├── slice.py                     # OrcaSlicer CLI + profile → gcode + summary
│   ├── octoprint.py                 # upload (+ start AFTER confirm), printer-aware
│   ├── printers.py                  # add / list / switch / retire printers
│   ├── jobs.py                      # CRUD over print history
│   └── review.py                    # attach outcome photo + rating/notes; update lessons
├── profiles/
│   ├── tina2s_pla.ini / .json
│   └── tina2s_petg.ini / .json
└── vendor/Tweaker-3/                # vendored auto-orient (or pip dep)
```

---

## Data model — SQLite at `~/.3dprint/history.db`

**printers**: id, name, model, bed_x, bed_y, bed_z, nozzle_d, gcode_flavor,
octoprint_url, api_key_env, baud, materials(csv), status(active|retired),
is_default, created_ts

**prints**: id, ts, source_type(stl|3mf|scad|url|text), source_ref, model_path,
printer_id→printers, material, settings_json, slice_summary_json (time/grams/
layers), gcode_path, octoprint_job, status(sliced|uploaded|printing|done|failed),
outcome_rating(1-5|null), outcome_notes, outcome_images(csv), adjustments_json

**lessons**: id, printer_id, material, trigger, learned_adjustment, source_print_id,
ts — outcome reviews append here; `slice.py` consults relevant lessons so the agent
improves per-printer over time.

---

## Codified adjustment rules (default profile + when to deviate)

Default (PLA, Tina 2S): 0.2 mm layer · 3 walls (~1.2 mm) · 15–20% gyroid infill ·
nozzle 205 °C · bed 60 °C · 100% cooling after layer 1 · skirt · supports off.

| Trigger detected | Adjustment |
|---|---|
| Overhang > ~50° from vertical, or bridge > ~5 mm | enable supports |
| Small footprint / tall aspect (h > ~3× base) / tippy | add brim |
| Fine/small features | layer height 0.12–0.16 mm |
| Tall, simple, low-detail | layer height 0.28 mm (faster) |
| Decorative | 2 walls, 10–15% infill |
| Functional / load-bearing | 4+ walls FIRST, then 30–50% infill |
| Stress along layer lines | suggest reorientation (weakest between layers) |
| PETG selected | nozzle ~235 °C, bed ~75 °C, fan 30–50% (off layer 1), higher retraction, slower, brim recommended |

Full version with citations lives in `references/adjustment-rules.md`.

---

## PHASES & CHECKPOINTS

### Phase 0 — Scaffolding  *(in progress)*
- [x] Create repo, `git init`, subfolders
- [x] Write `PLAN.md`
- [ ] Write `PROGRESS.md`, `requirements.txt`, `.gitignore`
- [ ] Symlink `~/.claude/skills/3d-print` → repo root
- [ ] Initial commit
- **CHECKPOINT 0:** `ls ~/.claude/skills/3d-print/PLAN.md` resolves through the
  symlink; `git -C ~/dev/3d-print-skill log --oneline` shows the initial commit.

### Phase 1 — Environment + printer registry foundation
- [ ] `requirements.txt` + venv bootstrap; verify OrcaSlicer/OpenSCAD/stl-thumb on PATH
- [ ] `common.py`: env loading, DB init/migrate, printer resolution (active/default)
- [ ] `printers.py`: add / list / switch / retire; seed Tina 2S
- [ ] DB created at `~/.3dprint/history.db`
- **CHECKPOINT 1:** `python scripts/printers.py list` shows Tina 2S as active+default
  with correct bed dims; `printers.py add`/`switch`/`retire` round-trip works.

### Phase 2 — Ingest + prepare (no printing yet)
- [ ] `ingest.py`: STL/3MF/.scad passthrough; URL download (Printables + direct);
      unzip + pick model file(s)
- [ ] `prepare.py`: trimesh bbox vs active printer bed; auto scale-to-fit; Tweaker-3
      auto-orient; stl-thumb thumbnail
- **CHECKPOINT 2:** feed a known STL and a Printables URL → get a normalized,
  bed-fitting, oriented model file + a `thumbnail.png`. Oversize test scales down
  and reports the factor.

### Phase 3 — Slice + adjustment engine
- [ ] `profiles/`: Tina 2S PLA + PETG profiles for OrcaSlicer
- [ ] `slice.py`: invoke OrcaSlicer CLI; parse time/grams/layers; apply codified
      rules + consult `lessons`; record `adjustments_json`
- [ ] `references/adjustment-rules.md` finalized
- **CHECKPOINT 3:** slice a test model → valid `.gcode` + summary JSON; a model with
  a >50° overhang auto-enables supports and the summary explains why.

### Phase 4 — OctoPrint upload + confirm gate + job logging
- [ ] `octoprint.py`: upload to active printer; **start only after explicit confirm**;
      verify start
- [ ] `jobs.py`: full CRUD; log at each stage
- **CHECKPOINT 4:** end-to-end on real Tina 2S: agent shows preview+summary, waits,
  then on "go" uploads and starts; a `prints` row reaches status=printing. (Run a
  calibration print to validate the ported profile.)

### Phase 5 — Text → 3D (describe → preview → print)
- [ ] `describe.py`: NL → OpenSCAD → `preview.png` → STL; iterate on feedback
- [ ] Wire into the main flow before `prepare`
- **CHECKPOINT 5:** "a 40 mm cube with a 10 mm hole" → preview PNG → approve →
  flows into slice/print pipeline.

### Phase 6 — Outcome review loop
- [ ] `review.py`: attach user photo to a job, set rating/notes, append `lessons`
- [ ] SKILL.md: how the agent grades quality, triages defects, proposes reprint tweaks
- **CHECKPOINT 6:** given a job id + a photo, agent records an assessment and writes
  at least one actionable lesson that a later slice would honor.

### Phase 7 — Polish, docs, open-source packaging
- [ ] `SKILL.md` finalized (tight description for good trigger accuracy)
- [ ] `README.md`, `LICENSE`, install script, sample profiles, screenshots
- [ ] Test prompts (with/without skill) per skill-creator guidance
- **CHECKPOINT 7:** fresh-machine install steps work from README; SKILL.md triggers
  on realistic prompts.

---

## Open questions to confirm with user as they arise
- Exact usable **Z height** of the Tina 2S (100 vs 110 mm).
- Exact OrcaSlicer CLI binary path on this Mac + whether to install via cask or AppImage.
- License choice for the repo (MIT?).
- Whether Printables needs auth for the models the user pulls (anti-bot).

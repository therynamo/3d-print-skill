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

### Seeded printer (CONFIRMED from official WEEFUN Tina 2S guide, 2026-06-16)
**Tina 2S** — build volume **X=100, Y=105, Z=100 mm** · single **0.4 mm** nozzle
(0.2/0.3/0.4 included) · nozzle max **245 °C** · **heated bed max 60 °C** ·
flexible spring-steel magnetic plate · 3-point auto-level · max speed 200 mm/s ·
Marlin (Silent TMC2208) · connectivity TF/APP/WiFi/USB · bundled slicer
**Wiibuilder** (Cura-based, ships a TINA2S profile — port from it) · default printer.

**USB/serial baud: UNRESOLVED** — Wiibuilder serial dialog shows 115200; OctoPrint
community guide uses 1,000,000. Verify empirically when wiring OctoPrint; record
the winner in PROGRESS.md.

**PETG constraint:** bed caps at 60 °C (PETG normally wants 70–80 °C). So the PETG
preset must rely on **glue stick + brim** for adhesion, bed pinned at 60 °C, and
flag to the user that PETG adhesion is marginal on this hardware. Officially the
printer lists PLA/PLA+/TPU; PETG is user-driven and out-of-spec.

---

## Toolchain (all local, open-source, installed on the Mac)

| Tool | Role | Install |
|---|---|---|
| OrcaSlicer (CLI) | slice → G-code | brew cask / appimage; CLI binary inside app bundle |
| OpenSCAD | text→model, PNG preview, STL export | `brew install --cask openscad` |
| Tweaker-3 | auto-orient STL | `pip` / vendored `MeshTweaker.py` (ChristophSchranz/Tweaker-3) |
| ~~stl-thumb~~ | DROPPED (not in Homebrew). Use **OpenSCAD** for all PNG rendering: trimesh converts 3MF→STL, then OpenSCAD imports+renders | — |
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
| PETG selected (Tina 2S) | nozzle ~235 °C, **bed pinned 60 °C (hardware max) + glue stick + brim required**, fan 30–50% (off layer 1), higher retraction, slower; warn adhesion is marginal |

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
- [ ] `scripts/setup.py` (a "doctor" + installer): checks Homebrew, installs
      OrcaSlicer/OpenSCAD/stl-thumb if missing, creates the venv + pip deps,
      locates the OrcaSlicer CLI binary, and **interactively walks the user through**
      the one-time printer/credential setup (see "Setup UX" below). Idempotent;
      safe to re-run as a health check.
- [ ] `requirements.txt` + venv bootstrap; verify OrcaSlicer/OpenSCAD/stl-thumb on PATH
- [ ] `common.py`: env loading, DB init/migrate, printer resolution (active/default)
- [ ] `printers.py`: add / list / switch / retire; seed Tina 2S
- [ ] DB created at `~/.3dprint/history.db`
- **CHECKPOINT 1:** `python scripts/printers.py list` shows Tina 2S as active+default
  with correct bed dims (100×105×100); `printers.py add`/`switch`/`retire` round-trip
  works; `setup.py` reports all tools green.

#### Setup UX (what the user does once, and how the agent assists)
The agent should make first-run nearly hands-off:
1. Run `setup.py` → it installs missing tools via Homebrew and reports a checklist.
2. **OctoPrint API key**: agent explains where to get it (OctoPrint → Settings →
   Application Keys, or the legacy API key), then helps the user export
   `OCTOPRINT_URL` (default `http://octopi.local`) and `OCTOPRINT_API_KEY` into
   their shell profile (`~/.zshrc`). Agent offers to append the lines; user pastes
   the key value (never commit it).
3. **Connectivity test**: `setup.py` pings the OctoPrint API (`/api/version`) and
   confirms the printer is reachable + the key works.
4. **Baud**: if/when serial control is needed, agent guides adding the printer in
   OctoPrint and resolving the 115200-vs-1,000,000 baud question empirically.
5. Seed/confirm the Tina 2S record; multi-printer users repeat `printers.py add`.

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
- [ ] `README.md`, `LICENSE` (MIT), install script, sample profiles, screenshots
- [ ] Test prompts (with/without skill) per skill-creator guidance

### Phase 8 — Skills evaluation + deliver report to user
- [ ] Use the skill-creator's eval tooling (`scripts/` + `eval-viewer/`): author
      2–3 realistic test prompts (e.g. "print this STL", "make me a 40 mm cube with
      a hole and print it", "slice this Printables URL for PETG") plus trigger-eval
      queries for the description.
- [ ] Run the evaluation, generate the **JSON data** + render the **HTML viewer**.
- [ ] Review results; make adjustments to SKILL.md/scripts; re-run until passing.
- [ ] **Send the user the HTML + data files** (via SendUserFile) so they can view
      results on mobile.
- **CHECKPOINT 8:** eval run completes, HTML+JSON produced and delivered to the user,
  and any regressions surfaced by the eval are fixed (or logged as follow-ups).
- **CHECKPOINT 7:** fresh-machine install steps work from README; SKILL.md triggers
  on realistic prompts.

---

## Resolved
- **Bed**: 100 × 105 × 100 mm (official guide).
- **License**: MIT (add `LICENSE` in Phase 7).
- **Install**: approved to `brew install` OrcaSlicer + openscad + stl-thumb; locate
  CLI binary during Phase 1 `setup.py`.

## Open questions to confirm as they arise
- OrcaSlicer CLI binary path on this Mac (resolve in `setup.py`).
- Serial **baud** for OctoPrint: 115200 (Wiibuilder) vs 1,000,000 (community) — verify.
- Whether Printables needs auth for the models the user pulls (anti-bot).

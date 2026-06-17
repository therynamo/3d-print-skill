---
name: 3d-print
description: >-
  Take a printable model (STL / 3MF / OBJ / OpenSCAD / a URL to a file, or a
  natural-language description) all the way to a confirmed print on a 3D printer
  via OctoPrint. Use when the user wants to slice, preview, or print a model;
  asks to "print this", "make a model of ...", "slice this STL", or to review how
  a finished print turned out. Handles ingest, auto-orient, scale-to-fit, slicing
  with codified adjustment rules, preview, upload, an explicit print confirm, and
  an outcome/lessons feedback loop.
---

# 3D Print

Drive a model from input to a confirmed print. Every script lives in `scripts/` and
shares state through a SQLite DB + work dir at `~/.3dprint/` (outside the repo).

## Hard safety rules
**Never start a print without explicit user confirmation.** Slicing, preview, and
upload are safe and may run automatically. Starting a print is physical and
hard-to-reverse: `octoprint.py start` refuses without `--yes`. Only pass `--yes`
after the user has seen the slice summary (time/grams) and explicitly said to print.

**Never reveal secrets.** Credentials (`OCTOPRINT_API_KEY`, `PRINTABLES_PASSWORD`,
`PRINTABLES_USERNAME`/`PRINTABLES_EMAIL`, any value from `.env` or the matching env
vars) are passed through to the tool that needs them and **must never** be printed,
echoed, logged, written to files, included in command output the user sees, or
repeated back in chat. Do not `cat`/`echo`/`grep` the `.env` file or run commands
that would surface its contents. Use the values only as a proxy to perform the task
(log in, call the API). If you must confirm a credential is set, check only that the
variable is non-empty — never display its value (not even partially/masked).

## Setup (first run)
```
python scripts/setup.py --seed --fetch-tweaker   # doctor + seed Tina 2S + get auto-orient
```
It checks PrusaSlicer, OpenSCAD (must be the `openscad@snapshot` arm64 cask),
Python deps, the DB, and OctoPrint reachability, then prints exact next steps.

Credentials live in env vars, never committed. Set them either by exporting in your
shell (e.g. `~/.zshrc`) **or** in a gitignored `.env` file — both `<repo>/.env` and
`~/.3dprint/.env` are auto-loaded. Shell exports always win over `.env`, so an
existing shell setup keeps working untouched. Keys:
`OCTOPRINT_URL`, `OCTOPRINT_API_KEY`.

## The pipeline
Run these in order; each prints a summary (add `--json` for machine-readable output).

1. **Ingest** — normalize any input to a local model file.
   `python scripts/ingest.py <path|http(s)-url|zip>`
   Printables model-page URLs are handled automatically via login (see below).
   Other sites' *page* URLs still need a direct file/zip link — it will say so.

2. **Prepare** — auto-orient (min support), scale-to-fit the bed, thumbnail.
   `python scripts/prepare.py <model> [--printer NAME]`

3. **Slice** — material profile + codified adjustment rules + learned lessons.
   `python scripts/slice.py <prepared.stl> --material PLA|PETG [--set key=value ...]`
   Reports time / grams / layers and **why** any setting changed (e.g. a >50°
   overhang auto-enables supports). See `references/adjustment-rules.md`.

4. **Preview & confirm** — show the user the thumbnail + slice summary. `prepare.py`
   and `describe.py` print a `deliver_to_user:` line listing the file(s) to hand the
   user (and include `deliver` in `--json`); send those with the file-delivery tool.
   By default this is **both** the inline PNG and the STL — macOS Quick Look / Preview
   render STL natively, so the user can orbit the model instead of a fixed-angle PNG.
   Set `$PRINT3D_PREVIEW_FORMAT` to `stl`, `png`, or `both` to change this. Wait for an
   explicit "yes, print it."

5. **Upload** (safe, no print):
   `python scripts/octoprint.py upload <gcode> --print-id <N>`

6. **Start** (only after confirm):
   `python scripts/octoprint.py start <remote_name> --yes --print-id <N>`
   Then `python scripts/octoprint.py status` to report progress, then stop — no polling.

## Text-to-3D (describe → preview → print)
When the user describes a part, **you** author parametric OpenSCAD (mm units), then:
```
python scripts/describe.py --name <slug> --code '<openscad source>'
```
Show the returned preview, sending the file(s) named in `deliver_to_user:` (the STL
orbits in macOS Preview; see step 4 and `$PRINT3D_PREVIEW_FORMAT`). On approval feed
`stl_path` into prepare → slice → the print flow above.

## Printables login (gated downloads)
Printables has no public API, so downloads are driven through a real Chromium
(Playwright). Set `PRINTABLES_USERNAME` (or `PRINTABLES_EMAIL`) and
`PRINTABLES_PASSWORD` (shell or `.env`). The session is persisted at
`~/.3dprint/printables_state.json`, so the password is only used when there is no
valid session.
```
python scripts/printables.py login [--headed]      # establish/refresh the session
python scripts/printables.py fetch <model-url> [--headed]
```
`ingest.py` calls this automatically for `printables.com` model URLs. If automated
login is blocked (Cloudflare / captcha / 2FA), re-run with `--headed` to log in by
hand once; the saved session is reused on later headless runs. Respect each model's
license; only download what you're entitled to for personal printing.

## Outcome review & learning
When the user sends photos of a finished print:
```
python scripts/review.py record <print_id> --rating 1-5 --notes "..." --images a.jpg,b.jpg
```
Look at the images, assess quality, triage. If a failure has a clear fix, record a
lesson so it is applied automatically next time:
```
python scripts/review.py learn <print_id> --trigger "first-layer lifting" --adjustment "brim_width=6"
```
Lessons are scoped to printer + material and layered on top of the geometric rules.

## Printers
`python scripts/printers.py list|show|add|switch|retire|reactivate|seed`
Supports multiple printers; slice/prepare/upload accept `--printer NAME` and otherwise
use the active default. Seeded default = WEEFUN Tina 2S (100×105×100 mm, 0.4 mm nozzle,
bed max 60 °C → PETG is marginal, needs glue + brim).

## Jobs
`python scripts/jobs.py list|show|set-status|outcome` — inspect/update print history.

## Progressive disclosure
- `references/adjustment-rules.md` — full slicing rule definitions + geometry math.
- `PLAN.md` / `PROGRESS.md` — build plan and live checkpoint state.
- Profiles in `profiles/` are self-contained PrusaSlicer INIs; edit to retune defaults.

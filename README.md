# 3d-print-skill

A portable, open-source [Claude skill](https://docs.anthropic.com/en/docs/claude-code/skills)
that takes a printable model — an STL / 3MF / OBJ / OpenSCAD file, a URL to one, or a
plain-language description — all the way to a confirmed print on a 3D printer via
[OctoPrint](https://octoprint.org/). It ingests, auto-orients, scales to fit the bed,
slices with codified adjustment rules, previews, uploads, prints **only after you
confirm**, and learns from how each print turns out.

Built and tuned for a WEEFUN **Tina 2S** (100×105×100 mm, 0.4 mm nozzle, 60 °C bed),
but the printer registry makes it portable to other machines.

## Why
Slicing decisions (supports, brim, infill, temps) are usually manual. This skill
codifies *when* those adjustments are needed (see
[`references/adjustment-rules.md`](references/adjustment-rules.md)), explains every
change it makes, and closes the loop by turning print failures into lessons it applies
automatically next time.

## Pipeline
`ingest → prepare (orient + scale + thumbnail) → slice (rules + lessons) → preview →
**explicit confirm** → upload → print → outcome review → lessons`

## Requirements
- macOS (Apple Silicon supported), Python 3.12+
- [PrusaSlicer](https://www.prusa3d.com/prusaslicer/) — `brew install --cask prusaslicer`
- [OpenSCAD snapshot](https://openscad.org/) — `brew install --cask openscad@snapshot`
  (the 2021.01 cask is Intel-only and fails on Apple Silicon)
- Python deps: `pip install -r requirements.txt`
- [Tweaker-3](https://github.com/ChristophSchranz/Tweaker-3) (GPL-3.0) for auto-orient —
  fetched at setup, **not** bundled, so this repo stays MIT-clean.
- An OctoPrint instance + API key (set `OCTOPRINT_URL` and `OCTOPRINT_API_KEY`).

## Install
```bash
git clone <this repo> ~/dev/3d-print-skill
cd ~/dev/3d-print-skill
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
python scripts/setup.py --seed --fetch-tweaker     # doctor + seed printer + auto-orient
ln -s "$PWD" ~/.claude/skills/3d-print             # expose as a Claude skill
```

## Quick start
```bash
python scripts/ingest.py model.stl
python scripts/prepare.py ~/.3dprint/work/model.stl
python scripts/slice.py ~/.3dprint/work/model_prepared.stl --material PLA
# review the time/grams + thumbnail, then:
python scripts/octoprint.py upload <gcode> --print-id 1
python scripts/octoprint.py start <remote_name> --yes --print-id 1   # only after you confirm
```

Or describe a part:
```bash
python scripts/describe.py --name bracket --code 'difference(){cube([30,30,10]); translate([15,15,-1]) cylinder(h=12,r=4,$fn=64);}'
```

## Safety
- Prints never auto-start; `octoprint.py start` requires `--yes` *and* user confirmation.
- Secrets stay in env vars; the DB, downloads, and G-code live in `~/.3dprint/`, never
  committed.

## Layout
| Path | Purpose |
|------|---------|
| `SKILL.md` | Agent entry point (when to use + full pipeline) |
| `scripts/` | `setup, printers, ingest, prepare, slice, describe, octoprint, jobs, review` |
| `profiles/` | Self-contained PrusaSlicer INIs (PLA, PETG) |
| `references/` | Adjustment-rule definitions |
| `PLAN.md` / `PROGRESS.md` | Build plan + checkpoint state |

## License
MIT — see [LICENSE](LICENSE). Tweaker-3 (GPL-3.0) is fetched separately at runtime and
invoked as a subprocess, not redistributed here.

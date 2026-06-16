# 3d-print-skill

A [Claude skill](https://docs.anthropic.com/en/docs/claude-code/skills) that takes a model
from input to a finished print through an AI agent. It accepts an STL, 3MF, OBJ, OpenSCAD
file, a URL to one, or a natural-language description, then orients and scales the model,
slices it with codified adjustment rules, previews it, uploads it to
[OctoPrint](https://octoprint.org/), and prints it **only after explicit confirmation**.
Print outcomes are recorded and fed back into future slicing decisions.

Default target is the WEEFUN Tina 2S; other printers are supported via the printer registry.

## Features

- Ingest from local files, direct URLs, or zip archives.
- Automatic orientation (minimize supports) and scale-to-fit the bed.
- Slicing via PrusaSlicer with self-contained PLA and PETG profiles.
- Codified adjustment rules (supports, brim, adhesion) with a plain-language rationale for
  every change — see [`references/adjustment-rules.md`](references/adjustment-rules.md).
- Text-to-3D: describe a part, get a rendered preview before committing to plastic.
- OctoPrint upload with a hard confirmation gate before any print starts.
- Outcome review loop: photos in, quality assessment and lessons out; lessons are applied
  automatically on subsequent prints.
- Multi-printer registry (add, switch, retire).

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| macOS (Apple Silicon supported) | |
| Python 3.12+ | |
| PrusaSlicer | `brew install --cask prusaslicer` |
| OpenSCAD (snapshot build) | `brew install --cask openscad@snapshot` — the 2021.01 cask is Intel-only and fails on Apple Silicon |
| Tweaker-3 (GPL-3.0) | Fetched at setup, not bundled. Used for auto-orient. |
| OctoPrint instance + API key | Set via environment variables (below) |

Python dependencies are listed in `requirements.txt` (trimesh, lxml, numpy, requests).

## Installation

```bash
git clone https://github.com/therynamo/3d-print-skill ~/dev/3d-print-skill
cd ~/dev/3d-print-skill
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt

# Health check, seed the default printer, fetch the auto-orient tool:
python scripts/setup.py --seed --fetch-tweaker

# Expose as a Claude skill:
ln -s "$PWD" ~/.claude/skills/3d-print
```

Configure OctoPrint credentials in your shell profile (`~/.zshrc`). They are never stored in
the repository or database:

```bash
export OCTOPRINT_URL="http://octopi.local"   # use the Pi's IP if .local does not resolve
export OCTOPRINT_API_KEY="your-api-key"
```

`python scripts/setup.py` re-runs the health check at any time and reports exactly what is
missing.

## Default printer

The seeded default is the **WEEFUN Tina 2S**:

| Spec | Value |
|------|-------|
| Build volume | 100 × 105 × 100 mm |
| Nozzle | 0.4 mm |
| Bed temperature | 60 °C max |
| Firmware | Marlin |
| Materials | PLA (recommended), PETG (marginal) |

Because the bed maxes at 60 °C, profiles target 55 °C (PLA) and 58 °C (PETG) — a bed target
set at the ceiling can hang `M190` (wait-for-bed) indefinitely. PETG is supported but
marginal: it relies on a forced brim and a glue stick for adhesion.

## Usage

The pipeline is a sequence of scripts. Each prints a human summary, or JSON with `--json`.

```bash
# 1. Ingest and prepare
python scripts/ingest.py model.stl
python scripts/prepare.py ~/.3dprint/work/model.stl

# 2. Slice (applies adjustment rules + learned lessons)
python scripts/slice.py ~/.3dprint/work/model_prepared.stl --material PLA

# 3. Review the time/grams estimate and thumbnail, then upload (does NOT print)
python scripts/octoprint.py upload <gcode> --print-id <N>

# 4. Start the print — requires --yes and your confirmation
python scripts/octoprint.py start <remote_name> --yes --print-id <N>

# 5. Monitor / cancel
python scripts/octoprint.py status
python scripts/octoprint.py cancel --print-id <N>
```

Text-to-3D (the agent authors the OpenSCAD; the script compiles and previews it):

```bash
python scripts/describe.py --name bracket --code '<openscad source>'
```

## Talking to the agent

The skill is driven by natural language. Representative requests and what each triggers:

| You say | The agent does |
|---------|----------------|
| "Print this STL on my Tina 2S." | Ingest → prepare → slice → preview → asks you to confirm → upload → print |
| "Slice this but don't print yet." | Stops after slicing and shows the estimate + thumbnail |
| "Make a 30mm cube with a 10mm hole and show me." | Authors OpenSCAD, compiles, returns a preview PNG |
| "Yes, go ahead and print it." | Runs the gated start (the only step that begins a physical print) |
| "Use PETG instead." | Re-slices with the PETG profile and warns about the marginal bed |
| "This came out stringy / the corners lifted." (with a photo) | Reviews the image, records the outcome, and stores a lesson that adjusts future slices |
| "Cancel the print." | Cancels the active job |
| "Switch to my other printer." | Changes the active printer (see below) |

The agent will not start a print without an explicit instruction to do so.

## Switching printers

```bash
python scripts/printers.py list                  # show registered printers
python scripts/printers.py add ender3 \
    --bed-x 220 --bed-y 220 --bed-z 250 --nozzle-max-c 260 --bed-max-c 110 \
    --materials PLA,PETG,ABS                      # register a new printer
python scripts/printers.py switch ender3         # make it the default
python scripts/printers.py retire tina2s         # mark a printer retired
python scripts/printers.py show ender3           # inspect one printer
```

`prepare`, `slice`, and the OctoPrint commands accept `--printer <name>`; without it they use
the active default. Lessons learned are scoped per printer + material, so adjustments do not
leak between machines. Note that profiles in `profiles/` are tuned for the Tina 2S; add
profiles for other printers as needed.

## Evaluation

A test harness drives the full pipeline and grades the skill against slice-quality and
skill-authoring criteria, producing a self-contained HTML report and JSON data:

```bash
python eval/evaluate.py
# writes eval/report.html (open on any device) and eval/results.json
```

The report covers a functional suite (does the pipeline work end to end?) and a quality suite
(frontmatter, description, progressive disclosure, working references).

## Safety

- Prints never start automatically. `octoprint.py start` requires `--yes` in addition to an
  explicit user instruction. Slicing, previewing, and uploading are safe and reversible;
  starting a print is the only physical, hard-to-reverse action and is gated accordingly.
- API keys live in environment variables. The database, downloads, and generated G-code live
  under `~/.3dprint/`, outside the repository. Nothing sensitive is committed.
- Tweaker-3 (GPL-3.0) is fetched at runtime and invoked as a subprocess, never redistributed
  in this repository.

## Repository layout

| Path | Purpose |
|------|---------|
| `SKILL.md` | Agent entry point: when to use the skill and how the pipeline fits together |
| `scripts/` | `setup`, `printers`, `ingest`, `prepare`, `slice`, `describe`, `octoprint`, `jobs`, `review` |
| `profiles/` | PrusaSlicer configuration bundles (PLA, PETG) |
| `references/` | Adjustment-rule definitions and slicing rationale |
| `eval/` | Evaluation harness and generated reports |
| `PLAN.md`, `PROGRESS.md` | Build plan and checkpoint history |

## License

MIT — see [LICENSE](LICENSE). Tweaker-3 is GPL-3.0 and is fetched separately at runtime
rather than redistributed here.

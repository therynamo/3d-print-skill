# 3d-print-skill

**Hand a model to your AI agent and get a real print off your printer — without babysitting the slicer.**

This is a [Claude skill](https://docs.anthropic.com/en/docs/claude-code/skills) that takes
*anything printable* — an STL, 3MF, OBJ, an OpenSCAD file, a link to one, or even a
plain-English description of the thing you want — and walks it all the way to a finished
print on your [OctoPrint](https://octoprint.org/)-connected machine. It orients the model,
scales it to your bed, slices it, decides when a print actually needs supports or a brim
(and tells you *why*), shows you a preview, and waits for your go-ahead before anything
touches the hotend. Afterward, you send it a photo of the result and it learns from how the
print turned out.

It was built and dialed in for a **WEEFUN Tina 2S**, but the printer registry means you can
point it at whatever you own.

---

## Why this exists

Slicing is the part of 3D printing where all the fiddly judgment lives. *Does this overhang
need support? Will this tall skinny thing tip over without a brim? Is my bed hot enough for
PETG?* Most tools make you answer those questions by hand, every time, and they don't
remember what went wrong last week.

This skill **codifies that judgment** ([see the rules](references/adjustment-rules.md)),
explains every decision in plain language, and closes the loop: when a print fails, you
teach it once and it adjusts automatically forever after. It's the difference between a
slicer and a printing assistant that actually pays attention.

It's also deliberately **safe by default** — an agent driving a hot, moving machine should
never start a print on its own. So it doesn't. Ever. (More on that below.)

---

## The flow

```
ingest → prepare → slice → preview → ✋ you confirm → upload → print → review → it learns
```

A typical session looks like this:

```bash
# Got an STL? Point at it.
python scripts/ingest.py cool-thing.stl
python scripts/prepare.py ~/.3dprint/work/cool-thing.stl       # orient + fit + thumbnail
python scripts/slice.py  ~/.3dprint/work/cool-thing_prepared.stl --material PLA

# Look at the time/grams estimate and the thumbnail. Happy? Then:
python scripts/octoprint.py upload <gcode> --print-id 12       # stages it — does NOT print
python scripts/octoprint.py start  <remote> --yes --print-id 12  # prints, only after you say so
python scripts/octoprint.py status                              # check on it
```

Don't have a model yet? Describe it and let the agent write the OpenSCAD:

```bash
python scripts/describe.py --name phone-stand \
  --code 'difference(){ cube([70,80,4]); /* ...the agent fills this in... */ }'
# -> compiles to STL + renders a preview PNG you can eyeball before committing to plastic
```

## The part that makes it smart

When a print comes out wrong, tell it what you saw:

```bash
python scripts/review.py record 12 --rating 2 --notes "corners lifted" --images corner.jpg
python scripts/review.py learn  12 --trigger "first-layer lifting" --adjustment "brim_width=6"
```

From then on, every PLA print on that printer gets the wider brim automatically — until a
newer lesson says otherwise. The adjustments are scoped per printer + material, so a fix for
your Tina 2S doesn't leak onto a future Bambu.

---

## Setup

You'll need macOS (Apple Silicon is fine), Python 3.12+, and a few tools:

```bash
brew install --cask prusaslicer
brew install --cask openscad@snapshot   # the 2021.01 cask is Intel-only and won't run on M-series

git clone <this repo> ~/dev/3d-print-skill
cd ~/dev/3d-print-skill
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt

python scripts/setup.py --seed --fetch-tweaker    # health check + seed your printer + grab auto-orient
ln -s "$PWD" ~/.claude/skills/3d-print             # make it available as a Claude skill
```

`setup.py` is a friendly doctor — run it any time and it'll tell you exactly what's missing
and how to fix it. For OctoPrint, drop your credentials in your shell profile (never in the
repo):

```bash
export OCTOPRINT_URL="http://octopi.local"   # or the Pi's IP if .local won't resolve
export OCTOPRINT_API_KEY="your-key-here"
```

> **Tip:** if `octopi.local` doesn't resolve for the Python tools, use the Pi's IP and give
> it a DHCP reservation so it never changes on you.

---

## A note on the Tina 2S

It's a charming little printer (100 × 105 × 100 mm, 0.4 mm nozzle) with one real constraint:
**the bed maxes out at 60 °C.** PLA is happy there. PETG technically prints, but it wants a
70–80 °C bed for adhesion — so the PETG profile pins the bed at 60, forces a brim, and the
skill will remind you to lay down a glue stick. Treat PETG as "works, with care," not
"works, ignore it."

---

## Safety, plainly

- **Nothing prints without you.** `octoprint.py start` flat-out refuses unless you pass
  `--yes`, and the skill is instructed to get your explicit confirmation first. Slicing,
  previewing, and uploading are all safe and reversible; starting a print is the one
  physical, hard-to-undo step, so it's gated.
- **Your secrets stay yours.** API keys live in environment variables. The database,
  downloads, and generated G-code live in `~/.3dprint/`, outside the repo. Nothing sensitive
  is ever committed.
- **No GPL in the box.** [Tweaker-3](https://github.com/ChristophSchranz/Tweaker-3) (the
  auto-orient engine, GPL-3.0) is fetched at setup and invoked as a separate program, not
  bundled — so this repo stays cleanly MIT.

---

## What's in here

| Path | What it does |
|------|--------------|
| `SKILL.md` | The agent's entry point — when to use it and how the pipeline fits together |
| `scripts/` | `setup`, `printers`, `ingest`, `prepare`, `slice`, `describe`, `octoprint`, `jobs`, `review` |
| `profiles/` | Self-contained PrusaSlicer configs (PLA, PETG) — tweak these to retune your defaults |
| `references/` | The adjustment-rule definitions, including the overhang math |
| `eval/` | A test harness that drives the whole pipeline and grades the skill; outputs an HTML report |
| `PLAN.md` / `PROGRESS.md` | How it was built and where each checkpoint landed |

Want to verify everything works on your machine? Run the evaluation:

```bash
python eval/evaluate.py    # writes eval/report.html — open it on your phone
```

---

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, point it at your own printer. Tweaker-3 is
GPL-3.0 and is fetched separately at runtime rather than redistributed here.

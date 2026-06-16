# Codified slicing adjustment rules

`slice.py` starts from a material profile (`profiles/tina2s_<material>.ini`) and then
applies the rules below as **overrides**, so most prints work with the default while
the agent only changes what the geometry or prior experience demands. Every override is
recorded in `prints.adjustments_json` with the rule name and the value that triggered it,
so a human can audit *why* a setting changed.

Order of precedence (last wins):
1. Material profile defaults (the `.ini`).
2. Codified geometric rules (this file).
3. Lessons learned from past prints (`lessons` table, matched by printer + material).
4. Explicit user overrides passed on the command line (`--set key=value`).

## Geometric measurements

Computed from the prepared, bed-resting STL with trimesh:

- **extents** `(x, y, z)` mm — bounding box after orient + scale-to-fit.
- **height** = `z`.
- **min_footprint** = `min(x, y)` — narrowest base dimension.
- **aspect** = `height / min_footprint` — tall-and-tippy indicator.
- **overhang severity** per downward-facing triangle (`normal.z < 0`):
  `severity = degrees(asin(-normal.z))`, so **0° = vertical wall** (safe) and
  **90° = flat horizontal ceiling** (worst). Each triangle is weighted by its area.
  - `max_overhang` = highest severity over any face with non-trivial area.
  - `severe_overhang_area_cm2` = total area of faces with severity > 50°.

## Rules

### R1 — Supports for steep overhangs
- **Trigger:** `max_overhang > 50°` **and** `severe_overhang_area_cm2 >= 1.0`.
  (The area gate avoids enabling supports for tiny chamfers/lettering.)
- **Action:** `support_material = 1`. The profile's `support_material_threshold`
  (40° PLA / 45° PETG, measured 90°=vertical) then decides which faces get support.
- **Why:** unsupported material shallower than ~40° from horizontal sags. PrusaSlicer
  also independently emits a "Consider enabling supports" stability warning; if that
  warning fires we enable supports even when the area gate is borderline.
- **Explanation surfaced to user:** e.g. *"Enabled supports: detected a 78° overhang over
  4.2 cm² — it would sag without them."*

### R2 — Brim for tall / tippy parts
- **Trigger:** `aspect > 4` (tall and narrow).
- **Action:** `brim_width = max(profile, 5)`.
- **Why:** small footprint + tall body = high tip-over / detachment risk; a brim widens
  the effective base.

### R3 — Brim for tiny footprints
- **Trigger:** `min_footprint < 10 mm`.
- **Action:** `brim_width = max(profile, 4)`.
- **Why:** very small first-layer contact area peels easily; brim adds grip.

### Bed target must stay below the bed's max
- The Tina 2S bed maxes at 60 °C. `M190 S<target>` in the start G-code **blocks until
  the bed reaches the target**. If the target equals the bed's ceiling, the bed
  asymptotes just below it and never satisfies `M190` — the print hangs in the start
  block forever (nozzle parked hot, 0% progress). Real failure seen on the first test
  print. Profiles therefore target **55 °C (PLA)** and **58 °C (PETG)**, comfortably
  reachable. Keep first-layer + steady bed targets at or below ~58 for this printer.

### The Tina 2S must auto-level (G29) every print
- The start G-code MUST run `G29` (auto bed leveling) after homing, or the first layer
  rides too high and will not adhere (skirt barely deposited, filament balls up on the
  nozzle — seen on the second test print). `M203 Z15`/`Z5` cap the Tina 2S's slow Z
  feedrate (fast for homing/leveling, slow for printing); the nozzle is pre-warmed to
  150 °C during leveling to avoid ooze, then brought to full temp afterward. This start
  sequence is ported from Cura's authoritative `weefun_tina2s` machine definition.

### R4 — PETG adhesion (out-of-spec bed)
- **Trigger:** `material == PETG` (always, on the Tina 2S).
- **Action:** profile already forces `brim_width = 5`; the agent additionally **warns the
  user** that the 60°C bed ceiling makes PETG marginal — clean plate + glue stick advised.
- **Why:** Tina 2S bed maxes at 60°C; PETG wants 70-80°C. Adhesion is the failure mode.

### R5 — Extra top layers for wide flat tops *(future / not yet auto-applied)*
- Large flat top surfaces can pillow with too few solid layers. Documented for a later
  pass; not auto-applied to avoid over-tuning.

## Lessons feedback (R-L)
After an outcome review, `review.py` may insert a row into `lessons` (printer + material +
trigger + learned_adjustment). On the next slice for the same printer/material, those
adjustments are layered on top of the geometric rules. Example: if a PLA print on `tina2s`
repeatedly shows first-layer lifting, a lesson can raise `brim_width` or
`first_layer_bed_temperature` for that printer going forward.

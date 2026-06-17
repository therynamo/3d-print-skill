# Photo → 3D model intake & build

How to turn a user's photo(s) of a real object into an accurately-dimensioned,
printable model. The agent (multimodal) reads the photos to recover *shape*; the
**user's measurements** supply *scale and fit*. Photos alone never give reliable
dimensions — perspective, lens distortion, and unknown camera distance make
pixel-measuring guesswork. Always pair images with at least one real measurement.

This skill prints on an FDM machine and authors geometry as parametric OpenSCAD
(see `describe.py`). So the target is a clean parametric solid driven by named
dimension variables, not a photogrammetry mesh. That keeps the model editable,
watertight, and trivially re-scaled when a measurement is corrected.

## What this flow is good at / not good at
- **Good:** functional parts with describable geometry — brackets, mounts, clips,
  spacers, enclosures, replacement knobs/feet, adapters, organizers. Anything you
  can decompose into prisms, cylinders, fillets, holes, and boolean cuts.
- **Poor:** organic/sculptural shapes (faces, figurines, complex curves). Those want
  photogrammetry or AI image-to-mesh tools, which this skill does not run. Say so and
  offer the parametric approximation instead.
- **Lithophanes** (photo → relief plaque) are a separate, well-trodden path; mention
  it only if the user actually wants a picture-in-relief, not a physical replica.

## Capture protocol (what to ask the user to photograph)
Distilled from the reference-scale / multi-view guidance below. Ask for:

1. **Multiple orthogonal views** — straight-on **front, side, and top** at minimum;
   add a 3/4 angled shot to disambiguate depth. 3–4 photos beats one. Each face you
   can't see is a face you have to guess.
2. **Camera parallel to the face** being shot (sensor plane parallel to the object
   face). Shooting at an angle injects perspective distortion that warps proportions.
3. **A reference object of known size in the same plane** as the object (next to it,
   same distance from camera): a ruler/tape is best; a coin or a credit card
   (85.6 × 53.98 mm) works. Bigger reference = smaller relative error. This lets the
   agent sanity-check the user's stated measurements and infer ones they didn't give.
4. **Even, neutral lighting** and a **plain, contrasting background** so edges read
   clearly. Avoid harsh shadows that hide features.
5. **High resolution, in focus.** More real detail = better shape recovery. No tiny
   thumbnails or heavy compression.

## Measurement protocol (what to ask the user to measure)
Calipers are ideal (0.1 mm); a steel ruler is fine for larger parts. Gather:

- **Overall bounding box**: length × width × height. This is the non-negotiable one.
- **Every fit-critical feature**: hole diameters, shaft/post diameters, slot widths,
  wall thickness, bolt-hole spacing (center-to-center), lip/flange depths. For each,
  ask *what it mates with* — that determines tolerance.
- **Reference dimension** you can also see in the photo, so shape and scale agree.

Ask the user to call out which dimensions are **load-bearing for fit** vs. merely
cosmetic, so effort and tolerance go where they matter.

## Tolerances & FDM realities (apply when authoring)
- **Clearance fits**: add **~0.2 mm per side** (0.4 mm on a diameter) where the part
  must slide into/over an existing object. Tight/press fit: ~0.1 mm. Loose: ~0.3 mm.
  Tina 2S + PLA tends to print holes slightly undersize — err toward more clearance
  and let the user confirm on a test fit.
- **Minimum wall** ~2–3 perimeters (≈0.8–1.2 mm at 0.4 mm nozzle); thinner won't be
  solid. **Minimum feature** ≈ nozzle width.
- **Draft / overhangs**: unsupported overhangs past ~50° need supports (the slicer
  rules handle this) — but prefer orienting so fit surfaces print cleanly.
- **Shrinkage**: PLA ~0.2–0.3%; negligible for most parts, relevant for tight fits.
- Keep one **named OpenSCAD variable per measured dimension** at the top of the file,
  so a corrected measurement is a one-line edit and re-slice.

## Validation loop
After building, deliver the **reference photo and the rendered preview together** so
the user can eyeball shape fidelity against the real object. Confirm the overall
dimensions in the preview match what they measured before slicing. Iterate on the
parametric variables — not a remodel — when something's off. Only then prepare →
slice → confirm → print.

## Sources
- Prusa, "From 2D to 3D: how to turn a picture or a photo into a 3D model"
- chanhontech, "How to make negatives from 2D shapes and 3D scans for 3D printing"
- ImageMeter reference-scale manual; general multi-view / photogrammetry-lite guidance
- Meshy / 3dmyphoto image-to-3D capture guidance (AI mesh path, not used here)

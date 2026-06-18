#!/usr/bin/env python3
"""Photo -> 3D model: build an accurately-dimensioned printable part from a user's
photos of a real object, plus the measurements they take.

Photos recover *shape* (the agent is multimodal and reads them directly); the user's
measurements supply *scale and fit*. Pixels alone never give reliable dimensions, so
this flow always pairs images with real measurements. The agent then authors
parametric OpenSCAD dimensioned to those measurements -- this just compiles/previews
it (reusing describe.py) and bundles the reference photos + spec so the user can
validate the render against the real object. See references/photo-to-model.md.

  python scripts/from_photo.py analyze --refs a.jpg,b.jpg [--task fit]
                                                            # diagnose what the photos give vs. need
  python scripts/from_photo.py intake                       # print the capture/measure checklist
  python scripts/from_photo.py build --name knob \
      --code '<openscad>' --refs front.jpg,side.jpg \
      --measure overall_h=24 --measure shaft_d=6.2          # build + bundle refs/spec
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import common
import describe

# What a usable photo set must cover, per kind of job, and how to capture each.
# `analyze` reports the user's images against the chosen profile; the agent (which
# actually sees the images) maps each photo to the requirements it satisfies.
CAPTURE_PROFILES = {
    "fit": {
        "blurb": "A part that must mate with an existing object (cover, bracket, "
                 "adapter). Fit tolerance is unforgiving, so capture is strict.",
        "requirements": [
            ("true_outline",
             "The exact 2D outline of the opening / mating face",
             ["Lay paper over the opening, press/crease it into the real edge (or "
              "trace the edge with a pen held vertical), then photograph that FLAT "
              "tracing straight-down with a ruler beside it. This turns a curved 3D "
              "edge into a scaled 2D shape with no perspective error.",
              "Alternative: shoot the opening dead-overhead, lens parallel to the "
              "opening plane, with a ruler lying in that same plane."]),
            ("bounding_box",
             "Overall length x width of the opening",
             ["Calipers/ruler across the two widest spans; capture the digital "
              "readout (or ruler ticks) in the same frame as the span."]),
            ("depth",
             "Recess depth, rim down to the floor",
             ["Stand a ruler vertically in the opening touching the rim and shoot "
              "DEAD-LEVEL from the side, so the rim edge reads against the scale."]),
            ("rim_profile",
             "Cross-section of the rim the cover grips: wall angle, lip, groove",
             ["Press putty/modelling clay/foil onto a short section of the rim, peel "
              "it off, slice it, and photograph the cut face next to a ruler.",
              "Or a close, level shot of an exposed edge/corner if one is accessible."]),
            ("mating_features",
             "Tabs, slots, posts, screw bosses in or around the opening",
             ["Caliper each feature and its center-to-center spacing; one close, "
              "square-on photo per feature with the readout in frame."]),
            ("reference_scale",
             "A known-size object in the SAME plane as the subject, for scale",
             ["Include a ruler (best), a coin, or a credit card (85.6 x 53.98 mm) "
              "lying in the subject's plane, with the lens parallel to that plane."]),
        ],
    },
    "replica": {
        "blurb": "Reproduce an object's shape/appearance (no mating constraint).",
        "requirements": [
            ("ortho_front", "Straight-on FRONT view (lens parallel to the face)",
             ["Square-on, centered, fills the frame, plain background."]),
            ("ortho_side", "Straight-on SIDE view", ["Square-on at 90 deg to front."]),
            ("ortho_top", "Straight-on TOP view", ["Directly overhead."]),
            ("three_quarter", "A 3/4 angled view to disambiguate depth",
             ["One corner-on shot so concave/convex reads correctly."]),
            ("key_dims", "Overall bounding box + any feature dimensions that matter",
             ["Calipers/ruler; capture readouts in frame."]),
            ("reference_scale", "A known-size object in-plane for scale",
             ["Ruler / coin / credit card beside the object, lens parallel."]),
        ],
    },
    "lithophane": {
        "blurb": "Photo -> backlit relief plaque (a different pipeline, not a replica).",
        "requirements": [
            ("source_image", "One high-resolution, high-contrast image",
             ["No measurements needed; resolution and tonal range drive quality."]),
        ],
    },
}

CHECKLIST = """\
PHOTO -> 3D MODEL INTAKE  (ask the user for these before modeling)

Photos -- shape comes from these:
  * Front, side, and top, shot straight-on (camera parallel to each face).
  * Add a 3/4 angled shot to pin down depth. 3-4 photos beats 1.
  * Put a known-size reference in frame, same plane as the object:
    a ruler is best; a coin or credit card (85.6 x 53.98 mm) also works.
  * Even lighting, plain contrasting background, in focus, high resolution.

Measurements -- scale & fit come from these (calipers ideal, ruler ok):
  * Overall bounding box: length x width x height  (REQUIRED).
  * Every fit-critical feature: hole/shaft diameters, slot widths, wall
    thickness, bolt-hole spacing (center-to-center), lip/flange depths.
  * For each fit feature, ask WHAT IT MATES WITH -> sets the tolerance.
  * Flag which dims are load-bearing for fit vs. merely cosmetic.

Tolerances when modeling (FDM / PLA on the Tina 2S):
  * Slide/clearance fit: +~0.2 mm per side (~0.4 mm on a diameter).
  * Press fit ~0.1 mm; loose ~0.3 mm. Holes tend to print undersize.
  * Min wall ~0.8-1.2 mm; min feature ~= nozzle width (0.4 mm).

Then: author parametric OpenSCAD with one named variable per measured
dimension, `build` it, and deliver the reference photo + render together
so the user can confirm shape and size before slicing.
"""


_ORIENT = {1: "normal", 3: "rotated 180", 6: "rotated 90 CW", 8: "rotated 90 CCW"}


def image_facts(path: str) -> dict:
    """Machine-extractable quality facts for one image (what a tool can know without
    'seeing' content): resolution, EXIF orientation/camera, focus score, brightness."""
    from PIL import Image  # Pillow; added to requirements for this feature
    import numpy as np

    f: dict = {"path": path, "name": Path(path).name}
    try:
        im = Image.open(path)
    except Exception as e:
        f["error"] = f"unreadable: {e}"
        return f
    w, h = im.size
    f["resolution"] = f"{w}x{h}"
    f["megapixels"] = round(w * h / 1e6, 1)
    exif = im.getexif()
    f["orientation"] = _ORIENT.get(exif.get(274), "unknown")
    f["camera"] = exif.get(272) or exif.get(271)  # Model / Make; often stripped
    f["focal_mm"] = exif.get(37386)

    g = np.asarray(im.convert("L"), dtype=np.float64)
    step = max(1, int(max(g.shape) / 1000))   # downscale for speed
    g = g[::step, ::step]
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
           + g[1:-1, :-2] + g[1:-1, 2:])       # discrete Laplacian
    f["focus_score"] = round(float(lap.var()), 1)
    f["brightness"] = round(float(g.mean() / 255), 2)

    flags = []
    if f["megapixels"] < 2:
        flags.append("low-resolution")
    if f["focus_score"] < 80:
        flags.append("soft/possibly-blurry")
    if f["brightness"] < 0.22:
        flags.append("dark")
    elif f["brightness"] > 0.92:
        flags.append("over-exposed")
    f["flags"] = flags
    return f


def analyze(refs: list[str], task: str) -> dict:
    """Report what the supplied images provide vs. what the job needs, and the
    capture method for each requirement. The agent fills coverage by inspecting the
    images; this gives consistent facts + the requirement/method catalog every time."""
    profile = CAPTURE_PROFILES[task]
    facts = [image_facts(r) for r in refs]
    return {
        "task": task,
        "task_blurb": profile["blurb"],
        "image_count": len(refs),
        "images": facts,
        "requirements": [
            {"key": k, "need": need, "methods": methods}
            for (k, need, methods) in profile["requirements"]
        ],
    }


def _print_analysis(a: dict) -> None:
    print(f"PHOTO SET ANALYSIS  (task: {a['task']} -- {a['task_blurb']})")
    print(f"\nWHAT YOU PROVIDED  ({a['image_count']} image(s)):")
    any_cam = False
    for im in a["images"]:
        if "error" in im:
            print(f"  - {im['name']}: {im['error']}")
            continue
        any_cam = any_cam or bool(im["camera"])
        flag = f"  [{', '.join(im['flags'])}]" if im["flags"] else ""
        print(f"  - {im['name']}: {im['resolution']} ({im['megapixels']} MP), "
              f"{im['orientation']}, focus={im['focus_score']}, "
              f"brightness={im['brightness']}{flag}")
    if not any_cam:
        print("  (EXIF camera/focal data stripped -> cannot infer shot distance/angle;"
              " judge view & on-axis-ness visually.)")
    print("\nFocus score is relative across the set; higher = sharper. Soft frames are"
          " unreliable for reading scales or fine features.")

    print("\nWHAT THE JOB NEEDS  (confirm each against the images above):")
    for r in a["requirements"]:
        print(f"  [ ] {r['key']}: {r['need']}")

    print("\nHOW TO CAPTURE WHAT'S MISSING:")
    for r in a["requirements"]:
        print(f"  * {r['key']}:")
        for m in r["methods"]:
            print(f"      - {m}")
    print("\nNext: for each requirement, state which image satisfies it (or mark it"
          " MISSING) and ask the user only for the gaps, citing the method above.")


def _parse_measures(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"--measure expects key=value, got {p!r}")
        k, _, v = p.partition("=")
        out[k.strip()] = v.strip()
    return out


def build(name: str, scad_src: str, refs: list[str], measures: dict) -> dict:
    """Compile the OpenSCAD, stash reference photos + measurement spec alongside,
    and return paths to deliver (reference photos first, then the render)."""
    result = describe.compile_scad(scad_src, name)

    saved_refs: list[str] = []
    if refs:
        ref_dir = common.WORK_DIR / f"{name}_refs"
        ref_dir.mkdir(parents=True, exist_ok=True)
        for r in refs:
            src = Path(r).expanduser()
            if not src.exists():
                raise FileNotFoundError(f"reference image not found: {r}")
            dest = ref_dir / src.name
            shutil.copy2(src, dest)
            saved_refs.append(str(dest))

    spec = {"name": name, "measurements": measures, "references": saved_refs,
            "dimensions_mm": result["dimensions_mm"]}
    spec_path = common.WORK_DIR / f"{name}_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))

    result["references"] = saved_refs
    result["spec_path"] = str(spec_path)
    result["measurements"] = measures
    # Deliver reference photos alongside the render so the user can compare.
    result["deliver"] = saved_refs + result.get("deliver", [])
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Photo -> dimensioned 3D model")
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze", help="diagnose a photo set vs. what the job needs")
    an.add_argument("--refs", default="", help="comma-separated image paths")
    an.add_argument("--task", default="fit", choices=sorted(CAPTURE_PROFILES),
                    help="job type: fit (mating part) | replica | lithophane")
    an.add_argument("--json", action="store_true")
    sub.add_parser("intake", help="print the photo + measurement checklist")
    b = sub.add_parser("build", help="compile OpenSCAD + bundle reference photos/spec")
    src = b.add_mutually_exclusive_group()
    src.add_argument("--code", help="inline OpenSCAD source")
    src.add_argument("--scad", help="path to a .scad file")
    b.add_argument("--name", default="from_photo", help="base name for outputs")
    b.add_argument("--refs", default="", help="comma-separated reference image paths")
    b.add_argument("--measure", action="append", default=[],
                   help="key=value measurement (repeatable), e.g. --measure shaft_d=6.2")
    b.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        refs = [r.strip() for r in args.refs.split(",") if r.strip()]
        if not refs:
            print("analyze needs --refs img1,img2,...", file=sys.stderr)
            return 2
        try:
            a = analyze(refs, args.task)
        except Exception as e:
            print(f"from_photo analyze error: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(a, indent=2))
        else:
            _print_analysis(a)
        return 0

    if args.cmd == "intake":
        print(CHECKLIST)
        return 0

    if args.code:
        scad_src = args.code
    elif args.scad:
        scad_src = Path(args.scad).expanduser().read_text()
    else:
        scad_src = sys.stdin.read()
    if not scad_src.strip():
        print("no OpenSCAD source provided (use --code, --scad, or stdin)",
              file=sys.stderr)
        return 2

    refs = [r.strip() for r in args.refs.split(",") if r.strip()]
    try:
        measures = _parse_measures(args.measure)
        r = build(args.name, scad_src, refs, measures)
    except Exception as e:
        print(f"from_photo error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        d = r["dimensions_mm"]
        print(f"compiled: {r['stl_path']}")
        print(f"dimensions: {d[0]} x {d[1]} x {d[2]} mm")
        if r["measurements"]:
            print("measured spec:")
            for k, v in r["measurements"].items():
                print(f"  {k} = {v}")
            print("  ^ compare these against the dimensions above before slicing.")
        if r["references"]:
            print(f"references: {len(r['references'])} photo(s) bundled")
        if r["deliver"]:
            print(f"deliver_to_user: {' '.join(r['deliver'])}")
        print("Next: send deliver_to_user file(s) -- show the reference photo next to "
              "the render so the user can confirm shape + size, then prepare.py + slice.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

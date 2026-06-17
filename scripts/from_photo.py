#!/usr/bin/env python3
"""Photo -> 3D model: build an accurately-dimensioned printable part from a user's
photos of a real object, plus the measurements they take.

Photos recover *shape* (the agent is multimodal and reads them directly); the user's
measurements supply *scale and fit*. Pixels alone never give reliable dimensions, so
this flow always pairs images with real measurements. The agent then authors
parametric OpenSCAD dimensioned to those measurements -- this just compiles/previews
it (reusing describe.py) and bundles the reference photos + spec so the user can
validate the render against the real object. See references/photo-to-model.md.

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

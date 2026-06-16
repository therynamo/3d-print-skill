#!/usr/bin/env python3
"""Text-to-3D preview harness: OpenSCAD source -> STL -> PNG preview.

The LLM agent authors the OpenSCAD code from the user's natural-language description
(parametric, units in mm) and passes it here. This script compiles it, renders a
preview the user can eyeball, and returns paths ready for prepare.py / slice.py.
Nothing is printed -- this is the "describe -> preview -> decide" loop.

  python scripts/describe.py --code 'cube([20,20,20]);' --name widget
  python scripts/describe.py --scad model.scad
  echo 'sphere(r=10);' | python scripts/describe.py --name ball
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import common


def compile_scad(scad_src: str, name: str) -> dict:
    scad_bin = common.openscad_bin()
    if not scad_bin:
        raise RuntimeError("OpenSCAD not found -> brew install --cask openscad@snapshot")
    common.ensure_dirs()
    scad_path = common.WORK_DIR / f"{name}.scad"
    stl_path = common.WORK_DIR / f"{name}.stl"
    png_path = common.WORK_DIR / f"{name}_preview.png"
    scad_path.write_text(scad_src)

    proc = subprocess.run([scad_bin, "-o", str(stl_path), str(scad_path)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not stl_path.exists():
        raise RuntimeError(f"OpenSCAD compile failed:\n{proc.stderr.strip()[-500:]}")

    common.render_stl_png(str(stl_path), str(png_path))

    import trimesh
    ext = [round(float(v), 2) for v in trimesh.load(str(stl_path), force="mesh").extents]
    return {
        "name": name,
        "scad_path": str(scad_path),
        "stl_path": str(stl_path),
        "preview_png": str(png_path),
        "dimensions_mm": ext,
        "deliver": common.deliver_files(str(stl_path), str(png_path)),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OpenSCAD text-to-3D preview")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--code", help="inline OpenSCAD source")
    src.add_argument("--scad", help="path to a .scad file")
    ap.add_argument("--name", default="described", help="base name for outputs")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

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

    try:
        r = compile_scad(scad_src, args.name)
    except Exception as e:
        print(f"describe error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        d = r["dimensions_mm"]
        print(f"compiled: {r['stl_path']}")
        print(f"dimensions: {d[0]} x {d[1]} x {d[2]} mm")
        print(f"preview: {r['preview_png']}")
        if r["deliver"]:
            print(f"deliver_to_user: {' '.join(r['deliver'])}")
        print("Next: send deliver_to_user file(s) to the user (STL orbits in macOS "
              "Preview), then prepare.py + slice.py if you like it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

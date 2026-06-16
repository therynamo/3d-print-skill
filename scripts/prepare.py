#!/usr/bin/env python3
"""Prepare a model for slicing on a specific printer.

Steps: (compile .scad if needed) -> auto-orient (Tweaker-3) -> measure bbox ->
auto scale-to-fit the bed -> export normalized STL -> render a PNG thumbnail.

  python scripts/prepare.py <model.stl|.3mf|.obj|.scad> [--printer NAME] [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import common

MARGIN_MM = 1.0  # clearance kept on each side of the bed


def _compile_scad(scad_path: Path, out_stl: Path) -> Path:
    scad = common.openscad_bin()
    if not scad:
        raise RuntimeError("OpenSCAD not found; cannot compile .scad")
    subprocess.run([scad, "-o", str(out_stl), str(scad_path)],
                   check=True, capture_output=True, text=True)
    return out_stl


def _to_stl(model_path: Path, out_stl: Path) -> Path:
    """Ensure we have an STL (convert 3mf/obj via trimesh, compile scad)."""
    ext = model_path.suffix.lower()
    if ext == ".stl":
        return model_path
    if ext == ".scad":
        return _compile_scad(model_path, out_stl)
    import trimesh
    mesh = trimesh.load(str(model_path), force="mesh")
    mesh.export(str(out_stl))
    return out_stl


def _auto_orient(stl_in: Path, stl_out: Path) -> bool:
    """Run Tweaker-3 to minimize support. Returns True if it produced output."""
    script = common.tweaker_script()
    if not script:
        return False
    try:
        subprocess.run(
            [sys.executable, script, "-i", str(stl_in), "-o", str(stl_out),
             "-min", "sur", "-t", "binarystl"],
            check=True, capture_output=True, text=True, cwd=str(Path(script).parent),
        )
        return stl_out.exists()
    except subprocess.CalledProcessError as e:
        print(f"  (auto-orient skipped: {e.stderr.strip()[:120]})", file=sys.stderr)
        return False


def prepare(model_path: str, printer_name: str | None = None) -> dict:
    import trimesh

    common.ensure_dirs()
    src = Path(model_path).expanduser().resolve()
    stem = src.stem

    conn = common.connect()
    common.init_db(conn)
    printer = (common.get_printer_by_name(conn, printer_name) if printer_name
               else common.get_active_printer(conn))
    if not printer:
        raise RuntimeError("No printer configured. Run: printers.py seed")
    bed = (printer["bed_x"], printer["bed_y"], printer["bed_z"])

    # 1. normalize to STL
    base_stl = common.WORK_DIR / f"{stem}.stl"
    base_stl = _to_stl(src, base_stl)

    # 2. auto-orient
    oriented = common.WORK_DIR / f"{stem}_oriented.stl"
    did_orient = _auto_orient(base_stl, oriented)
    work_stl = oriented if did_orient else base_stl

    # 3. measure
    mesh = trimesh.load(str(work_stl), force="mesh")
    ext = [float(v) for v in mesh.extents]  # x, y, z

    # 4. scale-to-fit (uniform)
    usable = [b - 2 * MARGIN_MM for b in bed]
    ratios = [u / e for u, e in zip(usable, ext) if e > 0]
    factor = min(ratios) if ratios else 1.0
    scaled = False
    if factor < 1.0:
        mesh.apply_scale(factor)
        ext = [float(v) for v in mesh.extents]
        scaled = True
    else:
        factor = 1.0

    # 5. export normalized model
    final_stl = common.WORK_DIR / f"{stem}_prepared.stl"
    mesh.export(str(final_stl))

    # 6. thumbnail
    thumb = common.WORK_DIR / f"{stem}_thumb.png"
    try:
        common.render_stl_png(str(final_stl), str(thumb))
        thumb_path = str(thumb)
    except Exception as e:
        print(f"  (thumbnail skipped: {e})", file=sys.stderr)
        thumb_path = None

    fits = all(e <= u for e, u in zip(ext, usable))
    return {
        "printer": printer["name"],
        "bed": list(bed),
        "prepared_stl": str(final_stl),
        "thumbnail": thumb_path,
        "dimensions_mm": [round(v, 2) for v in ext],
        "auto_oriented": did_orient,
        "scaled_to_fit": scaled,
        "scale_factor": round(factor, 4),
        "fits_bed": fits,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prepare a model for slicing")
    ap.add_argument("model")
    ap.add_argument("--printer", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = prepare(args.model, args.printer)
    except Exception as e:
        print(f"prepare error: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        d = r["dimensions_mm"]
        print(f"printer: {r['printer']}  bed: {r['bed']}")
        print(f"dimensions: {d[0]} x {d[1]} x {d[2]} mm  fits={r['fits_bed']}")
        print(f"auto-oriented: {r['auto_oriented']}  scaled: {r['scaled_to_fit']} "
              f"(x{r['scale_factor']})")
        print(f"prepared: {r['prepared_stl']}")
        if r["thumbnail"]:
            print(f"thumbnail: {r['thumbnail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

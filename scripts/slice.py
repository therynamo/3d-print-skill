#!/usr/bin/env python3
"""Slice a prepared model with PrusaSlicer, applying codified adjustment rules.

Pipeline: load the material profile -> measure geometry -> derive setting overrides
(see references/adjustment-rules.md) -> consult lessons from past prints -> invoke
PrusaSlicer CLI -> parse the G-code summary (time / grams / layers) -> record the run
in the prints table. Does NOT upload or print -- that is octoprint.py + explicit confirm.

  python scripts/slice.py <prepared.stl> [--material PLA|PETG] [--printer NAME]
                          [--set key=value ...] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import common

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"
SEVERE_OVERHANG_DEG = 50.0
SEVERE_AREA_GATE_CM2 = 1.0
TALL_ASPECT = 4.0
TINY_FOOTPRINT_MM = 10.0


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def measure(stl_path: str) -> dict:
    import numpy as np
    import trimesh

    mesh = trimesh.load(stl_path, force="mesh")
    ext = [float(v) for v in mesh.extents]  # x, y, z
    height = ext[2]
    min_footprint = min(ext[0], ext[1])
    aspect = height / min_footprint if min_footprint > 0 else 0.0

    normals = mesh.face_normals
    areas = mesh.area_faces
    down = normals[:, 2] < 0
    severity = np.degrees(np.arcsin(np.clip(-normals[down, 2], 0.0, 1.0)))
    down_areas = areas[down]
    if severity.size:
        max_overhang = float(severity.max())
        severe = severity > SEVERE_OVERHANG_DEG
        severe_area_cm2 = float(down_areas[severe].sum()) / 100.0  # mm^2 -> cm^2
    else:
        max_overhang = 0.0
        severe_area_cm2 = 0.0

    return {
        "dimensions_mm": [round(v, 2) for v in ext],
        "height_mm": round(height, 2),
        "min_footprint_mm": round(min_footprint, 2),
        "aspect": round(aspect, 2),
        "max_overhang_deg": round(max_overhang, 1),
        "severe_overhang_area_cm2": round(severe_area_cm2, 2),
    }


# ---------------------------------------------------------------------------
# Adjustment rules
# ---------------------------------------------------------------------------
def adjustments(geo: dict, material: str, lessons: list) -> tuple[dict, list]:
    """Return (overrides, explanations) from codified rules + lessons."""
    overrides: dict[str, str] = {}
    notes: list[str] = []

    # R1 -- supports for steep overhangs
    if (geo["max_overhang_deg"] > SEVERE_OVERHANG_DEG
            and geo["severe_overhang_area_cm2"] >= SEVERE_AREA_GATE_CM2):
        overrides["support_material"] = "1"
        notes.append(
            f"R1: enabled supports -- {geo['max_overhang_deg']}deg overhang over "
            f"{geo['severe_overhang_area_cm2']} cm2 would sag unsupported.")

    # R2 -- brim for tall/tippy parts
    if geo["aspect"] > TALL_ASPECT:
        overrides["brim_width"] = "5"
        notes.append(
            f"R2: added 5mm brim -- tall/narrow part (aspect {geo['aspect']}) "
            f"is tip-over prone.")

    # R3 -- brim for tiny footprints
    if geo["min_footprint_mm"] < TINY_FOOTPRINT_MM:
        cur = int(overrides.get("brim_width", "0"))
        overrides["brim_width"] = str(max(cur, 4))
        notes.append(
            f"R3: ensured >=4mm brim -- small footprint "
            f"({geo['min_footprint_mm']}mm) peels easily.")

    # R4 -- PETG adhesion warning (out-of-spec bed)
    if material.upper() == "PETG":
        notes.append(
            "R4: PETG on the Tina 2S is marginal -- bed maxes at 60C (PETG wants "
            "70-80C). Use a clean plate + glue stick; brim is forced in the profile.")

    # Lessons learned (layered on top of geometric rules)
    for ls in lessons:
        adj = (ls["learned_adjustment"] or "").strip()
        if "=" in adj:
            k, v = adj.split("=", 1)
            overrides[k.strip()] = v.strip()
            notes.append(
                f"Lesson: applied {k.strip()}={v.strip()} "
                f"(learned from: {ls['trigger']}).")

    return overrides, notes


def fetch_lessons(conn, printer_id: int, material: str) -> list:
    return conn.execute(
        "SELECT * FROM lessons WHERE printer_id=? AND material=? ORDER BY ts DESC",
        (printer_id, material.upper()),
    ).fetchall()


# ---------------------------------------------------------------------------
# Slice
# ---------------------------------------------------------------------------
def profile_for(material: str) -> Path:
    p = PROFILE_DIR / f"tina2s_{material.lower()}.ini"
    if not p.exists():
        raise RuntimeError(f"No profile for material '{material}': {p} not found")
    return p


def _merged_profile(profile: Path, overrides: dict, stem: str) -> Path:
    """Write profile + overrides to one INI. PrusaSlicer's CLI flags don't cleanly
    cover every config key (booleans take no value), so we override via the loaded
    config file instead."""
    if not overrides:
        return profile
    remaining = dict(overrides)
    out_lines = []
    for line in profile.read_text().splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in remaining:
            out_lines.append(f"{key} = {remaining.pop(key)}")
        else:
            out_lines.append(line)
    if remaining:
        out_lines.append("\n# --- adjustment overrides ---")
        out_lines += [f"{k} = {v}" for k, v in remaining.items()]
    merged = common.WORK_DIR / f"{stem}_effective.ini"
    merged.write_text("\n".join(out_lines) + "\n")
    return merged


def run_slice(stl: Path, profile: Path, overrides: dict, out_gcode: Path) -> str:
    prusa = common.prusa_bin()
    if not prusa:
        raise RuntimeError("PrusaSlicer not found -> brew install --cask prusaslicer")
    cfg = _merged_profile(profile, overrides, stl.stem)
    cmd = [prusa, "--export-gcode", "--load", str(cfg),
           "--output", str(out_gcode), str(stl)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_gcode.exists():
        raise RuntimeError(f"PrusaSlicer failed:\n{proc.stderr.strip()[-500:]}")
    return proc.stderr  # warnings (e.g. stability hints) come on stderr


_RE_TIME = re.compile(r"estimated printing time \(normal mode\) = (.+)")
_RE_VOL = re.compile(r"filament used \[cm3\] = ([\d.]+)")
_RE_GRAMS = re.compile(r"total filament used \[g\] = ([\d.]+)")
_RE_DENSITY = re.compile(r"filament_density = ([\d.]+)")


def parse_summary(gcode: Path) -> dict:
    time = grams = vol = density = None
    layers = 0
    with open(gcode, errors="ignore") as f:
        for ln in f:
            if ln.startswith(";LAYER_CHANGE"):
                layers += 1
                continue
            if not ln.startswith(";"):
                continue
            if time is None and (m := _RE_TIME.search(ln)):
                time = m.group(1).strip()
            elif vol is None and (m := _RE_VOL.search(ln)):
                vol = float(m.group(1))
            elif (m := _RE_GRAMS.search(ln)):
                grams = float(m.group(1))
            elif density is None and (m := _RE_DENSITY.search(ln)):
                density = float(m.group(1))
    # PrusaSlicer leaves grams at 0 when density is unset; derive from volume.
    if (not grams) and vol and density:
        grams = round(vol * density, 2)
    return {"time": time, "grams": grams, "volume_cm3": vol, "layers": layers}


def detected_stability_warning(stderr: str) -> bool:
    return "enabling supports" in stderr.lower() or "print stability" in stderr.lower()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def slice_model(stl_path: str, material: str = "PLA",
                printer_name: str | None = None,
                user_overrides: dict | None = None,
                record: bool = True) -> dict:
    common.ensure_dirs()
    stl = Path(stl_path).expanduser().resolve()
    if not stl.exists():
        raise RuntimeError(f"Model not found: {stl}")

    conn = common.connect()
    common.init_db(conn)
    printer = (common.get_printer_by_name(conn, printer_name) if printer_name
               else common.get_active_printer(conn))
    if not printer:
        raise RuntimeError("No printer configured. Run: printers.py seed")

    profile = profile_for(material)
    geo = measure(str(stl))
    lessons = fetch_lessons(conn, printer["id"], material)
    overrides, notes = adjustments(geo, material, lessons)
    if user_overrides:
        for k, v in user_overrides.items():
            overrides[k] = v
            notes.append(f"User override: {k}={v}.")

    out_gcode = common.WORK_DIR / f"{stl.stem}_{material.lower()}.gcode"
    stderr = run_slice(stl, profile, overrides, out_gcode)

    # PrusaSlicer's own stability detector -> enable supports on a second pass.
    if detected_stability_warning(stderr) and "support_material" not in overrides:
        overrides["support_material"] = "1"
        notes.append("R1: PrusaSlicer flagged print-stability issues -> enabled "
                     "supports on a re-slice.")
        stderr = run_slice(stl, profile, overrides, out_gcode)

    summary = parse_summary(out_gcode)

    report = {
        "printer": printer["name"],
        "material": material.upper(),
        "profile": str(profile),
        "geometry": geo,
        "adjustments": overrides,
        "explanations": notes,
        "summary": summary,
        "gcode_path": str(out_gcode),
    }

    if record:
        cur = conn.execute(
            "INSERT INTO prints (source_type, model_path, printer_id, material, "
            "settings_json, slice_summary_json, gcode_path, status, adjustments_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (stl.suffix.lstrip(".").lower(), str(stl), printer["id"], material.upper(),
             json.dumps(overrides), json.dumps(summary), str(out_gcode), "sliced",
             json.dumps(notes)),
        )
        conn.commit()
        report["print_id"] = cur.lastrowid

    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Slice a model with adjustment rules")
    ap.add_argument("model")
    ap.add_argument("--material", default="PLA")
    ap.add_argument("--printer", default=None)
    ap.add_argument("--set", action="append", default=[], metavar="key=value",
                    help="explicit setting override (repeatable)")
    ap.add_argument("--no-record", action="store_true", help="do not log to DB")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    user_ov = {}
    for s in args.set:
        if "=" not in s:
            print(f"--set expects key=value, got: {s}", file=sys.stderr)
            return 2
        k, v = s.split("=", 1)
        user_ov[k.strip()] = v.strip()

    try:
        r = slice_model(args.model, args.material, args.printer,
                        user_ov, record=not args.no_record)
    except Exception as e:
        print(f"slice error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        g, s = r["geometry"], r["summary"]
        print(f"printer: {r['printer']}  material: {r['material']}")
        print(f"dimensions: {g['dimensions_mm']}  max overhang: "
              f"{g['max_overhang_deg']}deg ({g['severe_overhang_area_cm2']} cm2 severe)")
        print(f"time: {s['time']}  filament: {s['grams']} g  layers: {s['layers']}")
        if r["adjustments"]:
            print(f"adjustments: {r['adjustments']}")
        for n in r["explanations"]:
            print(f"  - {n}")
        print(f"gcode: {r['gcode_path']}")
        if "print_id" in r:
            print(f"logged as print #{r['print_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Doctor + first-run setup for the 3d-print skill.

Idempotent health check: verifies tools, DB, env vars, and OctoPrint reachability,
then prints a checklist and concrete next steps. Safe to re-run anytime.

  python scripts/setup.py            # full health check
  python scripts/setup.py --seed     # also seed the Tina 2S printer
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request

import common

OK, WARN, BAD = "OK  ", "WARN", "FAIL"


def line(status: str, label: str, detail: str = "") -> bool:
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    return status == OK


def check_tools() -> list[bool]:
    res = []
    brew = shutil.which("brew")
    res.append(line(OK if brew else WARN, "Homebrew",
                    brew or "not found (needed to install slicer/openscad)"))
    orca = common.orca_bin()
    res.append(line(OK if orca else BAD, "OrcaSlicer CLI",
                    orca or "missing -> brew install --cask orcaslicer"))
    scad = common.openscad_bin()
    res.append(line(OK if scad else BAD, "OpenSCAD (native)",
                    scad or "missing -> brew install --cask openscad@snapshot "
                            "(the 2021.01 cask is Intel-only, fails on Apple Silicon)"))
    tw = common.tweaker_script()
    res.append(line(OK if tw else WARN, "Tweaker-3 (auto-orient)",
                    tw or "not fetched -> run setup.py --fetch-tweaker (GPL, external)"))
    return res


def fetch_tweaker() -> None:
    common.ensure_dirs()
    if common.tweaker_script():
        print(f"Tweaker-3 already present at {common.TWEAKER_DIR}")
        return
    print(f"Fetching Tweaker-3 (GPL-3.0) into {common.TWEAKER_DIR} ...")
    subprocess.run(
        ["git", "clone", "--depth", "1", common.TWEAKER_REPO, str(common.TWEAKER_DIR)],
        check=True,
    )
    print("Done.")


def check_python() -> list[bool]:
    res = []
    try:
        import trimesh  # noqa: F401
        res.append(line(OK, "python: trimesh"))
    except Exception as e:
        res.append(line(BAD, "python: trimesh", f"{e} -> pip install -r requirements.txt"))
    try:
        import requests  # noqa: F401
        res.append(line(OK, "python: requests"))
    except Exception as e:
        res.append(line(BAD, "python: requests", str(e)))
    return res


def check_db() -> list[bool]:
    common.init_db()
    conn = common.connect()
    n = conn.execute("SELECT COUNT(*) FROM printers").fetchone()[0]
    active = common.get_active_printer(conn)
    res = [line(OK, "SQLite DB", str(common.DB_PATH))]
    if n == 0:
        res.append(line(WARN, "Printers", "none registered -> run with --seed"))
    else:
        res.append(line(OK, "Printers", f"{n} registered; default = "
                        f"{active['name'] if active else 'NONE'}"))
    return res


def check_octoprint() -> list[bool]:
    conn = common.connect()
    p = common.get_active_printer(conn)
    if not p:
        return [line(WARN, "OctoPrint", "no active printer yet")]
    url, key = common.octoprint_config(p)
    res = []
    if not key:
        res.append(line(WARN, "OctoPrint API key",
                        f"env {p['api_key_env']} not set -- see 'Next steps' below"))
        return res
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/version",
                                     headers={"X-Api-Key": key})
        with urllib.request.urlopen(req, timeout=5) as r:
            ok = r.status == 200
        res.append(line(OK if ok else BAD, "OctoPrint reachable", url))
    except Exception as e:
        res.append(line(WARN, "OctoPrint reachable", f"{url}: {e}"))
    return res


def next_steps() -> None:
    conn = common.connect()
    p = common.get_active_printer(conn)
    key_env = p["api_key_env"] if p else "OCTOPRINT_API_KEY"
    url = (p["octoprint_url"] if p else None) or "http://octopi.local"
    if os.environ.get(key_env):
        return
    print("\nNext steps (one-time credential setup):")
    print("  1. In OctoPrint: Settings -> Application Keys (or API key under Access).")
    print("  2. Add these lines to ~/.zshrc (replace the key), then restart your shell:")
    print(f'       export OCTOPRINT_URL="{url}"')
    print(f'       export {key_env}="<your-octoprint-api-key>"')
    print("  3. Re-run: python scripts/setup.py")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="3d-print skill setup/doctor")
    ap.add_argument("--seed", action="store_true", help="seed the Tina 2S printer")
    ap.add_argument("--fetch-tweaker", action="store_true",
                    help="git-clone Tweaker-3 (GPL) for auto-orient")
    args = ap.parse_args(argv)

    common.ensure_dirs()
    if args.fetch_tweaker:
        fetch_tweaker()
        print()
    if args.seed:
        import printers
        printers.cmd_seed(args)
        print()

    print("3d-print skill health check\n")
    results: list[bool] = []
    print("Tools:")
    results += check_tools()
    print("Python deps:")
    results += check_python()
    print("Storage:")
    results += check_db()
    print("Printer connectivity:")
    results += check_octoprint()

    next_steps()

    failed = results.count(False)
    print(f"\n{'All green.' if failed == 0 else f'{failed} item(s) need attention.'}")
    return 0  # doctor never hard-fails; it reports


if __name__ == "__main__":
    sys.exit(main())

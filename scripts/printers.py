#!/usr/bin/env python3
"""Printer registry CLI: add / list / switch / retire / show / seed.

Every print is stamped with its printer; retiring preserves history.
"""
from __future__ import annotations

import argparse
import sys

import common

TINA2S_SEED = dict(
    name="tina2s",
    model="WEEFUN Tina 2S",
    bed_x=100.0,
    bed_y=105.0,
    bed_z=100.0,
    nozzle_d=0.4,
    nozzle_max_c=245,
    bed_max_c=60,
    gcode_flavor="marlin",
    octoprint_url="http://octopi.local",
    api_key_env="OCTOPRINT_API_KEY",
    baud=None,  # 115200 (Wiibuilder) vs 1000000 (community) -- verify empirically
    materials="PLA,PETG",
    notes="Heated bed max 60C; PETG needs glue+brim. Bundled slicer: Wiibuilder.",
)


def _print_row(r) -> None:
    flag = " *default" if r["is_default"] else ""
    print(
        f"  [{r['id']}] {r['name']} ({r['model'] or '?'}) "
        f"{r['bed_x']:.0f}x{r['bed_y']:.0f}x{r['bed_z']:.0f}mm "
        f"materials={r['materials']} status={r['status']}{flag}"
    )


def cmd_list(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    rows = conn.execute("SELECT * FROM printers ORDER BY id").fetchall()
    if not rows:
        print("No printers registered. Run: printers.py seed")
        return 0
    print("Printers:")
    for r in rows:
        _print_row(r)
    return 0


def cmd_show(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    r = common.get_printer_by_name(conn, args.name)
    if not r:
        print(f"No printer named {args.name!r}", file=sys.stderr)
        return 1
    for k in r.keys():
        print(f"  {k}: {r[k]}")
    return 0


def _set_default(conn, printer_id: int) -> None:
    conn.execute("UPDATE printers SET is_default=0")
    conn.execute("UPDATE printers SET is_default=1 WHERE id=?", (printer_id,))


def cmd_add(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    if common.get_printer_by_name(conn, args.name):
        print(f"Printer {args.name!r} already exists.", file=sys.stderr)
        return 1
    cur = conn.execute(
        """INSERT INTO printers
           (name, model, bed_x, bed_y, bed_z, nozzle_d, nozzle_max_c, bed_max_c,
            gcode_flavor, octoprint_url, api_key_env, baud, materials, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (args.name, args.model, args.bed_x, args.bed_y, args.bed_z, args.nozzle_d,
         args.nozzle_max_c, args.bed_max_c, args.gcode_flavor, args.octoprint_url,
         args.api_key_env, args.baud, args.materials, args.notes),
    )
    if args.default or conn.execute("SELECT COUNT(*) FROM printers").fetchone()[0] == 1:
        _set_default(conn, cur.lastrowid)
    conn.commit()
    print(f"Added printer {args.name!r} (id={cur.lastrowid}).")
    return 0


def cmd_switch(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    r = common.get_printer_by_name(conn, args.name)
    if not r:
        print(f"No printer named {args.name!r}", file=sys.stderr)
        return 1
    if r["status"] != "active":
        print(f"Printer {args.name!r} is retired; reactivate it first.", file=sys.stderr)
        return 1
    _set_default(conn, r["id"])
    conn.commit()
    print(f"Default printer is now {args.name!r}.")
    return 0


def cmd_retire(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    r = common.get_printer_by_name(conn, args.name)
    if not r:
        print(f"No printer named {args.name!r}", file=sys.stderr)
        return 1
    was_default = bool(r["is_default"])
    conn.execute(
        "UPDATE printers SET status='retired', is_default=0 WHERE id=?", (r["id"],)
    )
    # if we just retired the default, promote the next active printer
    if was_default:
        nxt = conn.execute(
            "SELECT id FROM printers WHERE status='active' ORDER BY id LIMIT 1"
        ).fetchone()
        if nxt:
            _set_default(conn, nxt["id"])
    conn.commit()
    print(f"Retired {args.name!r} (history preserved).")
    return 0


def cmd_reactivate(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    r = common.get_printer_by_name(conn, args.name)
    if not r:
        print(f"No printer named {args.name!r}", file=sys.stderr)
        return 1
    conn.execute("UPDATE printers SET status='active' WHERE id=?", (r["id"],))
    conn.commit()
    print(f"Reactivated {args.name!r}.")
    return 0


def cmd_seed(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    if common.get_printer_by_name(conn, TINA2S_SEED["name"]):
        print("Tina 2S already seeded.")
        return 0
    cols = ",".join(TINA2S_SEED.keys())
    qs = ",".join("?" * len(TINA2S_SEED))
    cur = conn.execute(
        f"INSERT INTO printers ({cols}) VALUES ({qs})", tuple(TINA2S_SEED.values())
    )
    _set_default(conn, cur.lastrowid)
    conn.commit()
    print("Seeded Tina 2S as the default printer.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="3D printer registry")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("seed").set_defaults(func=cmd_seed)

    sp = sub.add_parser("show")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("add")
    sp.add_argument("name")
    sp.add_argument("--model", default=None)
    sp.add_argument("--bed-x", type=float, required=True, dest="bed_x")
    sp.add_argument("--bed-y", type=float, required=True, dest="bed_y")
    sp.add_argument("--bed-z", type=float, required=True, dest="bed_z")
    sp.add_argument("--nozzle-d", type=float, default=0.4, dest="nozzle_d")
    sp.add_argument("--nozzle-max-c", type=int, default=None, dest="nozzle_max_c")
    sp.add_argument("--bed-max-c", type=int, default=None, dest="bed_max_c")
    sp.add_argument("--gcode-flavor", default="marlin", dest="gcode_flavor")
    sp.add_argument("--octoprint-url", default=None, dest="octoprint_url")
    sp.add_argument("--api-key-env", default="OCTOPRINT_API_KEY", dest="api_key_env")
    sp.add_argument("--baud", type=int, default=None)
    sp.add_argument("--materials", default="PLA")
    sp.add_argument("--notes", default=None)
    sp.add_argument("--default", action="store_true")
    sp.set_defaults(func=cmd_add)

    for name, fn in (("switch", cmd_switch), ("retire", cmd_retire),
                     ("reactivate", cmd_reactivate)):
        sp = sub.add_parser(name)
        sp.add_argument("name")
        sp.set_defaults(func=fn)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

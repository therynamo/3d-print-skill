#!/usr/bin/env python3
"""Outcome review loop: record how a print turned out and learn from failures.

The user sends back photos of the finished print. The agent eyeballs them (reading
the image paths recorded here), assesses quality, and:
  1. stores rating + notes + image paths on the print (review),
  2. optionally records a *lesson* (printer + material + trigger + adjustment) so
     slice.py applies the fix automatically on the next print for that pairing.

  python scripts/review.py record <print_id> --rating 1-5 --notes "..." --images a.jpg,b.jpg
  python scripts/review.py learn  <print_id> --trigger "first-layer lifting" \
                                  --adjustment "brim_width=6"
  python scripts/review.py lessons [--printer NAME]
"""
from __future__ import annotations

import argparse
import json
import sys

import common


def _get_print(conn, print_id: int):
    r = conn.execute("SELECT * FROM prints WHERE id=?", (print_id,)).fetchone()
    if not r:
        raise RuntimeError(f"no print #{print_id}")
    return r


def cmd_record(args) -> int:
    if args.rating is not None and not (1 <= args.rating <= 5):
        print("rating must be 1-5", file=sys.stderr)
        return 2
    conn = common.connect()
    common.init_db(conn)
    p = _get_print(conn, args.print_id)
    status = args.status or ("done" if (args.rating or 0) >= 3 else "failed"
                             if args.rating else p["status"])
    conn.execute(
        "UPDATE prints SET outcome_rating=COALESCE(?, outcome_rating), "
        "outcome_notes=COALESCE(?, outcome_notes), "
        "outcome_images=COALESCE(?, outcome_images), status=? WHERE id=?",
        (args.rating, args.notes, args.images, status, args.print_id),
    )
    conn.commit()
    print(f"recorded outcome for print #{args.print_id} (status={status})")
    if args.images:
        print("images to review: " + ", ".join(args.images.split(",")))
    return 0


def cmd_learn(args) -> int:
    if "=" not in args.adjustment:
        print("--adjustment must be key=value (e.g. brim_width=6)", file=sys.stderr)
        return 2
    conn = common.connect()
    common.init_db(conn)
    p = _get_print(conn, args.print_id)
    if not p["printer_id"] or not p["material"]:
        print("print is missing printer/material; cannot scope a lesson",
              file=sys.stderr)
        return 1
    conn.execute(
        "INSERT INTO lessons (printer_id, material, trigger, learned_adjustment, "
        "source_print_id) VALUES (?,?,?,?,?)",
        (p["printer_id"], p["material"], args.trigger, args.adjustment, args.print_id),
    )
    conn.commit()
    print(f"learned: for printer #{p['printer_id']} / {p['material']}, "
          f"on '{args.trigger}' -> apply {args.adjustment}")
    print("slice.py will apply this automatically on the next matching slice.")
    return 0


def cmd_lessons(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    q = ("SELECT l.*, pr.name AS printer FROM lessons l "
         "JOIN printers pr ON pr.id=l.printer_id")
    params = []
    if args.printer:
        q += " WHERE pr.name=?"
        params.append(args.printer)
    q += " ORDER BY l.ts DESC"
    rows = conn.execute(q, params).fetchall()
    if not rows:
        print("no lessons recorded yet")
        return 0
    for r in rows:
        print(f"#{r['id']} {r['printer']}/{r['material']}: "
              f"'{r['trigger']}' -> {r['learned_adjustment']} "
              f"(from print #{r['source_print_id']})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="print outcome review + lessons")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="store rating/notes/images for a print")
    rec.add_argument("print_id", type=int)
    rec.add_argument("--rating", type=int, default=None)
    rec.add_argument("--notes", default=None)
    rec.add_argument("--images", default=None, help="csv of image paths")
    rec.add_argument("--status", default=None, help="override status")
    rec.set_defaults(func=cmd_record)

    lr = sub.add_parser("learn", help="record a lesson from a print's outcome")
    lr.add_argument("print_id", type=int)
    lr.add_argument("--trigger", required=True, help="the symptom observed")
    lr.add_argument("--adjustment", required=True, help="key=value fix to apply")
    lr.set_defaults(func=cmd_learn)

    ls = sub.add_parser("lessons", help="list learned lessons")
    ls.add_argument("--printer", default=None)
    ls.set_defaults(func=cmd_lessons)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        print(f"review error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

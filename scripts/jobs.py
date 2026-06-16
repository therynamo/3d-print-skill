#!/usr/bin/env python3
"""Print-job history CRUD over the `prints` table.

  python scripts/jobs.py list [--limit N] [--status S]
  python scripts/jobs.py show <id>
  python scripts/jobs.py set-status <id> <sliced|uploaded|printing|done|failed>
  python scripts/jobs.py outcome <id> --rating 1-5 [--notes "..."] [--images a.jpg,b.jpg]
"""
from __future__ import annotations

import argparse
import json
import sys

import common

STATUSES = {"sliced", "uploaded", "printing", "done", "failed"}


def _row_brief(r) -> str:
    s = json.loads(r["slice_summary_json"] or "{}")
    return (f"#{r['id']:<3} {r['ts'][:16]}  {r['status']:<9} "
            f"{(r['material'] or '?'):<5} {s.get('time') or '-':>10}  "
            f"{s.get('grams') or '-'}g  {r['model_path'].split('/')[-1]}")


def cmd_list(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    q = "SELECT * FROM prints"
    params = []
    if args.status:
        q += " WHERE status=?"
        params.append(args.status)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(q, params).fetchall()
    if not rows:
        print("no prints recorded yet")
        return 0
    for r in rows:
        print(_row_brief(r))
    return 0


def cmd_show(args) -> int:
    conn = common.connect()
    common.init_db(conn)
    r = conn.execute("SELECT * FROM prints WHERE id=?", (args.id,)).fetchone()
    if not r:
        print(f"no print #{args.id}", file=sys.stderr)
        return 1
    print(json.dumps(dict(r), indent=2))
    return 0


def cmd_set_status(args) -> int:
    if args.status not in STATUSES:
        print(f"status must be one of {sorted(STATUSES)}", file=sys.stderr)
        return 2
    conn = common.connect()
    common.init_db(conn)
    cur = conn.execute("UPDATE prints SET status=? WHERE id=?", (args.status, args.id))
    conn.commit()
    if cur.rowcount == 0:
        print(f"no print #{args.id}", file=sys.stderr)
        return 1
    print(f"print #{args.id} -> {args.status}")
    return 0


def cmd_outcome(args) -> int:
    if args.rating is not None and not (1 <= args.rating <= 5):
        print("rating must be 1-5", file=sys.stderr)
        return 2
    conn = common.connect()
    common.init_db(conn)
    cur = conn.execute(
        "UPDATE prints SET outcome_rating=COALESCE(?, outcome_rating), "
        "outcome_notes=COALESCE(?, outcome_notes), "
        "outcome_images=COALESCE(?, outcome_images) WHERE id=?",
        (args.rating, args.notes, args.images, args.id),
    )
    conn.commit()
    if cur.rowcount == 0:
        print(f"no print #{args.id}", file=sys.stderr)
        return 1
    print(f"recorded outcome for print #{args.id}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="print history CRUD")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list")
    ls.add_argument("--limit", type=int, default=20)
    ls.add_argument("--status", default=None)
    ls.set_defaults(func=cmd_list)

    sh = sub.add_parser("show")
    sh.add_argument("id", type=int)
    sh.set_defaults(func=cmd_show)

    ss = sub.add_parser("set-status")
    ss.add_argument("id", type=int)
    ss.add_argument("status")
    ss.set_defaults(func=cmd_set_status)

    oc = sub.add_parser("outcome")
    oc.add_argument("id", type=int)
    oc.add_argument("--rating", type=int, default=None)
    oc.add_argument("--notes", default=None)
    oc.add_argument("--images", default=None, help="csv of image paths")
    oc.set_defaults(func=cmd_outcome)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

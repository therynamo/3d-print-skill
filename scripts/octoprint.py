#!/usr/bin/env python3
"""OctoPrint bridge: upload sliced G-code and (only on explicit confirm) start a print.

SAFETY: `upload` never starts a print. Starting is a separate `start` command that
requires `--yes`, because a print is a physical, hard-to-reverse action. The agent
must obtain explicit user confirmation before ever calling `start`.

  python scripts/octoprint.py upload <file.gcode> [--printer NAME] [--print-id N]
  python scripts/octoprint.py start  <remote_name>  --yes [--printer NAME] [--print-id N]
  python scripts/octoprint.py status [--printer NAME]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

import common

TIMEOUT = 30


def _conn_printer(printer_name: str | None):
    conn = common.connect()
    common.init_db(conn)
    p = (common.get_printer_by_name(conn, printer_name) if printer_name
         else common.get_active_printer(conn))
    if not p:
        raise RuntimeError("No printer configured. Run: printers.py seed")
    url, key = common.octoprint_config(p)
    if not key:
        raise RuntimeError(
            f"OctoPrint API key missing. Set ${p['api_key_env']} "
            f"(see: python scripts/setup.py).")
    return conn, p, url.rstrip("/"), key


def _headers(key: str) -> dict:
    return {"X-Api-Key": key}


def upload(gcode_path: str, printer_name: str | None = None,
           print_id: int | None = None) -> dict:
    conn, p, url, key = _conn_printer(printer_name)
    path = Path(gcode_path).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"G-code not found: {path}")
    with open(path, "rb") as fh:
        # select=true stages the file as active but does NOT print (print omitted).
        r = requests.post(
            f"{url}/api/files/local",
            headers=_headers(key),
            files={"file": (path.name, fh, "application/octet-stream")},
            data={"select": "true", "print": "false"},
            timeout=120,
        )
    r.raise_for_status()
    remote = r.json().get("files", {}).get("local", {}).get("name", path.name)
    if print_id:
        conn.execute("UPDATE prints SET status='uploaded', octoprint_job=? WHERE id=?",
                     (remote, print_id))
        conn.commit()
    return {"uploaded": remote, "printer": p["name"], "octoprint": url,
            "printed": False, "note": "Staged only. Run `start` to print after confirm."}


def start(remote_name: str, printer_name: str | None = None,
          print_id: int | None = None, yes: bool = False) -> dict:
    if not yes:
        raise RuntimeError(
            "Refusing to start a print without --yes. A print is physical and "
            "hard to reverse; confirm with the user first, then pass --yes.")
    conn, p, url, key = _conn_printer(printer_name)
    r = requests.post(
        f"{url}/api/files/local/{remote_name}",
        headers={**_headers(key), "Content-Type": "application/json"},
        data=json.dumps({"command": "select", "print": True}),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    if print_id:
        conn.execute("UPDATE prints SET status='printing', octoprint_job=? WHERE id=?",
                     (remote_name, print_id))
        conn.commit()
    return {"started": remote_name, "printer": p["name"], "octoprint": url,
            "printed": True}


def cancel(printer_name: str | None = None, print_id: int | None = None) -> dict:
    conn, p, url, key = _conn_printer(printer_name)
    r = requests.post(f"{url}/api/job",
                      headers={**_headers(key), "Content-Type": "application/json"},
                      data=json.dumps({"command": "cancel"}), timeout=TIMEOUT)
    r.raise_for_status()
    if print_id:
        conn.execute("UPDATE prints SET status='failed' WHERE id=?", (print_id,))
        conn.commit()
    return {"cancelled": True, "printer": p["name"], "octoprint": url}


def status(printer_name: str | None = None) -> dict:
    conn, p, url, key = _conn_printer(printer_name)
    out: dict = {"printer": p["name"], "octoprint": url}
    try:
        job = requests.get(f"{url}/api/job", headers=_headers(key), timeout=TIMEOUT)
        job.raise_for_status()
        j = job.json()
        out["state"] = j.get("state")
        out["file"] = (j.get("job") or {}).get("file", {}).get("name")
        out["completion"] = (j.get("progress") or {}).get("completion")
    except Exception as e:
        out["error"] = str(e)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OctoPrint upload / start / status")
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload", help="upload G-code (does NOT print)")
    up.add_argument("gcode")
    up.add_argument("--printer", default=None)
    up.add_argument("--print-id", type=int, default=None)

    st = sub.add_parser("start", help="start a print (requires --yes + user confirm)")
    st.add_argument("remote_name")
    st.add_argument("--printer", default=None)
    st.add_argument("--print-id", type=int, default=None)
    st.add_argument("--yes", action="store_true")

    cn = sub.add_parser("cancel", help="cancel the active print")
    cn.add_argument("--printer", default=None)
    cn.add_argument("--print-id", type=int, default=None)

    sub.add_parser("status", help="current job/printer status").add_argument(
        "--printer", default=None)

    args = ap.parse_args(argv)
    try:
        if args.cmd == "upload":
            r = upload(args.gcode, args.printer, args.print_id)
        elif args.cmd == "start":
            r = start(args.remote_name, args.printer, args.print_id, args.yes)
        elif args.cmd == "cancel":
            r = cancel(args.printer, args.print_id)
        else:
            r = status(args.printer)
    except Exception as e:
        print(f"octoprint error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

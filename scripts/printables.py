#!/usr/bin/env python3
"""Printables model download via the site's own GraphQL API (no browser, no login).

Printables has no *documented* API, but the website is driven by a public GraphQL
endpoint (api.printables.com) that is reachable without authentication or a Cloudflare
challenge for free models. We resolve a model URL to its file list, ask the API for a
direct CDN download link per file, and fetch it. This works headless/remote (unlike a
real-browser login, which needs a display the user can see).

Gated/paid models may require auth: set PRINTABLES_TOKEN to a bearer token copied from
your logged-in browser (DevTools -> a request to api.printables.com -> Authorization
header, the part after "Bearer "). It is sent only as an Authorization header, never
printed or logged.

  python scripts/printables.py files <model-url>          # list files
  python scripts/printables.py fetch <model-url> [--json]  # download files
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import common

GRAPHQL_URL = "https://api.printables.com/graphql/"
UA = "Mozilla/5.0 (3d-print-skill)"
# File buckets on PrintType -> the getDownloadLink fileType enum value.
FILE_KINDS = {"stls": "stl", "slas": "sla", "gcodes": "gcode", "otherFiles": "other"}


def _model_id(url_or_id: str) -> str:
    """Extract the numeric model id from a Printables URL or a bare id."""
    s = url_or_id.strip()
    if s.isdigit():
        return s
    m = re.search(r"/model/(\d+)", s)
    if not m:
        raise ValueError(f"Could not find a Printables model id in {url_or_id!r}")
    return m.group(1)


def _gql(query: str) -> dict:
    body = json.dumps({"query": query}).encode()
    headers = {"User-Agent": UA, "Content-Type": "application/json"}
    token = os.environ.get("PRINTABLES_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(GRAPHQL_URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read())
    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "") for e in payload["errors"])
        raise RuntimeError(f"Printables API error: {msgs}")
    return payload["data"]


def list_files(url_or_id: str) -> dict:
    """Return {id, name, files:[{id, name, kind, fileType, size}]} for a model."""
    pid = _model_id(url_or_id)
    buckets = " ".join(f"{b}{{id name fileSize}}" for b in FILE_KINDS)
    data = _gql(f"query{{print(id:{pid}){{id name {buckets}}}}}")
    print_obj = data.get("print")
    if not print_obj:
        raise RuntimeError(f"No Printables model found for id {pid}")
    files = []
    for bucket, ftype in FILE_KINDS.items():
        for f in print_obj.get(bucket) or []:
            files.append({"id": f["id"], "name": f["name"], "kind": bucket,
                          "fileType": ftype, "size": f.get("fileSize")})
    return {"id": print_obj["id"], "name": print_obj["name"], "files": files}


def _download_link(file_id: str, file_type: str, print_id: str) -> str:
    data = _gql(
        f"mutation{{getDownloadLink(id:{file_id},fileType:{file_type},"
        f"printId:{print_id},source:model_detail){{ok output{{link}}}}}}"
    )
    res = data.get("getDownloadLink") or {}
    if not res.get("ok") or not (res.get("output") or {}).get("link"):
        raise RuntimeError(
            f"Could not get a download link for file {file_id} "
            f"(model may be gated -- set PRINTABLES_TOKEN)."
        )
    return res["output"]["link"]


def _download(url: str, suggested: str) -> Path:
    common.ensure_dirs()
    dest = common.DOWNLOAD_DIR / Path(suggested).name
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        dest.write_bytes(r.read())
    return dest


def fetch(url_or_id: str, kinds: tuple[str, ...] = ("stls",)) -> list[Path]:
    """Download a model's printable files (default: STLs) to DOWNLOAD_DIR."""
    info = list_files(url_or_id)
    wanted = [f for f in info["files"] if f["kind"] in kinds]
    if not wanted:
        raise RuntimeError(
            f"No {'/'.join(kinds)} files on model {info['id']} ({info['name']!r})."
        )
    saved: list[Path] = []
    for f in wanted:
        link = _download_link(f["id"], f["fileType"], info["id"])
        saved.append(_download(link, f["name"]))
    return saved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Printables download via GraphQL API")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("files", help="list a model's files")
    ls.add_argument("url")
    ft = sub.add_parser("fetch", help="download a model's STL files")
    ft.add_argument("url")
    ft.add_argument("--all", action="store_true", help="include non-STL files too")
    ft.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "files":
            info = list_files(args.url)
            print(f"{info['name']} (id {info['id']})")
            for f in info["files"]:
                kb = f"{f['size']/1024:.0f} KB" if f.get("size") else "?"
                print(f"  [{f['fileType']}] {f['name']} ({kb})")
        else:
            kinds = tuple(FILE_KINDS) if args.all else ("stls",)
            files = fetch(args.url, kinds=kinds)
            if args.json:
                print(json.dumps({"files": [str(f) for f in files]}, indent=2))
            else:
                for f in files:
                    print(f"downloaded: {f}")
    except Exception as e:
        print(f"printables error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

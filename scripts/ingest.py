#!/usr/bin/env python3
"""Normalize any printable input to a local model file.

Accepts: a local path (.stl/.3mf/.scad/.zip), a direct http(s) file URL, or a
Printables model URL. Zips are extracted and the printable files surfaced.

  python scripts/ingest.py <path-or-url> [--json]

Returns (and prints as JSON with --json):
  { primary: <path>, type: stl|3mf|scad, candidates: [...], source_type, source_ref }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import common

MODEL_EXTS = {".stl", ".3mf", ".scad", ".obj"}
UA = {"User-Agent": "Mozilla/5.0 (3d-print-skill ingest)"}


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _download(url: str) -> Path:
    common.ensure_dirs()
    name = Path(urllib.parse.urlparse(url).path).name or "download"
    dest = common.DOWNLOAD_DIR / name
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        # if server gave a filename, honor it
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r'filename="?([^"]+)"?', cd)
        if m:
            dest = common.DOWNLOAD_DIR / Path(m.group(1)).name
        data = r.read()
    dest.write_bytes(data)
    return dest


def _extract_zip(zip_path: Path) -> list[Path]:
    out_dir = common.DOWNLOAD_DIR / (zip_path.stem + "_extracted")
    out_dir.mkdir(parents=True, exist_ok=True)
    found: list[Path] = []
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            if Path(member).suffix.lower() in MODEL_EXTS and not member.startswith("__MACOSX"):
                target = out_dir / Path(member).name
                with z.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                found.append(target)
    return found


def _fetch_printables(url: str, headed: bool) -> Path:
    """Log in and download a Printables model via the browser-driven fetcher."""
    import printables
    files = printables.fetch(url, headed=headed)
    # Prefer a zip (multi-part bundle); otherwise the largest file.
    zips = [f for f in files if f.suffix.lower() == ".zip"]
    return zips[0] if zips else max(files, key=lambda f: f.stat().st_size)


def ingest(source: str, headed: bool = False) -> dict:
    source_type = "url" if _is_url(source) else "file"
    candidates: list[Path] = []

    if _is_url(source):
        host = urllib.parse.urlparse(source).netloc.lower()
        path_ext = Path(urllib.parse.urlparse(source).path).suffix.lower()
        if "printables.com" in host and path_ext not in MODEL_EXTS and path_ext != ".zip":
            local = _fetch_printables(source, headed)
        else:
            local = _download(source)
    else:
        local = Path(source).expanduser().resolve()
        if not local.exists():
            raise FileNotFoundError(source)

    ext = local.suffix.lower()
    if ext == ".zip":
        candidates = _extract_zip(local)
        if not candidates:
            raise ValueError(f"No printable files (.stl/.3mf/.scad) found in {local.name}")
    elif ext in MODEL_EXTS:
        candidates = [local]
    else:
        raise ValueError(f"Unsupported input type: {ext or '(none)'}")

    # primary = largest model file (heuristic for the main part)
    primary = max(candidates, key=lambda p: p.stat().st_size)
    return {
        "primary": str(primary),
        "type": primary.suffix.lower().lstrip("."),
        "candidates": [str(c) for c in candidates],
        "source_type": source_type if not _is_url(source) else "url",
        "source_ref": source,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Normalize a printable input")
    ap.add_argument("source", help="local path or http(s) URL")
    ap.add_argument("--headed", action="store_true",
                    help="for Printables URLs: open a visible browser (manual login)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = ingest(args.source, headed=args.headed)
    except Exception as e:
        print(f"ingest error: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"primary: {result['primary']} ({result['type']})")
        if len(result["candidates"]) > 1:
            print(f"candidates ({len(result['candidates'])}):")
            for c in result["candidates"]:
                print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

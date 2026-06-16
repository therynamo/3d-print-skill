"""Shared config, SQLite access, and printer/tool resolution for the 3d-print skill.

All runtime state lives outside the repo at ~/.3dprint (DB, work dir, downloads),
so nothing secret or large is ever committed.
"""
from __future__ import annotations

import glob
import os
import sqlite3
import shutil
import subprocess
import tempfile
from pathlib import Path

DATA_DIR = Path(os.environ.get("PRINT3D_HOME", Path.home() / ".3dprint"))
DB_PATH = DATA_DIR / "history.db"
WORK_DIR = DATA_DIR / "work"
DOWNLOAD_DIR = DATA_DIR / "downloads"
VENDOR_DIR = DATA_DIR / "vendor"
# Tweaker-3 is GPL-3.0; fetched here at setup time, NOT bundled in this MIT repo.
# We only invoke it as a separate program (subprocess) -> license-clean.
TWEAKER_DIR = VENDOR_DIR / "Tweaker-3"
TWEAKER_REPO = "https://github.com/ChristophSchranz/Tweaker-3.git"

# --- candidate tool locations (resolved lazily; verified by setup.py) ---
PRUSA_CANDIDATES = [
    "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer",
    "/Applications/Original Prusa Drivers/PrusaSlicer.app/Contents/MacOS/PrusaSlicer",
    shutil.which("prusa-slicer") or "",
    shutil.which("PrusaSlicer") or "",
]
ORCA_CANDIDATES = [
    "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer",
    shutil.which("orca-slicer") or "",
    shutil.which("OrcaSlicer") or "",
]
OPENSCAD_CANDIDATES = [
    "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    *sorted(glob.glob("/Applications/OpenSCAD*.app/Contents/MacOS/OpenSCAD"), reverse=True),
    shutil.which("openscad") or "",
]


def ensure_dirs() -> None:
    for d in (DATA_DIR, WORK_DIR, DOWNLOAD_DIR, VENDOR_DIR):
        d.mkdir(parents=True, exist_ok=True)


def tweaker_script() -> str | None:
    p = TWEAKER_DIR / "Tweaker.py"
    return str(p) if p.exists() else None


def find_tool(candidates: list[str]) -> str | None:
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def prusa_bin() -> str | None:
    return find_tool(PRUSA_CANDIDATES)


def orca_bin() -> str | None:
    return find_tool(ORCA_CANDIDATES)


def openscad_bin() -> str | None:
    return find_tool(OPENSCAD_CANDIDATES)


def render_stl_png(stl_path: str, png_path: str, size: int = 700) -> str:
    """Headless STL -> PNG via OpenSCAD (imports the mesh and auto-frames it)."""
    scad = openscad_bin()
    if not scad:
        raise RuntimeError("OpenSCAD not found; cannot render preview.")
    abs = str(Path(stl_path).resolve()).replace("\\", "/")
    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False) as f:
        f.write(f'import("{abs}");\n')
        scad_file = f.name
    try:
        subprocess.run(
            [scad, "-o", png_path, f"--imgsize={size},{size}",
             "--autocenter", "--viewall", "--colorscheme=Tomorrow", scad_file],
            check=True, capture_output=True, text=True,
        )
    finally:
        os.unlink(scad_file)
    return png_path


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS printers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    model         TEXT,
    bed_x         REAL NOT NULL,
    bed_y         REAL NOT NULL,
    bed_z         REAL NOT NULL,
    nozzle_d      REAL DEFAULT 0.4,
    nozzle_max_c  INTEGER,
    bed_max_c     INTEGER,
    gcode_flavor  TEXT DEFAULT 'marlin',
    octoprint_url TEXT,
    api_key_env   TEXT DEFAULT 'OCTOPRINT_API_KEY',
    baud          INTEGER,
    materials     TEXT DEFAULT 'PLA',
    notes         TEXT,
    status        TEXT DEFAULT 'active',     -- active | retired
    is_default    INTEGER DEFAULT 0,
    created_ts    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT DEFAULT (datetime('now')),
    source_type     TEXT,                    -- stl | 3mf | scad | url | text
    source_ref      TEXT,
    model_path      TEXT,
    printer_id      INTEGER REFERENCES printers(id),
    material        TEXT,
    settings_json   TEXT,
    slice_summary_json TEXT,                 -- {time, grams, layers}
    gcode_path      TEXT,
    octoprint_job   TEXT,
    status          TEXT,                    -- sliced|uploaded|printing|done|failed
    outcome_rating  INTEGER,                 -- 1-5
    outcome_notes   TEXT,
    outcome_images  TEXT,                    -- csv of paths
    adjustments_json TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                TEXT DEFAULT (datetime('now')),
    printer_id        INTEGER REFERENCES printers(id),
    material          TEXT,
    trigger           TEXT,
    learned_adjustment TEXT,
    source_print_id   INTEGER REFERENCES prints(id)
);
"""


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    conn.executescript(SCHEMA)
    conn.commit()
    if own:
        conn.close()


# ----------------------------------------------------------------------------
# Printer resolution
# ----------------------------------------------------------------------------
def get_active_printer(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Active default printer; falls back to any active printer."""
    row = conn.execute(
        "SELECT * FROM printers WHERE status='active' AND is_default=1 LIMIT 1"
    ).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT * FROM printers WHERE status='active' ORDER BY id LIMIT 1"
    ).fetchone()


def get_printer_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM printers WHERE name=?", (name,)).fetchone()


def octoprint_config(printer: sqlite3.Row) -> tuple[str, str | None]:
    """(url, api_key) for a printer, env vars overriding stored defaults."""
    url = os.environ.get("OCTOPRINT_URL") or printer["octoprint_url"] or "http://octopi.local"
    key_env = printer["api_key_env"] or "OCTOPRINT_API_KEY"
    return url, os.environ.get(key_env)

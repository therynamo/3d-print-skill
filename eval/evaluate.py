#!/usr/bin/env python3
"""Skill evaluation harness for the 3d-print skill.

Runs two suites and emits a self-contained, mobile-friendly HTML report + JSON data:
  - functional: drives the actual scripts end-to-end (slice, describe, safety gate,
    lessons feedback, ...) and checks observable outcomes.
  - quality: scores SKILL.md against skill-creator best practices (frontmatter,
    description triggers, word count, progressive disclosure, working references).

  python eval/evaluate.py            # writes eval/report.html + eval/results.json
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EVAL_DIR = ROOT / "eval"
PY = sys.executable
DEMO_STL = Path.home() / ".3dprint" / "work" / "demo_object_prepared.stl"


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SCRIPTS)}
    import os
    full_env = {**os.environ, **env}
    return subprocess.run([PY, *args], capture_output=True, text=True,
                          env=full_env, cwd=str(ROOT), **kw)


# ---------------------------------------------------------------------------
# Functional suite
# ---------------------------------------------------------------------------
def fn_setup_doctor() -> tuple[bool, str]:
    p = run([str(SCRIPTS / "setup.py")])
    ok = p.returncode == 0 and "health check" in p.stdout
    return ok, "doctor ran and reported a checklist" if ok else p.stderr[-200:]


def fn_slice_summary() -> tuple[bool, str]:
    if not DEMO_STL.exists():
        return False, f"missing demo STL at {DEMO_STL} (run prepare.py first)"
    p = run([str(SCRIPTS / "slice.py"), str(DEMO_STL), "--material", "PLA",
             "--no-record", "--json"])
    if p.returncode != 0:
        return False, p.stderr[-200:]
    data = json.loads(p.stdout)
    s = data["summary"]
    ok = bool(s["time"]) and bool(s["grams"]) and s["layers"] > 0
    return ok, (f"time={s['time']} grams={s['grams']} layers={s['layers']}"
                if ok else f"incomplete summary: {s}")


def fn_overhang_supports() -> tuple[bool, str]:
    p = run([str(SCRIPTS / "slice.py"), str(DEMO_STL), "--material", "PLA",
             "--no-record", "--json"])
    if p.returncode != 0:
        return False, p.stderr[-200:]
    data = json.loads(p.stdout)
    ok = data["adjustments"].get("support_material") == "1" and any(
        "support" in n.lower() for n in data["explanations"])
    return ok, ("supports auto-enabled with explanation"
                if ok else f"no support rule fired: {data['adjustments']}")


def fn_describe_preview() -> tuple[bool, str]:
    p = run([str(SCRIPTS / "describe.py"), "--name", "eval_cube", "--json",
             "--code", "difference(){cube([30,30,30],center=true);"
                       "cylinder(h=40,r=5,center=true,$fn=48);}"])
    if p.returncode != 0:
        return False, p.stderr[-200:]
    data = json.loads(p.stdout)
    png = Path(data["preview_png"])
    ok = png.exists() and png.stat().st_size > 0
    return ok, f"preview rendered ({png.stat().st_size} bytes)" if ok else "no preview"


def fn_safety_gate() -> tuple[bool, str]:
    p = run([str(SCRIPTS / "octoprint.py"), "start", "whatever.gcode"])
    ok = p.returncode != 0 and "without --yes" in p.stderr
    return ok, ("start refused without --yes (physical-action gate)"
                if ok else "GATE FAILED: start did not refuse")


def fn_lessons_feedback() -> tuple[bool, str]:
    # Record a slice, learn a lesson, confirm it is applied on the next slice.
    sp = run([str(SCRIPTS / "slice.py"), str(DEMO_STL), "--material", "PLA", "--json"])
    if sp.returncode != 0:
        return False, sp.stderr[-200:]
    pid = json.loads(sp.stdout)["print_id"]
    run([str(SCRIPTS / "review.py"), "learn", str(pid),
         "--trigger", "eval-self-test", "--adjustment", "brim_width=7"])
    after = run([str(SCRIPTS / "slice.py"), str(DEMO_STL), "--material", "PLA",
                 "--no-record", "--json"])
    data = json.loads(after.stdout)
    ok = data["adjustments"].get("brim_width") == "7"
    return ok, ("learned lesson applied on re-slice"
                if ok else f"lesson not applied: {data['adjustments']}")


def fn_jobs_list() -> tuple[bool, str]:
    p = run([str(SCRIPTS / "jobs.py"), "list"])
    ok = p.returncode == 0
    return ok, "job history listed" if ok else p.stderr[-200:]


FUNCTIONAL = [
    ("Setup doctor runs", fn_setup_doctor),
    ("Slice produces time/grams/layers", fn_slice_summary),
    ("Steep overhang auto-enables supports", fn_overhang_supports),
    ("Text-to-3D renders a preview", fn_describe_preview),
    ("Print start refuses without --yes", fn_safety_gate),
    ("Lessons feedback applied on re-slice", fn_lessons_feedback),
    ("Job history lists", fn_jobs_list),
]


# ---------------------------------------------------------------------------
# Quality suite (skill-creator rubric)
# ---------------------------------------------------------------------------
def parse_skill() -> tuple[dict, str]:
    text = (ROOT / "SKILL.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    fm: dict[str, str] = {}
    key = None
    for line in fm_raw.splitlines():
        if re.match(r"^\w[\w-]*:", line):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().lstrip(">|").strip()
        elif key and line.strip():
            fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm, body


def q_frontmatter() -> tuple[bool, str]:
    fm, _ = parse_skill()
    ok = bool(fm.get("name")) and bool(fm.get("description"))
    return ok, f"name='{fm.get('name')}', description present" if ok else "missing fields"


def q_description_length() -> tuple[bool, str]:
    fm, _ = parse_skill()
    n = len(fm.get("description", ""))
    ok = 50 <= n <= 600
    return ok, f"{n} chars (target 50-600)"


def q_triggers() -> tuple[bool, str]:
    fm, _ = parse_skill()
    d = fm.get("description", "").lower()
    cues = ['"', "print this", "slice", "make a model", "use when", " when "]
    hits = [c for c in cues if c in d]
    ok = len(hits) >= 2
    return ok, f"trigger cues present: {hits}" if ok else "weak triggers"


def q_third_person() -> tuple[bool, str]:
    fm, _ = parse_skill()
    d = fm.get("description", "").lower()
    bad = [p for p in ("load this skill", "you should", "i will") if p in d]
    return (not bad), "third-person/imperative" if not bad else f"avoid: {bad}"


def q_word_count() -> tuple[bool, str]:
    _, body = parse_skill()
    n = len(body.split())
    ok = 300 <= n <= 3000
    return ok, f"{n} words (target 300-3000, lean)"


def q_progressive_disclosure() -> tuple[bool, str]:
    has_ref = (ROOT / "references").is_dir() and any((ROOT / "references").iterdir())
    has_scripts = (SCRIPTS).is_dir()
    _, body = parse_skill()
    points = "references/" in body and "scripts/" in body
    ok = has_ref and has_scripts and points
    return ok, "references/ + scripts/ exist and are pointed to" if ok else "incomplete"


def q_references_resolve() -> tuple[bool, str]:
    _, body = parse_skill()
    refs = re.findall(r"`?(scripts/\w+\.py|references/[\w-]+\.md)`?", body)
    missing = [r for r in set(refs) if not (ROOT / r).exists()]
    ok = not missing
    return ok, f"all {len(set(refs))} referenced files exist" if ok else f"missing: {missing}"


QUALITY = [
    ("Valid frontmatter (name+description)", q_frontmatter),
    ("Description length in range", q_description_length),
    ("Description has trigger cues", q_triggers),
    ("Third-person/imperative description", q_third_person),
    ("SKILL.md body word count lean", q_word_count),
    ("Progressive disclosure implemented", q_progressive_disclosure),
    ("Referenced files all resolve", q_references_resolve),
]


# ---------------------------------------------------------------------------
# Run + report
# ---------------------------------------------------------------------------
def run_suite(suite) -> list[dict]:
    out = []
    for name, fn in suite:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"exception: {e}"
        out.append({"name": name, "pass": ok, "detail": detail})
    return out


def build_html(results: dict) -> str:
    def rows(items):
        r = ""
        for it in items:
            badge = "pass" if it["pass"] else "fail"
            mark = "PASS" if it["pass"] else "FAIL"
            r += (f'<tr class="{badge}"><td class="b"><span class="pill {badge}">'
                  f'{mark}</span></td><td>{html.escape(it["name"])}<div class="d">'
                  f'{html.escape(str(it["detail"]))}</div></td></tr>')
        return r

    fn_pass = sum(i["pass"] for i in results["functional"])
    q_pass = sum(i["pass"] for i in results["quality"])
    fn_tot = len(results["functional"])
    q_tot = len(results["quality"])
    total_pass = fn_pass + q_pass
    total = fn_tot + q_tot
    pct = round(100 * total_pass / total) if total else 0
    overall = "pass" if total_pass == total else ("warn" if pct >= 80 else "fail")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>3d-print skill evaluation</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--muted:#9aa3b2;--pass:#2ecc71;--fail:#e74c3c;--warn:#f39c12;--line:#262a33}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:#e6e9ef;font:16px/1.5 -apple-system,system-ui,Segoe UI,Roboto,sans-serif;padding:16px}}
h1{{font-size:20px;margin:0 0 4px}}
.sub{{color:var(--muted);font-size:13px;margin-bottom:16px}}
.score{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
.metric{{flex:1;min-width:90px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}}
.metric .n{{font-size:26px;font-weight:700}}
.metric .l{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
.ring{{font-size:30px;font-weight:800}}
.ring.pass{{color:var(--pass)}}.ring.warn{{color:var(--warn)}}.ring.fail{{color:var(--fail)}}
h2{{font-size:15px;margin:22px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden;border:1px solid var(--line)}}
td{{padding:12px 10px;border-top:1px solid var(--line);vertical-align:top}}
td.b{{width:64px}}
.d{{color:var(--muted);font-size:13px;margin-top:3px;word-break:break-word}}
.pill{{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:700}}
.pill.pass{{background:rgba(46,204,113,.15);color:var(--pass)}}
.pill.fail{{background:rgba(231,76,60,.15);color:var(--fail)}}
.foot{{color:var(--muted);font-size:12px;margin-top:20px;text-align:center}}
</style></head><body>
<h1>3d-print skill evaluation</h1>
<div class="sub">{html.escape(results["generated"])} &middot; commit {html.escape(results["commit"])}</div>
<div class="score">
  <div class="metric"><div class="ring {overall}">{pct}%</div><div class="l">overall</div></div>
  <div class="metric"><div class="n">{fn_pass}/{fn_tot}</div><div class="l">functional</div></div>
  <div class="metric"><div class="n">{q_pass}/{q_tot}</div><div class="l">quality</div></div>
</div>
<h2>Functional &mdash; does the pipeline work?</h2>
<table>{rows(results["functional"])}</table>
<h2>Quality &mdash; skill-creator rubric</h2>
<table>{rows(results["quality"])}</table>
<div class="foot">Generated by eval/evaluate.py. Live print (CHECKPOINT 4) requires the
physical Tina 2S + OctoPrint API key and is excluded from automated checks.</div>
</body></html>"""


def main() -> int:
    EVAL_DIR.mkdir(exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                            cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    results = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "commit": commit or "unknown",
        "functional": run_suite(FUNCTIONAL),
        "quality": run_suite(QUALITY),
    }
    (EVAL_DIR / "results.json").write_text(json.dumps(results, indent=2))
    (EVAL_DIR / "report.html").write_text(build_html(results))

    fn_pass = sum(i["pass"] for i in results["functional"])
    q_pass = sum(i["pass"] for i in results["quality"])
    tot = len(results["functional"]) + len(results["quality"])
    print(f"functional {fn_pass}/{len(results['functional'])}  "
          f"quality {q_pass}/{len(results['quality'])}  "
          f"({fn_pass + q_pass}/{tot} total)")
    for section in ("functional", "quality"):
        for it in results[section]:
            print(f"  [{'PASS' if it['pass'] else 'FAIL'}] {it['name']} -- {it['detail']}")
    print(f"\nwrote {EVAL_DIR / 'report.html'} and {EVAL_DIR / 'results.json'}")
    return 0 if fn_pass + q_pass == tot else 1


if __name__ == "__main__":
    sys.exit(main())

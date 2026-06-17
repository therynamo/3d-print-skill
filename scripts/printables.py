#!/usr/bin/env python3
"""Automated Printables login + model download (no public API -> real browser).

Printables is gated behind Prusa's SSO and has no documented API, so we drive a
real Chromium via Playwright. The login session is persisted (storage_state) in the
data dir, so the password is only used when there is no valid session yet.

Credentials come from the environment (shell export or .env, see common._load_env_file):
  PRINTABLES_USERNAME  (or PRINTABLES_EMAIL)   -- the Prusa account email
  PRINTABLES_PASSWORD

  python scripts/printables.py login [--headed]
  python scripts/printables.py fetch <model-or-file-url> [--headed] [--json]

`--headed` opens a visible browser; use it the first time or whenever automated login
is blocked by Cloudflare / a captcha / 2FA -- log in by hand once and the saved
session is reused on later headless runs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import common

STATE_PATH = lambda: common.DATA_DIR / "printables_state.json"  # noqa: E731
LOGIN_URL = "https://www.printables.com/login"
HOME_URL = "https://www.printables.com/"
NAV_TIMEOUT_MS = 45_000


def _creds() -> tuple[str, str]:
    user = os.environ.get("PRINTABLES_USERNAME") or os.environ.get("PRINTABLES_EMAIL")
    pw = os.environ.get("PRINTABLES_PASSWORD")
    if not user or not pw:
        raise RuntimeError(
            "Missing Printables credentials. Set PRINTABLES_USERNAME (or "
            "PRINTABLES_EMAIL) and PRINTABLES_PASSWORD in your shell or .env."
        )
    return user, pw


def _new_context(p, headed: bool):
    browser = p.chromium.launch(headless=not headed)
    state = STATE_PATH()
    ctx = browser.new_context(storage_state=str(state)) if state.exists() else browser.new_context()
    ctx.set_default_timeout(NAV_TIMEOUT_MS)
    return browser, ctx


def _looks_logged_in(page) -> bool:
    """Heuristic: an authenticated session exposes a user/avatar menu, not a Login link."""
    try:
        page.goto(HOME_URL, wait_until="domcontentloaded")
    except Exception:
        return False
    for sel in ('a[href*="/logout"]', 'button[aria-label*="user" i]',
                'a[href*="/my-models"]', 'img[alt*="avatar" i]'):
        if page.locator(sel).count() > 0:
            return True
    return False


def _do_login(page, user: str, pw: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    # Printables hands off to Prusa SSO (Keycloak-style). Fill whatever appears.
    email_sel = ('input[type="email"], input[name="username"], input[name="email"], '
                 '#username, #email')
    page.wait_for_selector(email_sel)
    page.fill(email_sel, user)
    # Single-page form usually has the password visible; multi-step needs a Continue.
    pw_sel = 'input[type="password"], input[name="password"], #password'
    if page.locator(pw_sel).count() == 0:
        for nxt in ('button:has-text("Continue")', 'button:has-text("Next")',
                    'button[type="submit"]'):
            if page.locator(nxt).count() > 0:
                page.click(nxt)
                break
        page.wait_for_selector(pw_sel)
    page.fill(pw_sel, pw)
    for submit in ('button:has-text("Log in")', 'button:has-text("Sign in")',
                   'button[type="submit"]', 'input[type="submit"]'):
        if page.locator(submit).count() > 0:
            page.click(submit)
            break
    page.wait_for_url("**printables.com/**", timeout=NAV_TIMEOUT_MS)


def login(headed: bool = False) -> Path:
    """Log in and persist the session. Returns the storage_state path."""
    from playwright.sync_api import sync_playwright

    common.ensure_dirs()
    user, pw = _creds()
    with sync_playwright() as p:
        browser, ctx = _new_context(p, headed)
        page = ctx.new_page()
        try:
            if not _looks_logged_in(page):
                if headed:
                    # Manual escape hatch: let the human clear Cloudflare/2FA/captcha.
                    page.goto(LOGIN_URL, wait_until="domcontentloaded")
                    print("Complete the login in the opened browser window...",
                          file=sys.stderr)
                    page.wait_for_url("**printables.com/**", timeout=300_000)
                else:
                    _do_login(page, user, pw)
            ctx.storage_state(path=str(STATE_PATH()))
        except Exception as e:
            raise RuntimeError(
                f"Automated login failed ({type(e).__name__}: {str(e)[:160]}). "
                "Re-run with --headed to log in manually once; the session is then reused."
            ) from e
        finally:
            browser.close()
    return STATE_PATH()


def fetch(url: str, headed: bool = False) -> list[Path]:
    """Download a Printables model's files (zip or single) to DOWNLOAD_DIR."""
    from playwright.sync_api import sync_playwright

    common.ensure_dirs()
    if not STATE_PATH().exists():
        login(headed=headed)

    saved: list[Path] = []
    with sync_playwright() as p:
        browser, ctx = _new_context(p, headed)
        page = ctx.new_page()
        try:
            if not _looks_logged_in(page):
                browser.close()
                login(headed=headed)
                browser, ctx = _new_context(p, headed)
                page = ctx.new_page()

            page.goto(url, wait_until="domcontentloaded")
            # Open the download control, then grab the "all / zip" option if present.
            for trigger in ('button:has-text("Download")', 'a:has-text("Download")',
                            'button[aria-label*="download" i]'):
                if page.locator(trigger).first.count() > 0:
                    page.locator(trigger).first.click()
                    break
            with page.expect_download(timeout=NAV_TIMEOUT_MS) as dl_info:
                for opt in ('text=/download all/i', 'text=/\\.zip/i',
                            'a[href*="download"]', 'button:has-text("Download")'):
                    loc = page.locator(opt).first
                    if loc.count() > 0:
                        loc.click()
                        break
            dl = dl_info.value
            dest = common.DOWNLOAD_DIR / (dl.suggested_filename or "printables_download")
            dl.save_as(str(dest))
            saved.append(dest)
        except Exception as e:
            raise RuntimeError(
                f"Download failed ({type(e).__name__}: {str(e)[:160]}). The page layout "
                "may have changed, or login is required -- try --headed."
            ) from e
        finally:
            browser.close()
    if not saved:
        raise RuntimeError("No file was downloaded from Printables.")
    return saved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Printables automated login + download")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login", help="log in and persist the session")
    lg.add_argument("--headed", action="store_true")
    ft = sub.add_parser("fetch", help="download a model's files")
    ft.add_argument("url")
    ft.add_argument("--headed", action="store_true")
    ft.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "login":
            path = login(headed=args.headed)
            print(f"session saved: {path}")
        else:
            files = fetch(args.url, headed=args.headed)
            if getattr(args, "json", False):
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

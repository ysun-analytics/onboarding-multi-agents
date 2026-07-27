#!/usr/bin/env python3
"""
build_pages.py — assemble the static GitHub Pages bundle from the local app.

The dashboard's default mode is a cached replay of frozen real runs (demo_cache/*.json)
that never calls the API — so it can run as pure static files. This script bundles that
into a self-contained folder that GitHub Pages serves with no backend:

  index.html      — the dashboard, with paths made relative (Pages serves under a
                    /onboarding-multi-agents/ subpath, so absolute "/static/…" would 404)
                    and the api-shim injected before app.js. The "Live run" toggle is
                    disabled with a note — live mode needs the Python backend + a key.
  app.css, app.js — copied verbatim from static/
  api-shim.js     — the client-side cached driver (mirrors onboarding/server.py)
  profiles.json   — the picker roster, pre-generated here (the real /api/profiles is a
                    server route; static hosting can't run it, so we freeze its output)
  demo_cache/     — the frozen runs the shim replays
  diagrams/       — the architecture SVGs the "How it's built" tab shows
  .nojekyll       — tell Pages to serve files as-is (no Jekyll processing)

Run:  .venv/bin/python scripts/build_pages.py            # writes ./site/
Deploy is a separate step (push ./site to the gh-pages branch).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from onboarding import data_loaders as data

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
CACHE = ROOT / "demo_cache"
DIAGRAMS = ROOT / "docs" / "diagrams"
SHIM = ROOT / "scripts" / "pages" / "api-shim.js"
OUT = ROOT / "site"


def build_profiles() -> list[dict]:
    """Freeze the picker roster. Same shape server.py's /api/profiles returns, but we
    expose ONLY hires that have a cached run — so every pick in the hosted demo renders a
    complete frozen flow with no dead ends. (The malformed-profile / graceful-failure path
    is a local-only demo; it needs the live backend to trigger.)"""
    profiles = []
    for hire_id in data.list_profile_ids():
        if not (CACHE / f"{hire_id}.json").exists():
            continue
        p = data.get_profile(hire_id)  # raises on malformed → skipped by the guard above
        label = (
            f"{p.full_name} — {p.role_title} · {p.location.city} · "
            f"{'FTE' if p.employment_type == 'fte' else 'Contractor'}"
        )
        profiles.append({
            "hire_id": hire_id, "name": p.full_name, "role_title": p.role_title,
            "label": label, "cached": True, "valid": True,
        })
    if not profiles:
        raise SystemExit("No cached profiles found — nothing to host. Build demo_cache first.")
    return profiles


def build_index() -> str:
    """Take static/index.html and make it work as a standalone page under a subpath."""
    html = (STATIC / "index.html").read_text()

    # Absolute → relative so it resolves under /onboarding-multi-agents/ on Pages.
    html = html.replace('href="/static/app.css"', 'href="app.css"')
    html = html.replace('src="/static/app.js"', 'src="app.js"')
    html = html.replace('src="/diagrams/', 'src="diagrams/')

    # Disable the live toggle (keep the element — app.js reads #live-toggle on boot) and
    # say why, plainly, so nobody wonders why it does nothing.
    html = html.replace(
        '<label title="Cached replays a real, frozen run (instant). Live calls GPT-4o for real.">\n'
        '        <input type="checkbox" id="live-toggle" /> <span id="mode-label">Live run</span>\n'
        '      </label>',
        '<label title="This hosted demo replays frozen real runs. Live mode (real GPT-4o) '
        'runs from the local backend — see the repo README." class="live-off">\n'
        '        <input type="checkbox" id="live-toggle" disabled /> '
        '<span id="mode-label">Live run · local only</span>\n'
        '      </label>',
    )

    # Inject the shim BEFORE app.js so window.fetch is wrapped before the first call.
    html = html.replace(
        '<script src="app.js"></script>',
        '<script src="api-shim.js"></script>\n<script src="app.js"></script>',
    )
    return html


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    (OUT / "index.html").write_text(build_index())
    shutil.copy2(STATIC / "app.css", OUT / "app.css")
    shutil.copy2(STATIC / "app.js", OUT / "app.js")
    shutil.copy2(SHIM, OUT / "api-shim.js")

    (OUT / "profiles.json").write_text(json.dumps({"profiles": build_profiles()}, indent=2))

    shutil.copytree(CACHE, OUT / "demo_cache")
    # Only the assets the page actually references (SVGs); skip the heavier PNGs/mmd sources.
    (OUT / "diagrams").mkdir()
    for svg in sorted(DIAGRAMS.glob("*.svg")):
        shutil.copy2(svg, OUT / "diagrams" / svg.name)

    (OUT / ".nojekyll").write_text("")

    n_files = sum(1 for _ in OUT.rglob("*") if _.is_file())
    print(f"Built {OUT.relative_to(ROOT)}/ — {n_files} files, "
          f"{len(json.loads((OUT / 'profiles.json').read_text())['profiles'])} hires.")


if __name__ == "__main__":
    main()

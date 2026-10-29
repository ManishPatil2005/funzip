"""Headless-Chromium smoke test for the chart UI. Requires the API (port 8000) and the Vite dev server (port 5173) to be running.

    pip install playwright && python scripts/ui_smoke.py [--shots DIR]

For each mode it checks that the canvas is not blank (enough distinct colours and enough non-background pixels) and that the
page logged no errors. Exit code 1 on any failure. Optional screenshots help review.
"""
from __future__ import annotations

import argparse
import os
import sys

from playwright.sync_api import sync_playwright


def canvas_stats(page) -> tuple[int, float]:  # type: ignore[no-untyped-def]
    """(distinct colours, share of sampled pixels that differ from the background) of the first chart canvas."""
    return page.evaluate(
        """() => {
          const c = document.querySelector('canvas'); const x = c.getContext('2d');
          const d = x.getImageData(0, 0, c.width, c.height).data; const seen = new Set(); let non = 0, n = 0;
          for (let i = 0; i < d.length; i += 4 * 7) {
            n++; seen.add((d[i] << 16) | (d[i+1] << 8) | d[i+2]);
            if (Math.abs(d[i]-11) + Math.abs(d[i+1]-15) + Math.abs(d[i+2]-23) > 12) non++;
          }
          return [seen.size, non / n];
        }"""
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5173/")
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    exe = "/opt/pw-browsers/chromium"
    failures: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(a.url)
        pg.wait_for_timeout(3500)
        for label, wait in (("Footprint", 4000), ("Candles + VP", 4000), ("TPO", 5000)):
            pg.get_by_role("button", name=label, exact=True).first.click()
            pg.wait_for_timeout(wait)
            colours, share = canvas_stats(pg)
            ok = colours >= 40 and share >= 0.08
            print(f"{label:14s} colours={colours:5d} content={share:5.1%} {'ok' if ok else 'BLANK/THIN'}")
            if not ok:
                failures.append(f"{label}: canvas looks empty")
            if a.shots:
                os.makedirs(a.shots, exist_ok=True)
                pg.screenshot(path=os.path.join(a.shots, label.split()[0].lower() + ".png"))
        if errs:
            failures.append(f"browser errors: {errs[:3]}")
        b.close()
    for f in failures:
        print("FAIL:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

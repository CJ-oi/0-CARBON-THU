from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


def launch_browser(playwright):
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if executable:
        options["executable_path"] = executable
    else:
        for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
            if Path(candidate).exists():
                options["executable_path"] = candidate
                break
    return playwright.chromium.launch(**options)


def embedded_site_html(site: Path) -> str:
    html = (site / "index.html").read_text(encoding="utf-8")
    css = (site / "styles.css").read_text(encoding="utf-8")
    js = (site / "app.js").read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    payloads: dict[str, object] = {}
    for relative in (
        "data/dashboard.json",
        "data/curated_archive.json",
        "data/archive.json",
        "data/report_index.json",
        "assets/maps/map_geometry.json",
        "data/runtime_config.json",
    ):
        path = site / relative
        if path.exists():
            payloads[relative] = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(payloads, ensure_ascii=False).replace("</script>", "<\\/script>")
    # Report capture is deterministic and does not depend on third-party tile/CDN availability.
    html = re.sub(r'<link[^>]+href=["\']https://unpkg\.com/leaflet[^"\']+["\'][^>]*>', "", html)
    html = re.sub(r'<script[^>]+src=["\']https://unpkg\.com/leaflet[^"\']+["\'][^>]*></script>', "", html)
    html = re.sub(r'<link\s+rel=["\']stylesheet["\']\s+href=["\']styles\.css["\']\s*/?>', lambda _m: f"<style>{css}</style>", html)
    html = re.sub(r'<link\s+rel=["\']manifest["\'][^>]*>', "", html)
    html = re.sub(
        r'<script\s+src=["\']app\.js["\']\s+defer\s*></script>',
        lambda _m: f"<script>window.__ZCP_SELFTEST__=true;window.__ZCP_EMBEDDED__={payload};</script><script>{js}</script>",
        html,
    )
    return html


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def inline_report_assets(html: str, report_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        quote, src = match.group(1), match.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        target = (report_dir / src).resolve()
        if not target.exists():
            return match.group(0)
        return f"src={quote}{data_uri(target)}{quote}"

    return re.sub(r"src=([\"'])([^\"']+)\1", replace, html)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture reference screenshots and render report PDFs")
    parser.add_argument("--site", default="site", help="built site directory")
    args = parser.parse_args()
    site = Path(args.site).resolve()
    if not (site / "index.html").exists():
        raise SystemExit(f"Missing built site: {site / 'index.html'}")

    screenshots = site / "assets" / "report_screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    reports = site / "reports"

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page = context.new_page()
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.set_content(embedded_site_html(site), wait_until="load", timeout=120_000)
        page.wait_for_function("document.documentElement.dataset.selftest === 'pass'", timeout=60_000)
        page.wait_for_selector("#kpiGrid .kpi")
        page.wait_for_selector(".map-marker-group")

        page.locator("#overview").screenshot(path=str(screenshots / "site-overview.png"))

        first_marker = page.locator(".map-marker-group").first
        first_marker.click()
        page.wait_for_timeout(300)
        page.locator("#map").screenshot(path=str(screenshots / "map-and-detail.png"))

        page.locator('[data-panel="gap"]').click()
        page.locator("#loadGapDemo").click()
        page.locator("#runGap").click()
        page.locator('[data-panel="reduce"]').click()
        page.locator("#generateReductionAdvice").click()
        page.wait_for_timeout(300)
        workbench = page.locator("#workbench")
        workbench.scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        box = workbench.bounding_box()
        if not box:
            raise RuntimeError("Unable to locate five-question workbench for screenshot")
        page.screenshot(
            path=str(screenshots / "five-questions.png"),
            clip={
                "x": max(0, box["x"]),
                "y": max(0, box["y"]),
                "width": min(box["width"], 1440),
                "height": min(box["height"], 940),
            },
        )

        if console_errors:
            raise RuntimeError("Browser console errors: " + " | ".join(console_errors[:8]))

        for stem in ("daily-latest", "weekly-latest", "feasibility-latest"):
            html_path = reports / f"{stem}.html"
            if not html_path.exists():
                continue
            report_page = context.new_page()
            report_html = inline_report_assets(html_path.read_text(encoding="utf-8"), reports)
            report_page.set_content(report_html, wait_until="load", timeout=120_000)
            report_page.emulate_media(media="print")
            report_page.pdf(
                path=str(reports / f"{stem}.pdf"),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"},
            )
            report_page.close()
        context.close()
        browser.close()

    required = [
        screenshots / "site-overview.png",
        screenshots / "map-and-detail.png",
        screenshots / "five-questions.png",
        reports / "daily-latest.pdf",
        reports / "weekly-latest.pdf",
    ]
    missing = [str(path) for path in required if not path.exists() or path.stat().st_size < 1000]
    if missing:
        raise SystemExit("Missing or empty rendered outputs: " + ", ".join(missing))
    print(f"Captured screenshots and rendered report PDFs in {site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

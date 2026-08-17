from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def validate_site(site_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    required = ["index.html", "styles.css", "app.js", "data/dashboard.json", "data/archive.json", "data/report_index.json"]
    for relative in required:
        if not (site_dir / relative).exists():
            errors.append(f"missing required file: {relative}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "button_count": 0, "id_count": 0}
    html = (site_dir / "index.html").read_text(encoding="utf-8")
    js = (site_dir / "app.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id=["\']([^"\']+)', html))
    buttons = re.findall(r'<button\b[^>]*>', html, flags=re.I)
    dead = [tag for tag in buttons if "id=" not in tag and "data-" not in tag and "type=\"submit\"" not in tag]
    if dead:
        errors.append(f"{len(dead)} visible buttons lack an id, data action, or form submit role")
    for required_id in ("mapCanvas", "updatesGrid", "fieldChecklist", "gapForm", "projectTableBody", "archiveTable", "reportLinks"):
        if required_id not in ids:
            errors.append(f"missing interactive target id: {required_id}")
    for target in re.findall(r'href=["\']([^"\']+)["\']', html):
        if target.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
            continue
        path = (site_dir / target.split("#", 1)[0]).resolve()
        if not path.exists():
            errors.append(f"broken local link: {target}")
    behavior_groups = [
        ("dashboard data load", ('fetch(\"data/dashboard.json\"', 'fetchJson(\"data/dashboard.json\"')),
        ("archive data load", ('fetch(\"data/archive.json\"', 'fetchJson(\"data/archive.json\"', 'fetchJson(\"data/curated_archive.json\"')),
        ("feasibility calculation", ("runFeasibility",)),
        ("report export", ("downloadFeasibilityReport",)),
        ("automatic reduction advice", ("generateReductionAdvice",)),
        ("report email", ("sendReportEmail",)),
    ]
    for label, alternatives in behavior_groups:
        if not any(token in js for token in alternatives):
            errors.append(f"app.js missing expected behavior: {label}")
    try:
        dashboard = json.loads((site_dir / "data/dashboard.json").read_text(encoding="utf-8"))
        if not dashboard.get("parks"):
            errors.append("dashboard has no parks")
        if not dashboard.get("updates"):
            warnings.append("dashboard has no public updates")
    except Exception as exc:
        errors.append(f"invalid dashboard.json: {type(exc).__name__}: {exc}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "button_count": len(buttons), "id_count": len(ids)}

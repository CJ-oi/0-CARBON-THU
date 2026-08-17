from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def today_iso() -> str:
    return date.today().isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def canonical_url(url: str) -> str:
    """Normalize URLs without removing meaningful path parameters.

    Tracking parameters are removed, fragments are discarded, HTTP is upgraded
    to HTTPS, hostname is lower-cased, and a trailing slash is removed except at
    the origin root.
    """
    value = normalize_space(url)
    if not value:
        return ""
    if value.startswith("//"):
        value = "https:" + value
    if value.startswith("http://"):
        value = "https://" + value[len("http://"):]
    parts = urlsplit(value)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    ignore = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "spm", "from", "source"}
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in ignore])
    return urlunsplit((scheme, netloc, path, query, ""))


def parse_date(value: str | None, fallback: str | None = None) -> str:
    text = normalize_space(value)
    if not text:
        return fallback or today_iso()
    patterns = [
        r"(?P<y>20\d{2})[-/.年](?P<m>1[0-2]|0?[1-9])[-/.月](?P<d>3[01]|[12]\d|0?[1-9])日?",
        r"(?P<y>20\d{2})(?P<m>0[1-9]|1[0-2])(?P<d>0[1-9]|[12]\d|3[01])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return date(int(match.group("y")), int(match.group("m")), int(match.group("d"))).isoformat()
            except ValueError:
                pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return fallback or today_iso()


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "已确认", "confirmed"}


def html_page(title: str, body: str, *, description: str = "", extra_head: str = "") -> str:
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{html.escape(title)}</title><meta name=\"description\" content=\"{html.escape(description)}\">{extra_head}
<style>
:root{{--paper:#f7f5ef;--surface:#fff;--ink:#182226;--muted:#687276;--line:#dfe3de;--green:#285d50;--rust:#a75f3b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.72 system-ui,-apple-system,Segoe UI,"Noto Sans CJK SC","Microsoft YaHei",sans-serif}}
main{{max-width:980px;margin:auto;padding:54px 24px 90px}}h1{{font-size:34px;line-height:1.25}}h2{{margin-top:42px;border-top:1px solid var(--line);padding-top:24px}}h3{{margin-top:28px}}a{{color:var(--green)}}.meta{{color:var(--muted)}}.card{{background:var(--surface);border:1px solid var(--line);padding:18px;margin:14px 0}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{border:1px solid var(--line);padding:9px;text-align:left;vertical-align:top}}th{{background:#eef2ef}}code,pre{{background:#ecefea}}pre{{padding:14px;overflow:auto}}.status{{display:inline-block;padding:3px 8px;border:1px solid var(--line);border-radius:99px}}.warn{{color:#8b4b2f}}.ok{{color:#24634f}}@media(max-width:700px){{table{{display:block;overflow-x:auto}}}}
</style></head><body><main>{body}</main></body></html>"""


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(map(cell, headers)) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)

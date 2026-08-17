from __future__ import annotations

import html as html_lib
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .curation import curate_record
from .utils import canonical_url, iso_now, normalize_space, parse_date, read_json, sha256_text, today_iso, write_json

USER_AGENT = "ZeroCarbonParkObservatory/1.0 (public-data research; GitHub open-source project)"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.meta: dict[str, str] = {}
        self.paragraphs: list[str] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []
        self._in_p = False
        self._p_text: list[str] = []
        self.page_title = ""
        self._in_title = False
        self._title_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {str(k).lower(): (v or "") for k, v in attrs}
        lower = tag.lower()
        if lower == "a":
            self._href = attrs_dict.get("href")
            self._anchor_text = []
        elif lower == "meta":
            key = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content", "")
            if key and content:
                self.meta[key] = content
        elif lower == "p":
            self._in_p = True
            self._p_text = []
        elif lower == "title":
            self._in_title = True
            self._title_text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._anchor_text.append(data)
        if self._in_p:
            self._p_text.append(data)
        if self._in_title:
            self._title_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower == "a" and self._href is not None:
            text = normalize_space("".join(self._anchor_text))
            if self._href and text:
                self.links.append({"href": self._href, "text": text})
            self._href = None
            self._anchor_text = []
        elif lower == "p" and self._in_p:
            text = normalize_space("".join(self._p_text))
            if len(text) >= 30:
                self.paragraphs.append(text)
            self._in_p = False
            self._p_text = []
        elif lower == "title" and self._in_title:
            self.page_title = normalize_space("".join(self._title_text))
            self._in_title = False
            self._title_text = []


@dataclass
class FetchResult:
    url: str
    body: bytes
    content_type: str
    charset: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)


def fetch(url: str, *, timeout: int = 20, max_bytes: int = 3_000_000) -> FetchResult:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            body = body[:max_bytes]
        content_type = response.headers.get_content_type() or "application/octet-stream"
        charset = response.headers.get_content_charset() or "utf-8"
        return FetchResult(
            url=response.geturl(),
            body=body,
            content_type=content_type,
            charset=charset,
            status=getattr(response, "status", 200),
            headers={k.lower(): v for k, v in response.headers.items()},
        )


def parse_html(body: bytes, charset: str = "utf-8") -> LinkParser:
    parser = LinkParser()
    parser.feed(body.decode(charset, errors="replace"))
    return parser


def _allowed(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return not domains or any(host == d or host.endswith("." + d) for d in domains)


def _topic(title: str, topic_rules: dict[str, list[str]]) -> str:
    for topic, terms in topic_rules.items():
        if any(term in title for term in terms):
            return topic
    return "综合动态"


def _extract_date(*values: str) -> str:
    for value in values:
        parsed = parse_date(value, fallback="")
        if parsed:
            return parsed
    return today_iso()


def _extract_summary(parser: LinkParser, title: str) -> str:
    candidates = [
        parser.meta.get("description", ""),
        parser.meta.get("og:description", ""),
        parser.meta.get("twitter:description", ""),
    ]
    candidates.extend(parser.paragraphs[:6])
    for value in candidates:
        text = normalize_space(html_lib.unescape(value))
        if len(text) >= 50:
            return text[:360] + ("…" if len(text) > 360 else "")
    return f"公开页面发布了“{title}”相关信息。该记录用于发现政策、园区实践或技术线索；涉及园区绩效和项目收益时，仍需核对原文和园区台账。"


def discover_source(source: dict[str, Any], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.monotonic()
    timeout = int(config.get("request_timeout_seconds", 20))
    link_limit = int(config.get("max_links_per_source", 40))
    article_limit = int(config.get("max_article_fetches_per_source", 8))
    minimum_score = int(config.get("minimum_relevance_score", 4))
    result = fetch(source["start_url"], timeout=timeout)
    if "html" not in result.content_type and "xml" not in result.content_type and "rss" not in result.content_type:
        raise ValueError(f"unsupported content type: {result.content_type}")
    parser = parse_html(result.body, result.charset)
    keywords = config.get("keywords", [])
    allowed_domains = source.get("allowed_domains", [])
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parser.links:
        title = normalize_space(item["text"])
        if len(title) < 6 or not any(keyword in title for keyword in keywords):
            continue
        url = canonical_url(urljoin(result.url, item["href"]))
        if not url or url in seen or not _allowed(url, allowed_domains):
            continue
        seen.add(url)
        candidates.append({"title": title[:180], "url": url})
        if len(candidates) >= link_limit:
            break

    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates):
        title = item["title"]
        summary = ""
        article_date = _extract_date(item["url"], title)
        if idx < article_limit:
            try:
                article = fetch(item["url"], timeout=timeout)
                article_parser = parse_html(article.body, article.charset)
                if article_parser.page_title and len(title) < 15:
                    title = article_parser.page_title[:180]
                summary = _extract_summary(article_parser, title)
                page_text = " ".join(article_parser.paragraphs[:10])
                article_date = _extract_date(page_text, item["url"], title)
            except (HTTPError, URLError, TimeoutError, ValueError, OSError):
                summary = ""
        if not summary:
            summary = f"公开来源发布了“{title}”相关信息。平台保留原文入口，并将其作为后续核验、数据补充或措施筛选的线索。"
        canonical = canonical_url(item["url"])
        now = iso_now()
        content_hash = sha256_text("|".join([title, summary, canonical]))
        raw = {
            "record_id": "WEB-" + content_hash[:16],
            "published_date": article_date,
            "title": title,
            "summary": summary,
            "publisher": source["name"],
            "source_name": source["name"],
            "source_id": source["id"],
            "source_scope": source.get("scope", ""),
            "source_type": source.get("type", ""),
            "default_category": source.get("default_category", ""),
            "region": source.get("region", "中国"),
            "parks": [],
            "url": item["url"],
            "canonical_url": canonical,
            "review_status": "machine_collected",
            "first_seen": now,
            "last_seen": now,
            "content_hash": content_hash,
        }
        curated = curate_record(raw, minimum_score=minimum_score)
        if curated.get("relevance_status") == "include":
            rows.append(curated)
        else:
            rejected.append({
                "title": curated.get("title"), "url": curated.get("url"),
                "score": curated.get("relevance_score"), "reason": curated.get("relevance_reason"),
            })
    log = {
        "source_id": source["id"],
        "source_name": source["name"],
        "start_url": source["start_url"],
        "status": "ok",
        "candidates": len(candidates),
        "records": len(rows),
        "rejected_low_relevance": len(rejected),
        "rejected_examples": rejected[:5],
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "attempted_at": iso_now(),
        "error": "",
    }
    return rows, log


def load_health(path: Path) -> dict[str, Any]:
    health = read_json(path, {"updated_at": None, "sources": {}})
    health.setdefault("sources", {})
    return health


def should_attempt(source: dict[str, Any], health: dict[str, Any], config: dict[str, Any]) -> bool:
    row = health.get("sources", {}).get(source["id"], {})
    if row.get("status") != "quarantined":
        return True
    last_attempt = row.get("last_attempt")
    if not last_attempt:
        return True
    try:
        previous = time.mktime(time.strptime(last_attempt[:10], "%Y-%m-%d"))
        days = (time.time() - previous) / 86400
        return days >= int(config.get("failure_policy", {}).get("quarantine_retest_days", 7))
    except (ValueError, TypeError):
        return True


def update_health(health: dict[str, Any], source: dict[str, Any], log: dict[str, Any], config: dict[str, Any]) -> None:
    policy = config.get("failure_policy", {})
    watch_after = int(policy.get("watch_after", 3))
    quarantine_after = int(policy.get("quarantine_after", 7))
    previous = health["sources"].get(source["id"], {})
    failures = int(previous.get("consecutive_failures", 0))
    if log["status"] == "ok":
        failures = 0
        status = "healthy"
        last_success = log["attempted_at"]
    else:
        failures += 1
        last_success = previous.get("last_success")
        status = "quarantined" if failures >= quarantine_after else ("watch" if failures >= watch_after else "failed")
    health["sources"][source["id"]] = {
        "source_name": source["name"],
        "status": status,
        "consecutive_failures": failures,
        "last_attempt": log["attempted_at"],
        "last_success": last_success,
        "last_record_count": log.get("records", 0),
        "last_error": log.get("error", ""),
        "start_url": source["start_url"],
    }
    health["updated_at"] = iso_now()


def collect_all(config_path: Path, health_path: Path, *, source_id: str | None = None, sleep_seconds: float = 0.5) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    config = read_json(config_path, {})
    health = load_health(health_path)
    records: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    for source in config.get("sources", []):
        if not source.get("enabled", True) or (source_id and source["id"] != source_id):
            continue
        if not should_attempt(source, health, config):
            logs.append({
                "source_id": source["id"], "source_name": source["name"], "start_url": source["start_url"],
                "status": "skipped_quarantine", "records": 0, "elapsed_seconds": 0,
                "attempted_at": iso_now(), "error": "source is quarantined and awaiting scheduled retest",
            })
            continue
        try:
            rows, log = discover_source(source, config)
            records.extend(rows)
        except Exception as exc:  # one source must not stop the rest
            log = {
                "source_id": source["id"], "source_name": source["name"], "start_url": source["start_url"],
                "status": "failed", "records": 0, "elapsed_seconds": 0,
                "attempted_at": iso_now(), "error": f"{type(exc).__name__}: {exc}"[:500],
            }
        logs.append(log)
        update_health(health, source, log, config)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    write_json(health_path, health)
    return records, logs, health

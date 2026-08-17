from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .curation import curate_archive, curate_record
from .utils import canonical_url, iso_now, read_json, sha256_text, write_json


def load_archive(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            except json.JSONDecodeError:
                continue
    return rows


def save_archive(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def initialize_archive(path: Path, seed_path: Path) -> list[dict[str, Any]]:
    """Initialize the archive and merge maintainer-reviewed seed records.

    Reviewed seeds are part of the public audit trail.  They are merged by
    canonical URL on every build so a maintainer can add or correct a reviewed
    record without deleting the rolling archive.  Unchanged records keep their
    original ``last_seen`` value; this avoids a no-op build creating a data
    commit.
    """
    rows = load_archive(path)
    seeds = [dict(item) for item in (read_json(seed_path, []) or []) if isinstance(item, dict)]
    if not rows:
        merged, _ = merge_records([], seeds)
        save_archive(path, merged)
        return merged

    by_url: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = canonical_url(row.get("canonical_url") or row.get("url") or "")
        if key:
            item = dict(row)
            item["canonical_url"] = key
            by_url[key] = item

    changed = False
    for seed in seeds:
        key = canonical_url(seed.get("canonical_url") or seed.get("url") or "")
        if not key:
            continue
        seed["canonical_url"] = key
        seed.setdefault("url", key)
        seed.setdefault("content_hash", sha256_text("|".join([str(seed.get("title", "")), str(seed.get("summary", "")), key])))
        previous = by_url.get(key)
        if previous is None:
            seed.setdefault("first_seen", iso_now())
            seed.setdefault("last_seen", seed["first_seen"] )
            seed.setdefault("version_count", 1)
            by_url[key] = seed
            changed = True
        elif previous.get("content_hash") != seed.get("content_hash"):
            seed["first_seen"] = previous.get("first_seen") or seed.get("first_seen") or iso_now()
            seed["last_seen"] = seed.get("last_seen") or iso_now()
            seed["version_count"] = int(previous.get("version_count", 1)) + 1
            seed["previous_content_hash"] = previous.get("content_hash")
            by_url[key] = {**previous, **seed}
            changed = True

    merged = sorted(by_url.values(), key=lambda x: (x.get("published_date", ""), x.get("first_seen", "")), reverse=True)
    merged, _ = curate_archive(merged)
    if changed or len(merged) != len(rows):
        save_archive(path, merged)
    return merged


def merge_records(existing: list[dict[str, Any]], incoming: Iterable[dict[str, Any]], *, max_records: int = 100000, minimum_relevance_score: int = 4, near_duplicate_threshold: float = 0.90) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_url: dict[str, dict[str, Any]] = {}
    for row in existing:
        key = canonical_url(row.get("canonical_url") or row.get("url") or "")
        if not key:
            continue
        row = dict(row)
        row["canonical_url"] = key
        row.setdefault("version_count", 1)
        by_url[key] = row
    added = 0
    updated = 0
    unchanged = 0
    for item in incoming:
        row = dict(item)
        key = canonical_url(row.get("canonical_url") or row.get("url") or "")
        if not key:
            continue
        row["canonical_url"] = key
        row["url"] = row.get("url") or key
        row.setdefault("content_hash", sha256_text("|".join([str(row.get("title", "")), str(row.get("summary", "")), key])))
        row.setdefault("first_seen", iso_now())
        row["last_seen"] = iso_now()
        previous = by_url.get(key)
        if previous is None:
            row["version_count"] = 1
            by_url[key] = row
            added += 1
        elif previous.get("content_hash") != row.get("content_hash"):
            row["first_seen"] = previous.get("first_seen", row["first_seen"])
            row["version_count"] = int(previous.get("version_count", 1)) + 1
            row["previous_content_hash"] = previous.get("content_hash")
            by_url[key] = {**previous, **row}
            updated += 1
        else:
            previous["last_seen"] = row["last_seen"]
            previous["publisher"] = row.get("publisher") or previous.get("publisher")
            unchanged += 1
    rows = sorted(by_url.values(), key=lambda x: (x.get("published_date", ""), x.get("first_seen", "")), reverse=True)
    rows, curation_stats = curate_archive(rows, minimum_score=minimum_relevance_score, threshold=near_duplicate_threshold)
    if len(rows) > max_records:
        rows = rows[:max_records]
    return rows, {
        "added": added, "updated": updated, "unchanged": unchanged, "total": len(rows),
        "duplicates_collapsed": curation_stats.get("duplicates_collapsed", 0),
        "included": curation_stats.get("included", 0),
        "excluded_low_relevance": curation_stats.get("excluded_low_relevance", 0),
    }


def archive_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = max((row.get("published_date", "") for row in rows), default="")
    topics: dict[str, int] = {}
    sources: dict[str, int] = {}
    for row in rows:
        topics[row.get("topic") or "未分类"] = topics.get(row.get("topic") or "未分类", 0) + 1
        sources[row.get("publisher") or row.get("source_name") or "未知来源"] = sources.get(row.get("publisher") or row.get("source_name") or "未知来源", 0) + 1
    return {
        "generated_at": iso_now(),
        "record_count": len(rows),
        "latest_published_date": latest,
        "topic_counts": dict(sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))),
        "source_counts": dict(sorted(sources.items(), key=lambda kv: (-kv[1], kv[0]))),
        "content_hash": sha256_text(json.dumps([(r.get("canonical_url"), r.get("content_hash")) for r in rows], ensure_ascii=False, sort_keys=True)),
    }


def write_archive_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    write_json(path, archive_manifest(rows))

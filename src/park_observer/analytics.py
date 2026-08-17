from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from .utils import parse_date, safe_float


def _top(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [{"name": name, "value": count} for name, count in counter.most_common(limit)]


def park_analytics(parks: list[dict[str, str]]) -> dict[str, Any]:
    domestic = [p for p in parks if (p.get("region_scope") or p.get("scope")) == "国内园区"]
    international = [p for p in parks if p not in domestic]
    province = Counter((p.get("province") or "未标注") for p in domestic)
    industry = Counter((p.get("industry_group") or p.get("industry") or "未分类") for p in domestic)
    level = Counter((p.get("level") or "未标注") for p in domestic)
    boundary = Counter((p.get("boundary_type") or "待核实") for p in domestic)
    return {
        "domestic_count": len(domestic),
        "international_count": len(international),
        "province": _top(province, 20),
        "industry": _top(industry, 12),
        "level": _top(level, 10),
        "boundary": _top(boundary, 10),
    }


def corpus_analytics(records: list[dict[str, Any]]) -> dict[str, Any]:
    topic = Counter((r.get("topic") or "未分类") for r in records)
    source = Counter((r.get("publisher") or r.get("source_name") or "未知来源") for r in records)
    region = Counter((r.get("region") or "未标注") for r in records)
    month = Counter()
    by_day = Counter()
    for row in records:
        d = parse_date(row.get("published_date"), fallback="")
        if d:
            month[d[:7]] += 1
            by_day[d] += 1
    latest_days = sorted(by_day)[-90:]
    cumulative = []
    running = 0
    for d in latest_days:
        running += by_day[d]
        cumulative.append({"date": d, "value": running})
    return {
        "topics": _top(topic, 12),
        "sources": _top(source, 12),
        "regions": _top(region, 12),
        "monthly": [{"name": k, "value": month[k]} for k in sorted(month)],
        "cumulative_90d": cumulative,
    }


def data_funnel(parks: list[dict[str, str]], evidence: list[dict[str, str]], verified_facts: list[dict[str, str]], archive: list[dict[str, Any]], assessments: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    assessments = assessments or []
    valid_assessments = 0
    for item in assessments:
        gate = item.get("gate") or {}
        if gate.get("ready"):
            valid_assessments += 1
    return [
        {"name": "园区名录对象", "value": len(parks), "meaning": "具有标准名称和唯一标识的园区或国际案例"},
        {"name": "滚动公开记录", "value": len(archive), "meaning": "经规范URL去重的政策、园区和技术记录"},
        {"name": "园区公开证据", "value": len(evidence), "meaning": "可以关联到具体园区、但仍需核对口径的材料"},
        {"name": "核验后公共事实", "value": len(verified_facts), "meaning": "完成来源与对象核验的名单、政策或宏观事实"},
        {"name": "正式核算园区", "value": valid_assessments, "meaning": "同边界、同年度、活动数据和排放数据均完整"},
    ]


def source_health_summary(health: dict[str, Any]) -> dict[str, Any]:
    rows = list((health.get("sources") or {}).values())
    counts = Counter(row.get("status") or "unknown" for row in rows)
    return {
        "counts": dict(counts),
        "rows": sorted(rows, key=lambda r: (r.get("status", ""), r.get("source_name", ""))),
        "updated_at": health.get("updated_at"),
    }


def prepare_public_parks(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    parks = []
    for row in rows:
        lat = safe_float(row.get("latitude"), 0.0) or 0.0
        lon = safe_float(row.get("longitude"), 0.0) or 0.0
        scope = row.get("region_scope") or "国内园区"
        parks.append({
            "park_id": row.get("park_id", ""),
            "scope": scope,
            "list_level": row.get("list_level", ""),
            "level": row.get("level", ""),
            "country": row.get("country", ""),
            "province": row.get("province", ""),
            "city": row.get("city", ""),
            "name": row.get("park_name", ""),
            "lat": lat,
            "lon": lon,
            "boundary_type": row.get("boundary_type", ""),
            "period": row.get("construction_period", ""),
            "industry": row.get("industry_group", ""),
            "classification_note": row.get("industry_classification_note", ""),
            "source_title": row.get("source_title", ""),
            "source_url": row.get("source_url", ""),
            "source_date": row.get("source_date", ""),
            "status": row.get("public_data_status", ""),
            "note": row.get("public_facts_note", "") or row.get("public_data_note", "") or row.get("notes", ""),
            "focus": row.get("recommended_focus", "") or row.get("suggested_path", "") or "优先核对边界、企业清单、能源平衡和基准年排放。",
            "coordinate_precision": row.get("coordinate_precision", "园区或所在片区近似中心"),
            "coordinate_status": row.get("coordinate_status", "待复核"),
            "coordinate_source": row.get("coordinate_source", "公开位置整理"),
            "coordinate_review_date": row.get("coordinate_review_date", ""),
        })
    return parks


def evidence_by_park(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        park_id = row.get("park_id") or row.get("关联park_id") or ""
        if not park_id:
            continue
        result[park_id].append({
            "statement": row.get("statement") or row.get("公开事实") or row.get("fact") or "",
            "source": row.get("source_name") or row.get("来源") or "",
            "url": row.get("source_url") or row.get("url") or "",
            "date": row.get("source_date") or row.get("date") or "",
            "caveat": row.get("caveat") or row.get("限制说明") or row.get("verification_note") or "仅作公开资料线索，正式使用前核对统计边界。",
        })
    return dict(result)

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any, Iterable

from .utils import normalize_space, sha256_text

_CITATION_TOKEN = re.compile(r"(?:cite|filecite).*?")
_DATE_PREFIX = re.compile(r"^\s*(?:20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s*)")
_DECORATIVE_PREFIX = re.compile(
    r"^\s*(?:部门图解|政策图解|一图读懂|图解|视频|音频|答记者问|文字实录|新闻发布会|权威解读)\s*[丨|｜:：·—-]*\s*"
)
_DOC_NUMBER = re.compile(r"(?:[\u4e00-\u9fa5]{1,10})?[〔\[]\s*(20\d{2})\s*[〕\]]\s*\d+\s*号")
_PUNCT = re.compile(r"[\s\-—–_·•丨|｜:：;；,，。.!！?？'\"“”‘’()（）\[\]【】《》<>]+")

CORE_TERMS: dict[str, int] = {
    "零碳园区": 10, "低碳园区": 8, "绿色园区": 6, "经济技术开发区": 2, "经开区": 2,
    "工业园区": 2, "产业园区": 1, "节能降碳": 6, "能碳管理": 6, "碳核算": 5,
    "碳排放": 3, "碳计量": 5, "碳足迹": 3, "工业共生": 6, "绿电直连": 5,
    "源网荷储": 5, "虚拟电厂": 4, "微电网": 4, "余热": 3, "余压": 3, "余冷": 3,
    "蒸汽系统": 3, "空压": 3, "电机节能": 3, "水回用": 3, "固废综合利用": 3,
    "绿色制造": 2, "绿色工厂": 3, "清洁能源": 2, "储能": 2, "绿电": 2,
    "节能改造": 4, "能效": 2, "减排": 2, "能源管理": 2,
}

NEGATIVE_TERMS: dict[str, int] = {
    "词元驱动": 10, "智能经济": 7, "脑机接口": 6, "量子科技": 5, "6g": 5,
    "低空装备": 5, "人才引进": 5, "科技创新生态": 6, "创新创业大赛": 6,
    "招商推介": 3, "文旅": 5, "赛事": 5, "消费券": 5, "党建": 4, "干部任免": 6,
    "采购公告": 4, "比选公告": 4, "招聘": 6, "表彰": 3, "会议通知": 2,
}

CATEGORY_TERMS: list[tuple[str, tuple[str, ...]]] = [
    ("技术与设施", ("余热", "余压", "余冷", "热泵", "电机", "空压", "蒸汽", "凝结水", "水回用", "固废", "节能改造", "绿色工厂", "储能", "微电网", "虚拟电厂", "源网荷储", "分布式光伏", "设备更新")),
    ("数据与评估", ("能碳管理", "碳核算", "排放因子", "碳计量", "监测平台", "碳足迹", "数据平台", "计量体系", "评价", "评估", "指标体系", "标准研究", "白皮书")),
    ("项目与投融资", ("开工", "投产", "签约", "投资", "招标", "融资", "专项债", "绿色贷款", "合同能源管理", "项目清单")),
    ("园区建设", ("零碳园区", "低碳园区", "绿色园区", "经开区", "经济技术开发区", "开发区", "工业园区", "产业园区", "园中园", "建设方案", "创建", "培育", "示范")),
    ("政策与标准", ("通知", "意见", "办法", "规划", "标准", "指南", "行动计划", "实施方案", "征求意见", "管理办法")),
]

NATIONAL_SOURCE_TERMS = ("国家发展改革委", "国家能源局", "工业和信息化部", "生态环境部", "商务部", "中国政府网", "国务院", "国家标准化")
LOCAL_SOURCE_TERMS = ("省发展改革委", "省能源局", "市发展改革委", "经济技术开发区", "高新技术产业开发区", "管委会", "人民政府")
IMPLEMENTATION_TERMS = ("投产", "开工", "改造", "项目", "投资", "减排", "节能量", "装机", "回收", "利用率", "能效", "示范", "建成", "运行")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = _CITATION_TOKEN.sub("", text).replace("\u200b", "").replace("\ufeff", "")
    return normalize_space(text)


def clean_title(value: Any) -> str:
    title = clean_text(value)
    title = _DATE_PREFIX.sub("", title)
    title = _DECORATIVE_PREFIX.sub("", title)
    return normalize_space(title.strip(" -—–_丨|｜:：·"))


def normalize_title(value: Any) -> str:
    title = clean_title(value).lower()
    for token in ("（试行）", "(试行)", "征求意见稿", "正式发布", "权威发布"):
        title = title.replace(token, "")
    return _PUNCT.sub("", title)


def extract_document_number(*values: Any) -> str:
    for value in values:
        match = _DOC_NUMBER.search(clean_text(value))
        if match:
            return _PUNCT.sub("", match.group(0))
    return ""


def source_level(source_name: str, source_scope: str = "") -> str:
    scope = clean_text(source_scope)
    if scope in {"国家", "地方", "园区", "行业", "研究"}:
        return scope
    text = clean_text(source_name)
    if any(term in text for term in NATIONAL_SOURCE_TERMS):
        return "国家"
    if "开发区" in text or "园区" in text or "管委会" in text:
        return "园区"
    if any(term in text for term in LOCAL_SOURCE_TERMS) or re.search(r"(?:省|市|自治区|新区)", text):
        return "地方"
    return "其他"


def relevance_score(title: str, summary: str = "", source_name: str = "", source_scope: str = "") -> tuple[int, list[str]]:
    text = f"{clean_title(title)} {clean_text(summary)}".lower()
    score = 0
    reasons: list[str] = []
    for term, weight in CORE_TERMS.items():
        if term.lower() in text:
            score += weight
            reasons.append(f"命中“{term}”")
    for term, weight in NEGATIVE_TERMS.items():
        if term.lower() in text:
            score -= weight
            reasons.append(f"弱相关“{term}”")
    if any(term in text for term in IMPLEMENTATION_TERMS):
        score += 2
        reasons.append("含实施或量化线索")
    level = source_level(source_name, source_scope)
    if level == "园区":
        score += 2
        reasons.append("来自园区公开来源")
    elif level == "国家" and any(term in text for term in ("标准", "核算", "指标体系", "零碳园区", "节能降碳")):
        score += 2
        reasons.append("国家级规则来源")
    if not any(term in text for term in ("园区", "开发区", "经开区", "节能", "碳", "能源", "绿色制造", "工业共生")):
        score -= 5
        reasons.append("缺少园区或降碳直接语义")
    return score, reasons


def classify_category(title: str, summary: str, source_name: str, source_scope: str = "", default_category: str = "") -> tuple[str, str]:
    text = f"{clean_title(title)} {clean_text(summary)}"
    level = source_level(source_name, source_scope)
    # Facilities and quantified projects take precedence over the word “通知”.
    for category, terms in CATEGORY_TERMS:
        if any(term in text for term in terms):
            if category == "项目与投融资" and not any(term in text for term in ("开工", "投产", "签约", "投资", "招标", "融资", "项目清单")):
                continue
            return category, level
    if default_category in {"园区建设", "技术与设施", "政策与标准", "数据与评估", "项目与投融资"}:
        return default_category, level
    return "其他重要动态", level


def event_key(row: dict[str, Any]) -> str:
    doc = extract_document_number(row.get("title"), row.get("summary"))
    if doc:
        return "DOC-" + sha256_text(doc)[:16]
    norm = normalize_title(row.get("title"))
    day = str(row.get("published_date") or "")[:10]
    return "EVT-" + sha256_text(f"{norm}|{day}")[:16]


def _why_for_category(category: str) -> str:
    mapping = {
        "园区建设": "用于核对建设范围、实施主体和进展；涉及绩效时仍需园区台账。",
        "技术与设施": "作为设施改造和项目储备线索；投资、节能量和减排量需可研或测量验证。",
        "政策与标准": "用于更新适用条件、核算规则和监管要求，并核对生效日期与适用对象。",
        "数据与评估": "用于更新数据字段、核算口径和评估方法；正式使用需保留版本与原始凭证。",
        "项目与投融资": "用于识别项目条件、实施主体和资金线索；收益与风险需基于项目参数复核。",
        "其他重要动态": "用于公开信息跟踪；正式评价前需核对对象、边界、年份和原始材料。",
    }
    return mapping.get(category, mapping["其他重要动态"])


def curate_record(row: dict[str, Any], *, minimum_score: int = 4) -> dict[str, Any]:
    result = dict(row)
    title = clean_title(result.get("title"))
    summary = clean_text(result.get("summary"))
    publisher = clean_text(result.get("publisher") or result.get("source_name"))
    scope = clean_text(result.get("source_scope"))
    score, reasons = relevance_score(title, summary, publisher, scope)
    category, level = classify_category(title, summary, publisher, scope, clean_text(result.get("default_category")))
    result.update({
        "title": title,
        "summary": summary,
        "normalized_title": normalize_title(title),
        "document_number": extract_document_number(title, summary),
        "topic": category,
        "category": category,
        "source_level": level,
        "relevance_score": score,
        "relevance_status": "include" if score >= minimum_score else "exclude",
        "relevance_reason": "；".join(reasons[:7]) if reasons else "未命中零碳园区核心主题",
    })
    result["event_key"] = event_key(result)
    result["why"] = _why_for_category(category) if result["relevance_status"] == "include" else "与园区降碳建设的直接关联不足，不进入首页和周报；原记录保留在审计档案。"
    # Quality score is deliberately interpretable: relevance + source + summary completeness.
    quality = score
    quality += 2 if level in {"国家", "地方", "园区"} else 0
    quality += 2 if len(summary) >= 80 else (1 if len(summary) >= 40 else 0)
    quality += 1 if result.get("published_date") else 0
    quality += 1 if result.get("url") else 0
    result["quality_score"] = quality
    return result


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _primary_rank(row: dict[str, Any]) -> tuple[int, int, int, int]:
    url = str(row.get("url") or "")
    path_score = 0
    if "/top/" in url or "图解" in str(row.get("title")):
        path_score -= 2
    if any(token in url for token in ("/tz/", "/ywtz/", "/zcfg/", "/zwgk/", "/xxgk/")):
        path_score += 2
    return int(row.get("quality_score") or 0), path_score, len(clean_text(row.get("summary"))), int(row.get("version_count") or 1)


def collapse_duplicates(records: Iterable[dict[str, Any]], *, threshold: float = 0.90) -> tuple[list[dict[str, Any]], int]:
    rows = [dict(r) for r in records]
    rows.sort(key=lambda r: (str(r.get("published_date") or ""), _primary_rank(r)), reverse=True)
    groups: list[list[dict[str, Any]]] = []
    for row in rows:
        placed = False
        for group in groups:
            head = group[0]
            same_doc = bool(row.get("document_number")) and row.get("document_number") == head.get("document_number")
            same_day = str(row.get("published_date") or "")[:10] == str(head.get("published_date") or "")[:10]
            same_title = row.get("normalized_title") and row.get("normalized_title") == head.get("normalized_title")
            near_title = same_day and title_similarity(str(row.get("title")), str(head.get("title"))) >= threshold
            if same_doc or same_title or near_title:
                group.append(row)
                placed = True
                break
        if not placed:
            groups.append([row])
    output: list[dict[str, Any]] = []
    collapsed = 0
    for group in groups:
        group.sort(key=_primary_rank, reverse=True)
        primary = dict(group[0])
        related = [
            {"title": r.get("title"), "publisher": r.get("publisher") or r.get("source_name"), "url": r.get("url")}
            for r in group[1:] if r.get("url")
        ]
        if related:
            primary["related_materials"] = related
            primary["duplicate_count"] = len(related)
            collapsed += len(related)
        output.append(primary)
    output.sort(key=lambda r: (str(r.get("published_date") or ""), int(r.get("quality_score") or 0)), reverse=True)
    return output, collapsed


def curate_archive(records: Iterable[dict[str, Any]], *, minimum_score: int = 4, threshold: float = 0.90) -> tuple[list[dict[str, Any]], dict[str, int]]:
    curated = [curate_record(row, minimum_score=minimum_score) for row in records]
    deduped, collapsed = collapse_duplicates(curated, threshold=threshold)
    included = sum(1 for r in deduped if r.get("relevance_status") == "include")
    return deduped, {
        "input": len(curated), "output": len(deduped), "duplicates_collapsed": collapsed,
        "included": included, "excluded_low_relevance": len(deduped) - included,
    }


def report_event_groups(records: Iterable[dict[str, Any]], *, minimum_score: int = 4, threshold: float = 0.90) -> list[dict[str, Any]]:
    curated = [curate_record(r, minimum_score=minimum_score) for r in records]
    included = [r for r in curated if r.get("relevance_status") == "include"]
    events, _ = collapse_duplicates(included, threshold=threshold)
    return events


def category_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(r.get("category") or r.get("topic") or "未分类") for r in records).most_common())

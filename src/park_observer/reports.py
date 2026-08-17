from __future__ import annotations

import html
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .curation import report_event_groups
from .utils import PROJECT_ROOT, html_page, iso_now, markdown_table, parse_date, read_json, write_json

CATEGORY_ORDER = ["园区建设", "技术与设施", "政策与标准", "数据与评估", "项目与投融资", "其他重要动态"]


def _content_policy() -> dict[str, Any]:
    return read_json(PROJECT_ROOT / "config/content_policy.json", {}) or {}


def _window(records: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    valid = [parse_date(r.get("published_date"), fallback="") for r in records]
    latest = max((d for d in valid if d), default=date.today().isoformat())
    cutoff = (date.fromisoformat(latest) - timedelta(days=days - 1)).isoformat()
    return [r for r in records if parse_date(r.get("published_date"), fallback="") >= cutoff]


def _rank(row: dict[str, Any]) -> tuple[int, str, str]:
    return int(row.get("quality_score") or 0), str(row.get("published_date") or ""), str(row.get("title") or "")


def _balanced_select(records: list[dict[str, Any]], *, days: int, limit: int) -> list[dict[str, Any]]:
    policy = _content_policy()
    minimum = int(policy.get("minimum_relevance_score", 4))
    threshold = float(policy.get("near_duplicate_threshold", 0.90))
    events = report_event_groups(records, minimum_score=minimum, threshold=threshold)
    rows = _window(events, days)
    if len(rows) < min(6, limit):
        rows = _window(events, max(days * 4, 30))
    rows.sort(key=_rank, reverse=True)
    shares = policy.get("weekly_target_share", {})
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cat[str(row.get("category") or row.get("topic") or "其他重要动态")].append(row)
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for cat in CATEGORY_ORDER:
        target = max(1, round(limit * float(shares.get(cat, 0.05)))) if cat in shares else 0
        for row in by_cat.get(cat, [])[:target]:
            key = str(row.get("event_key") or row.get("canonical_url") or row.get("record_id"))
            if key not in used:
                selected.append(row); used.add(key)
    for row in rows:
        if len(selected) >= limit:
            break
        key = str(row.get("event_key") or row.get("canonical_url") or row.get("record_id"))
        if key not in used:
            selected.append(row); used.add(key)
    return sorted(selected[:limit], key=_rank, reverse=True)


def _editorial_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = Counter(str(r.get("category") or r.get("topic") or "其他重要动态") for r in rows)
    sources = Counter(str(r.get("publisher") or r.get("source_name") or "未知来源") for r in rows)
    levels = Counter(str(r.get("source_level") or "未标注") for r in rows)
    total = max(1, len(rows))
    implementation_categories = {"园区建设", "技术与设施", "项目与投融资"}
    implementation_count = sum(categories.get(cat, 0) for cat in implementation_categories)
    policy_count = categories.get("政策与标准", 0)
    numeric_pattern = re.compile(r"(?:\d+(?:\.\d+)?)\s*(?:%|亿元|万元|万千瓦|千瓦|MW|MWh|GWh|tCO.?|吨|万吨|公里|小时|年)", re.I)
    numeric_count = sum(bool(numeric_pattern.search(" ".join([str(r.get("title") or ""), str(r.get("summary") or "")]))) for r in rows)
    linked_park_count = sum(bool(r.get("parks")) for r in rows)
    related_material_count = sum(len(r.get("related_materials") or []) for r in rows)
    target = _content_policy().get("weekly_target_share", {})

    theme_terms = {
        "计量与能碳管理": ["计量", "能碳", "平台", "监测", "管理系统"],
        "设备与系统节能": ["空压", "电机", "泵", "风机", "蒸汽", "余热", "余压", "热泵"],
        "清洁供能": ["光伏", "绿电", "储能", "微电网", "源网荷储", "氢能"],
        "资源循环": ["再生水", "水回用", "固废", "副产物", "工业共生", "循环利用"],
        "交通与物流": ["重卡", "充换电", "物流", "交通"],
        "项目与资金": ["投资", "补贴", "申报", "合同能源", "融资", "项目清单"],
    }
    theme_counts: Counter[str] = Counter()
    for row in rows:
        text = " ".join([str(row.get("title") or ""), str(row.get("summary") or ""), str(row.get("why") or "")])
        for theme, terms in theme_terms.items():
            if any(term in text for term in terms):
                theme_counts[theme] += 1

    quality_metrics = [
        {"label": "入选记录", "value": len(rows), "note": "经相关性筛选和事件归并后的记录"},
        {"label": "实施类记录", "value": implementation_count, "note": f"占{implementation_count / total:.0%}，包括园区建设、技术设施和项目投融资"},
        {"label": "政策标准记录", "value": policy_count, "note": f"占{policy_count / total:.0%}"},
        {"label": "含量化线索", "value": numeric_count, "note": "仅表示存在数字，不代表可直接进入园区核算"},
        {"label": "明确关联园区", "value": linked_park_count, "note": "已完成园区对象关联的记录"},
        {"label": "独立来源", "value": len(sources), "note": f"最高单一来源占比{(sources.most_common(1)[0][1] / total if sources else 0):.0%}"},
        {"label": "归并关联材料", "value": related_material_count, "note": "同一事件下保留的补充来源"},
    ]

    summary = [
        f"本期纳入{len(rows)}条经过去重和相关性筛选的记录，其中实施类{implementation_count}条、政策标准{policy_count}条。",
        f"记录来自{len(sources)}个独立来源；{numeric_count}条含量化线索，{linked_park_count}条已明确关联具体园区。",
    ]
    if theme_counts:
        top_themes = "、".join(f"{name}{count}条" for name, count in theme_counts.most_common(3))
        summary.append(f"本期较集中的工作主题为：{top_themes}。")
    else:
        summary.append("本期记录尚未形成明显的设施或项目主题，需要继续补充园区一手资料。")

    opportunities: list[str] = []
    constraints: list[str] = []
    data_tasks: list[str] = []
    if theme_counts.get("计量与能碳管理"):
        opportunities.append("将分级计量、能碳台账和异常监测作为数据底座项目，先解决边界、口径和责任不清的问题。")
        data_tasks.append("补充计量点位清单、表计层级、数据频率、缺失率及与企业清单的对应关系。")
    if theme_counts.get("设备与系统节能"):
        opportunities.append("优先排查空压、蒸汽、泵风机、余热等运行改善项目，先形成基线和可验证节能量。")
        data_tasks.append("收集设备额定参数、负荷率、运行小时、改造前后能耗、停产影响和报价依据。")
    if theme_counts.get("资源循环"):
        opportunities.append("以水量、热量和副产物流向为基础，识别园区公共设施和企业间协同项目。")
        data_tasks.append("建立水、热、固废和副产物的来源—品质—规模—时间匹配表。")
    if theme_counts.get("清洁供能"):
        opportunities.append("清洁供能项目应在负荷、网架、消纳、计量结算和环境属性核清后进入专项论证。")
        data_tasks.append("补充15分钟或小时负荷曲线、可用场地、接入条件、消纳比例、绿证或绿电合同资料。")
    if theme_counts.get("交通与物流"):
        opportunities.append("把充换电、重卡和园区物流纳入场景项目库，明确车辆规模、里程、补能利用率和运营主体。")
        data_tasks.append("补充车辆清单、年行驶里程、燃料或电耗、补能设施利用率及运输组织方案。")
    if theme_counts.get("项目与资金"):
        opportunities.append("将资金政策与项目参数表联动，明确适用对象、申报窗口、投资主体和可计量绩效。")

    if sources and sources.most_common(1)[0][1] / total > 0.40:
        constraints.append("本期来源集中度偏高，需补充园区管委会、企业、公共设施运营方和地方主管部门的独立材料。")
    if policy_count / total > 0.35:
        constraints.append("政策标准记录占比仍偏高；下一轮采集应优先补充项目进度、设施参数和运行结果。")
    if numeric_count and not linked_park_count:
        constraints.append("部分记录含有数字，但尚未完成园区对象、统计年度和空间边界核验，不能直接写入园区指标。")
    if related_material_count:
        constraints.append(f"有{related_material_count}份补充来源被归并到主事件下，报告不再重复列示，但原始链接继续保留。")
    constraints.append("公开资料用于发现线索和形成核查任务；正式核算仍要求同一边界、同一年度、同一单位和可追溯凭证。")

    no_regret = [
        "确认园区法定边界、纳入企业清单和基准年，建立统一园区主键。",
        "完善分级计量、能源平衡和数据责任表，先处理缺失、重复和口径不一致。",
        "优先排查计量、空压、蒸汽、泵风机、余热和水回用，形成可验证的低风险项目。",
        "所有候选项目保留基线、计算方法、报价来源、实施主体和测量验证边界。",
    ]

    balance_rows = []
    for category in CATEGORY_ORDER:
        actual = categories.get(category, 0)
        balance_rows.append({
            "category": category,
            "count": actual,
            "actual_share": actual / total,
            "target_share": float(target.get(category, 0)),
        })

    return {
        "summary": summary,
        "opportunities": opportunities or ["继续补充园区与设施一手资料，形成可复核的案例和项目参数。"],
        "constraints": constraints,
        "data_tasks": data_tasks or ["补充园区建设边界、企业清单、基准年能源和排放台账。"],
        "no_regret": no_regret,
        "category_counts": dict(categories),
        "source_counts": dict(sources.most_common()),
        "source_level_counts": dict(levels),
        "theme_counts": dict(theme_counts.most_common()),
        "quality_metrics": quality_metrics,
        "balance_rows": balance_rows,
    }

def daily_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    limit = int(_content_policy().get("daily_limit", 12))
    rows = _balanced_select(records, days=2, limit=limit)
    latest = max((r.get("published_date", "") for r in rows), default=date.today().isoformat())
    return {
        "report_type": "daily", "generated_at": iso_now(), "report_date": latest,
        "record_count": len(rows), "records": rows, "analysis": _editorial_analysis(rows),
        "note": "按园区相关性、来源层级和记录完整度筛选；涉及投资、排放和绩效时回到原文与园区台账。",
        "screenshots": ["../assets/report_screenshots/site-overview.png", "../assets/report_screenshots/map-and-detail.png"],
    }


def weekly_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    limit = int(_content_policy().get("weekly_limit", 28))
    rows = _balanced_select(records, days=7, limit=limit)
    latest = max((r.get("published_date", "") for r in rows), default=date.today().isoformat())
    analysis = _editorial_analysis(rows)
    return {
        "report_type": "weekly", "generated_at": iso_now(), "report_date": latest,
        "record_count": len(rows), "records": rows, "analysis": analysis,
        "topic_counts": analysis["category_counts"], "source_counts": analysis["source_counts"],
        "note": "周报用于识别建设进展、技术设施、规则变化和下一步数据任务，不等同于园区绩效统计。",
        "screenshots": ["../assets/report_screenshots/site-overview.png", "../assets/report_screenshots/map-and-detail.png", "../assets/report_screenshots/five-questions.png"],
    }


def _records_by_category(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {cat: [] for cat in CATEGORY_ORDER}
    for row in rows:
        grouped.setdefault(str(row.get("category") or row.get("topic") or "其他重要动态"), []).append(row)
    return grouped


def intelligence_markdown(payload: dict[str, Any], title: str) -> str:
    analysis = payload.get("analysis", {})
    lines = [
        f"# {title}", "", f"- 报告日期：{payload.get('report_date')}", f"- 生成时间：{payload.get('generated_at')}",
        f"- 入选记录：{payload.get('record_count')} 条", "", f"> {payload.get('note', '')}", "",
        "## 本期摘要", "",
    ]
    lines.extend([f"- {x}" for x in analysis.get("summary", [])])
    lines.extend(["", "## 数据质量摘要", "", markdown_table(["项目", "数量", "说明"], [[m.get("label"), m.get("value"), m.get("note")] for m in analysis.get("quality_metrics", [])]), ""])
    lines.extend(["## 分类结构", "", markdown_table(["分类", "记录数", "实际占比", "参考占比"], [[r.get("category"), r.get("count"), f"{r.get('actual_share',0):.0%}", f"{r.get('target_share',0):.0%}"] for r in analysis.get("balance_rows", [])]), ""])
    if analysis.get("theme_counts"):
        lines.extend(["## 工作主题", "", markdown_table(["主题", "涉及记录"], [[k, v] for k, v in analysis.get("theme_counts", {}).items()]), ""])
    grouped = _records_by_category(payload.get("records", []))
    for category in CATEGORY_ORDER:
        rows = grouped.get(category, [])
        if not rows:
            continue
        lines.extend([f"## {category}", ""])
        for index, row in enumerate(rows, 1):
            lines.extend([
                f"### {index}. {row.get('title', '未命名记录')}", "",
                f"- 日期：{row.get('published_date', '—')}",
                f"- 来源：{row.get('publisher') or row.get('source_name') or '—'}",
                f"- 摘要：{row.get('summary', '')}",
                f"- 用途边界：{row.get('why', '')}",
                f"- 原文：{row.get('url', '')}", "",
            ])
    for heading, key in (("对经开区的机会", "opportunities"), ("约束与风险", "constraints"), ("下一步补数任务", "data_tasks"), ("无悔工作清单", "no_regret")):
        lines.extend([f"## {heading}", ""])
        lines.extend([f"- {x}" for x in analysis.get(key, [])])
        lines.append("")
    lines.extend(["## 使用边界", "", "公开记录用于发现线索、比较结构和组织数据任务。正式核算、排名和投资决策必须使用同边界、同年度、可追溯的园区数据。", ""])
    return "\n".join(lines)


def _report_css() -> str:
    return """
    :root{--ink:#1e2925;--muted:#68736d;--line:#d9dfda;--paper:#fff;--soft:#f4f6f3;--accent:#2f6650}
    *{box-sizing:border-box}body{margin:0;background:#eef1ed;color:var(--ink);font-family:"Noto Serif SC","Songti SC",SimSun,serif;line-height:1.72}
    main{max-width:980px;margin:30px auto;background:var(--paper);padding:48px 56px;box-shadow:0 12px 36px rgba(24,40,33,.08)}
    h1{font-size:30px;margin:0 0 8px}h2{font-size:21px;border-top:1px solid var(--line);padding-top:22px;margin-top:30px}h3{font-size:17px;margin-bottom:6px}
    p,li{font-size:14px}.meta{color:var(--muted);font-size:13px}.summary{border-left:3px solid var(--accent);background:var(--soft);padding:14px 18px;margin:20px 0}
    .record{padding:14px 0;border-bottom:1px solid var(--line)}.record h3{margin:0 0 6px}.record p{margin:5px 0}
    table{width:100%;border-collapse:collapse;font-size:13px}th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}th{background:var(--soft)}
    a{color:var(--accent);text-decoration:none}.figures{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.figures figure{margin:0}.figures img{width:100%;border:1px solid var(--line)}figcaption{font-size:12px;color:var(--muted);margin-top:5px}
    .avoid{break-inside:avoid}.footer-note{margin-top:28px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
    @media print{body{background:#fff}main{box-shadow:none;margin:0;max-width:none;padding:18mm 16mm}a{color:#000}.figures{grid-template-columns:1fr 1fr}@page{size:A4;margin:0}}
    """


def intelligence_html(payload: dict[str, Any], title: str) -> str:
    analysis = payload.get("analysis", {})
    grouped = _records_by_category(payload.get("records", []))
    sections = []
    for category in CATEGORY_ORDER:
        rows = grouped.get(category, [])
        if not rows:
            continue
        cards = []
        for row in rows:
            related = row.get("related_materials") or []
            related_text = f"<p class='meta'>合并了 {len(related)} 条重复或转发材料。</p>" if related else ""
            cards.append(f"""<article class="record avoid"><h3>{html.escape(str(row.get('title','未命名记录')))}</h3><p class="meta">{html.escape(str(row.get('published_date','—')))} · {html.escape(str(row.get('publisher') or row.get('source_name') or '—'))}</p><p>{html.escape(str(row.get('summary','')))}</p><p><strong>用途边界：</strong>{html.escape(str(row.get('why','')))}</p>{related_text}<p><a href="{html.escape(str(row.get('url','')))}" target="_blank" rel="noopener">查看原文</a></p></article>""")
        sections.append(f"<h2>{html.escape(category)}</h2>{''.join(cards)}")
    screenshots = payload.get("screenshots", [])
    figures = ""
    if screenshots:
        captions = ["平台首页与数据快照", "园区地图与资料卡", "五问工作台与测算入口"]
        figures = "<h2>平台界面快照</h2><div class='figures'>" + "".join(f"<figure><img src='{html.escape(src)}' alt='{captions[i] if i < len(captions) else '平台界面'}'><figcaption>{captions[i] if i < len(captions) else '平台界面'}</figcaption></figure>" for i, src in enumerate(screenshots)) + "</div>"
    def ul(key: str) -> str:
        return "<ul>" + "".join(f"<li>{html.escape(str(x))}</li>" for x in analysis.get(key, [])) + "</ul>"
    quality_table = "<table><tr><th>项目</th><th>数量</th><th>说明</th></tr>" + "".join(f"<tr><td>{html.escape(str(m.get('label','')))}</td><td>{m.get('value',0)}</td><td>{html.escape(str(m.get('note','')))}</td></tr>" for m in analysis.get("quality_metrics", [])) + "</table>"
    topic_table = "<table><tr><th>分类</th><th>记录数</th><th>实际占比</th><th>参考占比</th></tr>" + "".join(f"<tr><td>{html.escape(str(r.get('category','')))}</td><td>{r.get('count',0)}</td><td>{r.get('actual_share',0):.0%}</td><td>{r.get('target_share',0):.0%}</td></tr>" for r in analysis.get("balance_rows", [])) + "</table>"
    theme_table = "<table><tr><th>工作主题</th><th>涉及记录</th></tr>" + "".join(f"<tr><td>{html.escape(str(k))}</td><td>{v}</td></tr>" for k, v in analysis.get("theme_counts", {}).items()) + "</table>" if analysis.get("theme_counts") else ""
    body = f"""<main><p><a href="../index.html#reports">← 返回平台</a></p><h1>{html.escape(title)}</h1><p class="meta">报告日期：{html.escape(str(payload.get('report_date')))}　生成时间：{html.escape(str(payload.get('generated_at')))}　入选记录：{payload.get('record_count')}</p><div class="summary">{''.join(f'<p>{html.escape(str(x))}</p>' for x in analysis.get('summary', []))}</div>{figures}<h2>数据质量摘要</h2>{quality_table}<h2>分类结构</h2>{topic_table}{'<h2>工作主题</h2>'+theme_table if theme_table else ''}{''.join(sections)}<h2>对经开区的机会</h2>{ul('opportunities')}<h2>约束与风险</h2>{ul('constraints')}<h2>下一步补数任务</h2>{ul('data_tasks')}<h2>无悔工作清单</h2>{ul('no_regret')}<div class="footer-note">公开记录用于发现线索、比较结构和组织数据任务。正式核算、排名和投资决策必须使用同边界、同年度、可追溯的园区数据。</div></main>"""
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_report_css()}</style></head><body>{body}</body></html>"


def _display(value: Any) -> str:
    return "—" if value is None or value == "" else str(value)


def feasibility_markdown(result: dict[str, Any]) -> str:
    mode_label = {"formal": "正式初筛", "data_completion": "数据补齐", "demonstration": "演示场景"}.get(result.get("mode"), "前期筛查")
    lines = [
        f"# {result.get('park_name','园区')}零碳建设可行性初筛报告", "",
        f"- 基准年：{result.get('baseline_year') or '待确认'}", f"- 生成模式：{mode_label}",
        f"- 结论：{result.get('feasibility',{}).get('conclusion','—')}", "",
        "> 本报告用于前期筛查和项目排序，不替代节能审查、环评、接入系统审查、工程可研或投资决策。", "",
    ]
    for question, content in result.get("five_questions", {}).items():
        lines.extend([f"## {question}", "", str(content.get("answer", "")), ""])
        if content.get("tasks"):
            lines.append(markdown_table(["字段", "责任部门", "最低材料", "建议时限"], [[t.get("name"), t.get("owner"), t.get("minimum_material"), t.get("due")] for t in content["tasks"]])); lines.append("")
        if content.get("rows"):
            lines.append(markdown_table(["指标", "现状", "目标", "差距", "状态"], [[_display(r.get("metric")), _display(r.get("current")), _display(r.get("target")), _display(r.get("gap")), _display(r.get("status"))] for r in content["rows"]])); lines.append("")
        if content.get("recommendations"):
            lines.append(markdown_table(["层级", "建议", "对应差距", "前置数据", "主要责任方"], [[r.get("tier"), r.get("measure"), "、".join(r.get("matched_gaps", [])), r.get("prerequisites"), r.get("stakeholders")] for r in content["recommendations"]])); lines.append("")
        portfolio = content.get("portfolio")
        if portfolio:
            lines.extend([f"- 预算：{portfolio.get('budget_10k_cny',0):,.2f} 万元", f"- 入选投资：{portfolio.get('capex_10k_cny',0):,.2f} 万元", f"- 年减排：{portfolio.get('annual_abatement_tco2',0):,.2f} tCO₂", f"- 年净收益：{portfolio.get('annual_net_benefit_10k_cny',0):,.2f} 万元", f"- 目标缺口：{portfolio.get('target_gap_tco2',0):,.2f} tCO₂/年", ""])
            lines.append(markdown_table(["项目", "投资/万元", "年减排/tCO₂", "年净收益/万元", "回收期/年", "参数证据"], [[p.get("name"), p.get("capex_10k_cny"), p.get("annual_abatement_tco2"), p.get("annual_net_benefit_10k_cny"), p.get("simple_payback_years"), p.get("evidence_level")] for p in portfolio.get("selected_projects", [])])); lines.append("")
            if portfolio.get("sensitivity"):
                lines.extend(["### 关键参数敏感性", "", markdown_table(["情景", "投资/万元", "年减排/tCO₂", "年净收益/万元", "回收期/年", "参数变化"], [[r.get("name"), r.get("capex_10k_cny"), r.get("annual_abatement_tco2"), r.get("annual_net_benefit_10k_cny"), r.get("simple_payback_years"), r.get("note")] for r in portfolio.get("sensitivity", [])]), ""])
    lines.extend(["## 关键风险", "", markdown_table(["维度", "等级", "发现", "建议动作"], [[r.get("dimension"), r.get("level"), r.get("finding"), r.get("action")] for r in result.get("feasibility", {}).get("risks", [])]), ""])
    return "\n".join(lines)


def feasibility_html(result: dict[str, Any]) -> str:
    sections = []
    for question, content in result.get("five_questions", {}).items():
        inner = f"<p>{html.escape(str(content.get('answer','')))}</p>"
        if content.get("tasks"):
            inner += "<table><tr><th>字段</th><th>责任部门</th><th>最低材料</th><th>时限</th></tr>" + "".join(f"<tr><td>{html.escape(str(t.get('name','')))}</td><td>{html.escape(str(t.get('owner','')))}</td><td>{html.escape(str(t.get('minimum_material','')))}</td><td>{html.escape(str(t.get('due','')))}</td></tr>" for t in content["tasks"]) + "</table>"
        if content.get("rows"):
            inner += "<table><tr><th>指标</th><th>现状</th><th>目标</th><th>差距</th><th>状态</th></tr>" + "".join(f"<tr><td>{html.escape(str(r.get('metric','')))}</td><td>{html.escape(_display(r.get('current')))}</td><td>{html.escape(_display(r.get('target')))}</td><td>{html.escape(_display(r.get('gap')))}</td><td>{html.escape(str(r.get('status','')))}</td></tr>" for r in content["rows"]) + "</table>"
        if content.get("recommendations"):
            inner += "<table><tr><th>层级</th><th>建议</th><th>对应差距</th><th>前置数据</th><th>责任方</th></tr>" + "".join(f"<tr><td>{html.escape(str(r.get('tier','')))}</td><td>{html.escape(str(r.get('measure','')))}</td><td>{html.escape('、'.join(r.get('matched_gaps', [])))}</td><td>{html.escape(str(r.get('prerequisites','')))}</td><td>{html.escape(str(r.get('stakeholders','')))}</td></tr>" for r in content["recommendations"]) + "</table>"
        portfolio = content.get("portfolio")
        if portfolio:
            inner += f"<div class='summary'><strong>入选投资：</strong>{portfolio.get('capex_10k_cny',0):,.2f}万元　<strong>年减排：</strong>{portfolio.get('annual_abatement_tco2',0):,.2f}tCO₂　<strong>目标缺口：</strong>{portfolio.get('target_gap_tco2',0):,.2f}tCO₂/年</div>"
            inner += "<table><tr><th>项目</th><th>投资/万元</th><th>年减排/tCO₂</th><th>年净收益/万元</th><th>参数证据</th></tr>" + "".join(f"<tr><td>{html.escape(str(p.get('name','')))}</td><td>{p.get('capex_10k_cny')}</td><td>{p.get('annual_abatement_tco2')}</td><td>{p.get('annual_net_benefit_10k_cny')}</td><td>{html.escape(str(p.get('evidence_level','')))}</td></tr>" for p in portfolio.get("selected_projects", [])) + "</table>"
            if portfolio.get("sensitivity"):
                inner += "<h3>关键参数敏感性</h3><table><tr><th>情景</th><th>投资/万元</th><th>年减排/tCO₂</th><th>年净收益/万元</th><th>回收期/年</th></tr>" + "".join(f"<tr><td>{html.escape(str(r.get('name','')))}<br><small>{html.escape(str(r.get('note','')))}</small></td><td>{r.get('capex_10k_cny')}</td><td>{r.get('annual_abatement_tco2')}</td><td>{r.get('annual_net_benefit_10k_cny')}</td><td>{_display(r.get('simple_payback_years'))}</td></tr>" for r in portfolio.get("sensitivity", [])) + "</table>"
        sections.append(f"<h2>{html.escape(question)}</h2>{inner}")
    risks = "<table><tr><th>维度</th><th>等级</th><th>发现</th><th>建议动作</th></tr>" + "".join(f"<tr><td>{html.escape(str(r.get('dimension','')))}</td><td>{html.escape(str(r.get('level','')))}</td><td>{html.escape(str(r.get('finding','')))}</td><td>{html.escape(str(r.get('action','')))}</td></tr>" for r in result.get("feasibility", {}).get("risks", [])) + "</table>"
    mode_label = {"formal": "正式初筛", "data_completion": "数据补齐", "demonstration": "演示场景"}.get(result.get("mode"), "前期筛查")
    body = f"<main><p><a href='../index.html#cost'>← 返回平台</a></p><h1>{html.escape(str(result.get('park_name','园区')))}零碳建设可行性初筛报告</h1><p class='meta'>基准年：{html.escape(str(result.get('baseline_year') or '待确认'))}　生成模式：{html.escape(mode_label)}</p><div class='summary'><strong>结论：</strong>{html.escape(str(result.get('feasibility',{}).get('conclusion','—')))}<br>{html.escape(str(result.get('feasibility',{}).get('decision_boundary','')))}</div><div class='figures'><figure><img src='../assets/report_screenshots/five-questions.png' alt='五问工作台'><figcaption>数据准备、差距核算与投资测算入口</figcaption></figure><figure><img src='../assets/report_screenshots/map-and-detail.png' alt='园区资料卡'><figcaption>园区点位与公开资料卡</figcaption></figure></div>{''.join(sections)}<h2>关键风险</h2>{risks}<div class='footer-note'>所有减排量、投资和收益必须追溯到项目参数、原始凭证与测量验证边界。</div></main>"
    title = f"{result.get('park_name','园区')}可行性初筛报告"
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_report_css()}</style></head><body>{body}</body></html>"


def write_intelligence_reports(records: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    daily, weekly = daily_payload(records), weekly_payload(records)
    files = []
    for kind, payload, title in (("daily", daily, "零碳园区公开信息日报"), ("weekly", weekly, "零碳园区公开信息周报")):
        stem = f"{kind}-{payload['report_date']}"
        json_path, md_path, html_path = output_dir / f"{stem}.json", output_dir / f"{stem}.md", output_dir / f"{stem}.html"
        write_json(json_path, payload)
        md_path.write_text(intelligence_markdown(payload, title), encoding="utf-8")
        html_path.write_text(intelligence_html(payload, title), encoding="utf-8")
        for suffix, src in (("json", json_path), ("md", md_path), ("html", html_path)):
            (output_dir / f"{kind}-latest.{suffix}").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        files.append({"type": kind, "date": payload["report_date"], "html": f"reports/{kind}-latest.html", "markdown": f"reports/{kind}-latest.md", "json": f"reports/{kind}-latest.json", "pdf": f"reports/{kind}-latest.pdf", "record_count": payload["record_count"]})
    return {"generated_at": iso_now(), "reports": files}


def write_feasibility_report(result: dict[str, Any], output_dir: Path, stem: str = "feasibility-latest") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path, html_path = output_dir / f"{stem}.json", output_dir / f"{stem}.md", output_dir / f"{stem}.html"
    write_json(json_path, result)
    md_path.write_text(feasibility_markdown(result), encoding="utf-8")
    html_path.write_text(feasibility_html(result), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "html": str(html_path), "pdf": str(output_dir / f"{stem}.pdf")}

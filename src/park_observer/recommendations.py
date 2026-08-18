from __future__ import annotations

from typing import Any

from .utils import truthy

GAP_TERMS: dict[str, tuple[str, ...]] = {
    "单位能耗碳排放": ("计量", "能碳管理", "电机", "泵", "风机", "空压", "蒸汽", "余热", "工艺优化", "能源管理"),
    "园区企业产出产品单位能耗": ("电机", "泵", "风机", "空压", "蒸汽", "炉窑", "工艺优化", "设备更新", "能效"),
    "清洁能源消费占比": ("分布式光伏", "绿电", "储能", "微电网", "源网荷储", "热泵", "电气化"),
    "工业固体废弃物综合利用率": ("固废", "工业共生", "副产物", "资源化", "循环利用"),
    "余热/余冷/余压综合利用率": ("余热", "余压", "余冷", "热泵", "蒸汽", "凝结水"),
    "工业用水重复利用率": ("水回用", "再生水", "废水", "循环水", "中水"),
}

STAKEHOLDER_BY_TEXT = {
    "计量": "园区管委会、公共设施运营方、重点用能企业",
    "能碳管理": "园区管委会、能源运营方、重点用能企业",
    "电机": "重点用能企业",
    "空压": "重点用能企业",
    "蒸汽": "热力运营方、用汽企业",
    "余热": "能源运营方、供热企业、用热企业",
    "水回用": "水务运营方、用水企业",
    "固废": "园区管委会、产废企业、资源化企业",
    "工业共生": "园区管委会、上下游企业",
    "绿电": "能源运营方、用电企业、电网企业",
    "储能": "能源运营方、用电企业",
    "光伏": "园区业主、能源运营方、用电企业",
}


def _measure_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(k, "")) for k in ("一级方向", "二级措施", "对象/工艺", "减排计算逻辑", "备注"))


def _primary_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(k, "")) for k in ("一级方向", "二级措施", "对象/工艺"))


def _stakeholder(text: str) -> str:
    for term, owner in STAKEHOLDER_BY_TEXT.items():
        if term in text:
            return owner
    return "园区管委会、相关设施运营方和实施企业"


def _tier(primary_text: str, constraints: str = "") -> str:
    conditional = ("绿电", "储能", "微电网", "光伏", "热泵", "电锅炉", "电窑炉", "氢", "CCUS", "原料替代", "药剂替代")
    priority_actions = ("计量", "能碳管理", "电机", "泵", "风机", "空压", "蒸汽系统", "凝结水", "维护", "水回用", "工业共生", "余热回收")
    if any(x in primary_text for x in conditional):
        return "条件实施型"
    if any(x in primary_text for x in priority_actions):
        return "基础改进型"
    if any(x in constraints for x in ("产品质量", "工艺安全", "改造空间", "并网", "电网容量")):
        return "条件实施型"
    return "专项论证型"


def build_reduction_recommendations(
    gap_result: dict[str, Any] | None,
    measures: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Build traceable measure options without inventing project benefits.

    Measure options are tied to explicit gap rows. Quantitative abatement is not
    provided unless the user later supplies project parameters in the cost tool.
    """
    gap_rows = (gap_result or {}).get("rows", [])
    active_metrics = [
        str(r.get("metric")) for r in gap_rows
        if r.get("status") in {"未达到", "缺数据", "未完成判断", "待确认"}
    ]
    if not active_metrics:
        active_metrics = ["单位能耗碳排放", "园区企业产出产品单位能耗"]

    industry = str(payload.get("industry") or payload.get("industry_group") or "全部")
    green_ready = truthy(payload.get("green_power_conditions_confirmed"))
    ranked: list[dict[str, Any]] = []
    for row in measures:
        text = _measure_text(row)
        primary = _primary_text(row)
        calculation = str(row.get("减排计算逻辑") or "")
        remarks = str(row.get("备注") or "")
        metric_scores: list[tuple[str, int]] = []
        for metric in active_metrics:
            terms = GAP_TERMS.get(metric, ())
            match_score = 0
            if any(term in primary for term in terms):
                match_score += 3
            if any(term in calculation for term in terms):
                match_score += 2
            if any(term in remarks for term in terms):
                match_score += 1
            if match_score >= 2:
                metric_scores.append((metric, match_score))
        metric_scores.sort(key=lambda item: (-item[1], active_metrics.index(item[0])))
        matched = [metric for metric, _ in metric_scores[:3]]
        if not matched:
            continue
        applicable = str(row.get("适用园区") or "全部")
        score = sum(value for _, value in metric_scores[:3]) + len(matched) * 2
        if "全部" in applicable or industry in applicable:
            score += 3
        constraints = str(row.get("主要约束") or "需结合现场条件核对")
        tier = _tier(primary, constraints)
        if tier == "基础改进型":
            score += 4
        if tier == "条件实施型" and not green_ready and any(x in text for x in ("绿电", "储能", "微电网", "光伏")):
            score -= 3
        prerequisites = str(row.get("关键输入参数") or "需补充项目基线、设备运行和边界参数")
        reason = f"对应差距：{'、'.join(matched)}"
        if tier == "基础改进型":
            reason += "；用于建立基线、排查明显能效损失并提高资源利用"
        elif tier == "条件实施型":
            reason += "；需先完成源荷、接入、场地或工艺条件核查"
        else:
            reason += "；适合作为中长期专项论证方向"
        ranked.append({
            "tech_id": row.get("tech_id"),
            "tier": tier,
            "direction": row.get("一级方向"),
            "measure": row.get("二级措施"),
            "matched_gaps": matched,
            "reason": reason,
            "prerequisites": prerequisites,
            "calculation": row.get("减排计算逻辑") or "基线活动量与改造后活动量之差乘相应排放因子",
            "economics": row.get("经济性指标") or "投资、运行成本、年度节省和寿命",
            "constraints": constraints,
            "stakeholders": _stakeholder(text),
            "parameter_status": row.get("参数状态") or "指南级",
            "score": score,
            "quantitative_note": "未取得项目实测参数前不填写确定减排量和投资额。",
        })
    ranked.sort(key=lambda x: (-int(x["score"]), {"基础改进型": 0, "条件实施型": 1, "专项论证型": 2}.get(str(x["tier"]), 3), str(x.get("tech_id") or "")))
    return ranked[:limit]

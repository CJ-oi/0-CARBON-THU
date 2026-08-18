from __future__ import annotations

from collections import Counter
from typing import Any

from .accounting import data_gate, economic_intensity, national_indicator_gaps
from .portfolio import annual_path, portfolio_sensitivity, project_from_dict, select_portfolio, stakeholder_summary
from .recommendations import build_reduction_recommendations
from .utils import safe_float, truthy


BASIC_MEASURE_KEYWORDS = ("计量", "能碳管理", "电机", "泵", "风机", "空压", "蒸汽", "凝结水", "余热", "水回用", "维护", "工业共生")
CONDITIONAL_MEASURE_KEYWORDS = ("光伏", "绿电", "储能", "微电网", "热泵", "电锅炉", "电窑炉", "氢")


def classify_measure(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(k, "")) for k in ("一级方向", "二级措施", "对象/工艺", "主要约束", "备注"))
    if any(term in text for term in CONDITIONAL_MEASURE_KEYWORDS):
        return "条件实施型"
    if any(term in text for term in BASIC_MEASURE_KEYWORDS):
        return "基础改进型"
    return "专项论证型"


def screen_measures(measures: list[dict[str, Any]], payload: dict[str, Any], limit: int = 18) -> list[dict[str, Any]]:
    industry = str(payload.get("industry") or payload.get("industry_group") or "全部")
    constraints = " ".join(str(x) for x in payload.get("constraints", []))
    scored = []
    for row in measures:
        applicable = str(row.get("适用园区") or "全部")
        category = classify_measure(row)
        score = 0
        reasons = []
        if "全部" in applicable or industry in applicable or any(token and token in applicable for token in industry.replace("/", "、").split("、")):
            score += 3
            reasons.append("适用产业匹配")
        if category == "基础改进型":
            score += 3
            reasons.append("对外部制度与能源条件依赖较小")
        if "绿电" in str(row.get("二级措施")) and not truthy(payload.get("green_power_conditions_confirmed")):
            score -= 2
            reasons.append("绿电边界、网架、计量与结算条件尚未确认")
        if constraints and any(term in constraints for term in str(row.get("主要约束") or "").split("、")):
            score -= 1
        item = {
            "tech_id": row.get("tech_id"),
            "category": category,
            "direction": row.get("一级方向"),
            "measure": row.get("二级措施"),
            "applicable": applicable,
            "object": row.get("对象/工艺"),
            "inputs": row.get("关键输入参数"),
            "abatement_logic": row.get("减排计算逻辑"),
            "economics": row.get("经济性指标"),
            "constraints": row.get("主要约束"),
            "maturity": row.get("成熟度"),
            "parameter_status": row.get("参数状态"),
            "score": score,
            "reason": "；".join(reasons) or "作为指南条目保留",
        }
        scored.append(item)
    return sorted(scored, key=lambda x: (-x["score"], x["category"], str(x["tech_id"])))[:limit]


def feasibility_risks(payload: dict[str, Any], gap_result: dict[str, Any] | None, portfolio: dict[str, Any] | None) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    gate = data_gate(payload)
    if str(payload.get("scenario_type") or "").strip().lower() in {"demonstration", "demo", "演示"}:
        risks.append({"dimension": "示范数据", "level": "高", "finding": "当前排放、指标和项目经济参数用于验证计算链路，并非某个园区的正式台账", "action": "用同边界、同年度的原始台账、报价和测量验证参数替换后重新运行"})
    if not gate.ready:
        risks.append({"dimension": "数据与边界", "level": "高", "finding": f"缺少{len(gate.missing)}项正式核算前置数据", "action": "先完成边界、企业清单、基准年和排放活动数据闭环"})
    else:
        risks.append({"dimension": "数据与边界", "level": "低", "finding": "正式核算门槛字段已提供", "action": "继续保留原始凭证、因子版本和复核记录"})
    if not truthy(payload.get("green_power_conditions_confirmed")):
        risks.append({"dimension": "绿电实践", "level": "中", "finding": "源荷匹配、网架、计量结算或责任边界未全部确认", "action": "绿电直连仅作为条件实施型路径，先开展负荷曲线与接入条件专项核查"})
    else:
        risks.append({"dimension": "绿电实践", "level": "低", "finding": "已确认基本接入与责任条件", "action": "进入电价、消纳、可靠性和合同风险测算"})
    project_rows = payload.get("projects") or []
    low_evidence = sum(1 for row in project_rows if str(row.get("evidence_level") or row.get("参数证据") or "").strip().lower() in {"指南级", "示例", "演示", "演示参数", "low", ""})
    if project_rows and low_evidence:
        risks.append({"dimension": "项目参数", "level": "中", "finding": f"{low_evidence}个项目仍使用指南级或未核验参数", "action": "取得供应商报价、能量平衡、节能量测量与验证边界后再转为投资建议"})
    if portfolio and not portfolio.get("meets_target"):
        risks.append({"dimension": "减排目标", "level": "高", "finding": f"当前组合仍有{portfolio.get('target_gap_tco2', 0):,.0f} tCO₂/年缺口", "action": "增加候选项目、调整预算或重新确认目标年度"})
    if gap_result:
        gaps = [r for r in gap_result.get("rows", []) if r.get("status") in {"未达到", "缺数据", "未完成判断"}]
        risks.append({"dimension": "标准差距", "level": "中" if gaps else "低", "finding": f"{len(gaps)}项指标仍有差距或缺数据", "action": "按核心指标优先、引导指标分项推进"})
    return risks


def assess(payload: dict[str, Any], measures: list[dict[str, Any]]) -> dict[str, Any]:
    gate = data_gate(payload)
    scenario_type = str(payload.get("scenario_type") or "").strip().lower()
    is_demonstration = scenario_type in {"demonstration", "demo", "演示"}
    mode = "demonstration" if is_demonstration else ("formal" if gate.ready else "data_completion")
    result: dict[str, Any] = {
        "park_name": payload.get("park_name") or "未命名园区",
        "baseline_year": payload.get("baseline_year"),
        "mode": mode,
        "gate": {"ready": gate.ready, "missing": list(gate.missing), "checked": list(gate.checked)},
        "five_questions": {},
    }
    result["five_questions"]["数据够不够"] = {
        "answer": ("已填入演示数据，用于验证计算链路；正式使用仍需替换为园区原始台账" if is_demonstration else ("数据已具备正式筛查条件" if gate.ready else "数据尚不足，先完成补数任务")),
        "readiness_pct": round(100 * len(gate.checked) / (len(gate.checked) + len(gate.missing))) if gate.checked or gate.missing else 0,
        "tasks": list(gate.missing),
    }
    result["five_questions"]["现状是什么"] = {
        "answer": "已形成同边界、同年度的排放基线" if gate.ready else "只能形成公开资料画像，不能形成正式绩效排名",
        "industry": payload.get("industry") or payload.get("industry_group") or "待确认",
        "boundary": "已确认" if truthy(payload.get("boundary_confirmed")) else "待确认",
        "baseline_year": payload.get("baseline_year") or "待确认",
    }

    gap_result = None
    economic = None
    if gate.ready:
        gap_result = national_indicator_gaps(payload)
        economic = economic_intensity(payload)
        result["five_questions"]["现状是什么"].update({
            "inventory": gap_result["inventory"],
            "energy_tce": gap_result["energy_tce"],
            "economic_intensity": economic,
        })
        result["five_questions"]["差距在哪里"] = {
            "answer": "已按国家试行指标形成差距表",
            "core_target": gap_result["core_target"],
            "annual_reduction_needed_tco2": gap_result["annual_reduction_needed_tco2"],
            "rows": gap_result["rows"],
        }
    else:
        result["five_questions"]["差距在哪里"] = {
            "answer": "边界和基线未闭合，暂不输出达标判断或排名",
            "rows": [],
        }

    screened = screen_measures(measures, payload)
    recommendations = build_reduction_recommendations(gap_result, measures, payload)
    result["five_questions"]["怎么减"] = {
        "answer": "已按指标差距、产业适用性和实施前置条件形成措施清单；未取得项目参数前不填写确定减排量和投资额",
        "recommendations": recommendations,
        "measures": screened,
        "counts": dict(Counter(row["tier"] for row in recommendations)) if recommendations else dict(Counter(row["category"] for row in screened)),
    }

    portfolio = None
    projects = [project_from_dict(row) for row in (payload.get("projects") or []) if row.get("project_id") or row.get("name") or row.get("项目名称")]
    if projects:
        budget = safe_float(payload.get("budget_10k_cny"), 0.0) or 0.0
        target = safe_float(payload.get("annual_target_tco2"), 0.0) or 0.0
        portfolio = select_portfolio(projects, budget, target, safe_float(payload.get("discount_rate"), 0.05) or 0.05)
        baseline_emissions = (gap_result or {}).get("inventory", {}).get("net_emissions_tco2", safe_float(payload.get("baseline_emissions_tco2"), 0.0) or 0.0)
        portfolio["stakeholders"] = stakeholder_summary(portfolio["selected_projects"])
        portfolio["annual_path"] = annual_path(portfolio["selected_projects"], baseline_emissions, int(payload.get("path_end_year") or 2030))
        portfolio["sensitivity"] = portfolio_sensitivity(portfolio["selected_projects"], float(portfolio.get("discount_rate") or 0.05))
        cost_answer = "已形成预算约束下的项目组合" if portfolio.get("meets_target") else "当前预算内无法完全满足目标，已给出最大减排组合和剩余缺口"
    else:
        cost_answer = "尚未提供可核验的项目投资、减排和收益参数，当前仅能提供项目参数模板"
    result["five_questions"]["花多少钱"] = {"answer": cost_answer, "portfolio": portfolio}

    risks = feasibility_risks(payload, gap_result, portfolio)
    high = sum(1 for row in risks if row["level"] == "高")
    medium = sum(1 for row in risks if row["level"] == "中")
    if is_demonstration:
        conclusion = "演示场景仅用于验证计算链路，不构成园区可行性结论"
    elif not gate.ready:
        conclusion = "暂不具备正式可行性测算条件"
    elif high:
        conclusion = "具备初步测算基础，但关键风险尚未关闭"
    elif medium:
        conclusion = "具备初步可行性，需通过专项可研和参数核验后决策"
    else:
        conclusion = "具备较完整的初步可行性条件"
    result["feasibility"] = {
        "conclusion": conclusion,
        "high_risk_count": high,
        "medium_risk_count": medium,
        "risks": risks,
        "decision_boundary": "本结果属于前期筛查和项目排序，不替代法定节能审查、环评、接入系统审查、工程可研或投资决策。",
    }
    return result

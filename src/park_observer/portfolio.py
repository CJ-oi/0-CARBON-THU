from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable

from .utils import safe_float, safe_int


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    category: str
    capex_10k_cny: float
    annual_abatement_tco2: float
    annual_saving_10k_cny: float
    annual_opex_10k_cny: float
    lifetime_years: int
    start_year: int
    stakeholders: tuple[str, ...] = ()
    maturity: str = "待核实"
    evidence_level: str = "指南级"
    prerequisites: tuple[str, ...] = ()
    mutex_group: str = ""

    @property
    def annual_net_benefit_10k_cny(self) -> float:
        return self.annual_saving_10k_cny - self.annual_opex_10k_cny


def project_from_dict(row: dict[str, Any]) -> Project:
    def split(value: Any) -> tuple[str, ...]:
        if isinstance(value, list):
            return tuple(str(x).strip() for x in value if str(x).strip())
        return tuple(x.strip() for x in str(value or "").replace("；", ";").replace(",", ";").split(";") if x.strip())
    return Project(
        project_id=str(row.get("project_id") or row.get("id") or "").strip(),
        name=str(row.get("name") or row.get("项目名称") or "未命名项目").strip(),
        category=str(row.get("category") or row.get("类别") or "其他").strip(),
        capex_10k_cny=float(safe_float(row.get("capex_10k_cny") or row.get("投资_万元"), 0.0) or 0.0),
        annual_abatement_tco2=float(safe_float(row.get("annual_abatement_tco2") or row.get("年减排_tCO2"), 0.0) or 0.0),
        annual_saving_10k_cny=float(safe_float(row.get("annual_saving_10k_cny") or row.get("年节省_万元"), 0.0) or 0.0),
        annual_opex_10k_cny=float(safe_float(row.get("annual_opex_10k_cny") or row.get("年运维_万元"), 0.0) or 0.0),
        lifetime_years=max(1, safe_int(row.get("lifetime_years") or row.get("寿命_年"), 10)),
        start_year=safe_int(row.get("start_year") or row.get("实施年份"), 2027),
        stakeholders=split(row.get("stakeholders") or row.get("利益相关方")),
        maturity=str(row.get("maturity") or row.get("成熟度") or "待核实"),
        evidence_level=str(row.get("evidence_level") or row.get("参数证据") or "指南级"),
        prerequisites=split(row.get("prerequisites") or row.get("前置项目")),
        mutex_group=str(row.get("mutex_group") or row.get("互斥组") or "").strip(),
    )


def annuity_factor(rate: float, years: int) -> float:
    if years <= 0:
        raise ValueError("project lifetime must be positive")
    return float(years) if rate == 0 else (1 - (1 + rate) ** (-years)) / rate


def project_metrics(project: Project, discount_rate: float = 0.05) -> dict[str, Any]:
    factor = annuity_factor(discount_rate, project.lifetime_years)
    npv_benefit = project.annual_net_benefit_10k_cny * factor
    npv_cost = project.capex_10k_cny - npv_benefit
    life_abatement = project.annual_abatement_tco2 * project.lifetime_years
    payback = None if project.annual_net_benefit_10k_cny <= 0 else project.capex_10k_cny / project.annual_net_benefit_10k_cny
    macc = None if life_abatement <= 0 else npv_cost * 10000 / life_abatement
    return {
        "project_id": project.project_id,
        "name": project.name,
        "category": project.category,
        "capex_10k_cny": round(project.capex_10k_cny, 4),
        "annual_abatement_tco2": round(project.annual_abatement_tco2, 4),
        "annual_net_benefit_10k_cny": round(project.annual_net_benefit_10k_cny, 4),
        "lifetime_years": project.lifetime_years,
        "start_year": project.start_year,
        "npv_cost_10k_cny": round(npv_cost, 4),
        "lifetime_abatement_tco2": round(life_abatement, 4),
        "macc_cny_per_tco2": None if macc is None else round(macc, 4),
        "simple_payback_years": None if payback is None else round(payback, 3),
        "stakeholders": list(project.stakeholders),
        "maturity": project.maturity,
        "evidence_level": project.evidence_level,
    }


def _valid_subset(selected: tuple[Project, ...]) -> bool:
    ids = {p.project_id for p in selected}
    groups: set[str] = set()
    for project in selected:
        if project.prerequisites and not set(project.prerequisites).issubset(ids):
            return False
        if project.mutex_group:
            if project.mutex_group in groups:
                return False
            groups.add(project.mutex_group)
    return True


def _aggregate(selected: tuple[Project, ...], discount_rate: float) -> dict[str, Any]:
    metrics = [project_metrics(p, discount_rate) for p in selected]
    capex = sum(m["capex_10k_cny"] for m in metrics)
    abatement = sum(m["annual_abatement_tco2"] for m in metrics)
    benefit = sum(m["annual_net_benefit_10k_cny"] for m in metrics)
    npv_cost = sum(m["npv_cost_10k_cny"] for m in metrics)
    life_abatement = sum(m["lifetime_abatement_tco2"] for m in metrics)
    macc = None if life_abatement <= 0 else npv_cost * 10000 / life_abatement
    return {
        "selected_projects": metrics,
        "project_ids": [p.project_id for p in selected],
        "capex_10k_cny": round(capex, 4),
        "annual_abatement_tco2": round(abatement, 4),
        "annual_net_benefit_10k_cny": round(benefit, 4),
        "npv_cost_10k_cny": round(npv_cost, 4),
        "lifetime_abatement_tco2": round(life_abatement, 4),
        "macc_cny_per_tco2": None if macc is None else round(macc, 4),
    }


def select_portfolio(projects: Iterable[Project], budget_10k_cny: float, annual_target_tco2: float, discount_rate: float = 0.05, *, max_projects: int = 24) -> dict[str, Any]:
    items = tuple(p for p in projects if p.capex_10k_cny >= 0 and p.annual_abatement_tco2 >= 0)
    if len(items) > max_projects:
        raise ValueError(f"exact portfolio search is limited to {max_projects} projects")
    if budget_10k_cny < 0 or annual_target_tco2 < 0:
        raise ValueError("budget and target must be non-negative")

    order = sorted(items, key=lambda p: (-(p.annual_abatement_tco2 / max(p.capex_10k_cny, 1e-6)), p.project_id))
    suffix_abatement = [0.0] * (len(order) + 1)
    for i in range(len(order) - 1, -1, -1):
        suffix_abatement[i] = suffix_abatement[i + 1] + order[i].annual_abatement_tco2

    best_meeting: dict[str, Any] | None = None
    best_fallback: dict[str, Any] | None = None

    def consider(selected: tuple[Project, ...]) -> None:
        nonlocal best_meeting, best_fallback
        if not _valid_subset(selected):
            return
        result = _aggregate(selected, discount_rate)
        result["meets_target"] = result["annual_abatement_tco2"] + 1e-9 >= annual_target_tco2
        if result["meets_target"]:
            key = (result["npv_cost_10k_cny"], result["capex_10k_cny"], -result["annual_abatement_tco2"], len(selected))
            if best_meeting is None or key < best_meeting["_key"]:
                result["_key"] = key
                best_meeting = result
        else:
            key = (-result["annual_abatement_tco2"], result["npv_cost_10k_cny"], result["capex_10k_cny"], len(selected))
            if best_fallback is None or key < best_fallback["_key"]:
                result["_key"] = key
                best_fallback = result

    def dfs(index: int, selected: tuple[Project, ...], capex: float, abatement: float) -> None:
        if capex > budget_10k_cny + 1e-9:
            return
        if index == len(order):
            consider(selected)
            return
        upper_abatement = abatement + suffix_abatement[index]
        if best_meeting is not None and upper_abatement + 1e-9 < annual_target_tco2:
            # A target-meeting solution already exists, so a branch that can no
            # longer reach the target cannot improve the preferred result.
            return
        if best_meeting is None and best_fallback is not None:
            best_fallback_abatement = float(best_fallback.get("annual_abatement_tco2", 0.0))
            if upper_abatement + 1e-9 < best_fallback_abatement:
                # Even the optimistic abatement bound cannot improve the best
                # fallback. Strict inequality preserves economic tie-breaking.
                return
        project = order[index]
        dfs(index + 1, selected + (project,), capex + project.capex_10k_cny, abatement + project.annual_abatement_tco2)
        dfs(index + 1, selected, capex, abatement)

    dfs(0, tuple(), 0.0, 0.0)
    result = best_meeting or best_fallback
    if result is None:
        result = _aggregate(tuple(), discount_rate)
        result["meets_target"] = annual_target_tco2 <= 0
    result.pop("_key", None)
    result["budget_10k_cny"] = budget_10k_cny
    result["annual_target_tco2"] = annual_target_tco2
    result["target_gap_tco2"] = round(max(0.0, annual_target_tco2 - result["annual_abatement_tco2"]), 4)
    result["discount_rate"] = discount_rate
    return result


def stakeholder_summary(selected_projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, float]] = {}
    for project in selected_projects:
        stakeholders = project.get("stakeholders") or ["待明确"]
        share = 1 / max(1, len(stakeholders))
        for stakeholder in stakeholders:
            row = rows.setdefault(stakeholder, {"project_count": 0, "capex_10k_cny": 0.0, "annual_net_benefit_10k_cny": 0.0, "annual_abatement_tco2": 0.0})
            row["project_count"] += 1
            row["capex_10k_cny"] += project["capex_10k_cny"] * share
            row["annual_net_benefit_10k_cny"] += project["annual_net_benefit_10k_cny"] * share
            row["annual_abatement_tco2"] += project["annual_abatement_tco2"] * share
    return [{"stakeholder": k, **{name: round(value, 4) for name, value in v.items()}} for k, v in sorted(rows.items())]


def annual_path(selected_projects: list[dict[str, Any]], baseline_emissions_tco2: float, end_year: int = 2030) -> list[dict[str, Any]]:
    if not selected_projects:
        return []
    first_year = min(int(p.get("start_year") or 2027) for p in selected_projects)
    rows = []
    cumulative = 0.0
    for year in range(first_year, end_year + 1):
        annual = sum(float(p.get("annual_abatement_tco2") or 0) for p in selected_projects if int(p.get("start_year") or first_year) <= year)
        cumulative += annual
        remaining = max(0.0, baseline_emissions_tco2 - annual)
        stage = "减碳"
        if baseline_emissions_tco2 > 0 and remaining / baseline_emissions_tco2 <= 0.1:
            stage = "近零碳"
        if remaining <= 1e-9:
            stage = "零碳（需核验剩余排放与抵消）"
        rows.append({"year": year, "annual_abatement_tco2": round(annual, 4), "cumulative_abatement_tco2": round(cumulative, 4), "remaining_emissions_tco2": round(remaining, 4), "stage": stage})
    return rows


def portfolio_sensitivity(selected_projects: list[dict[str, Any]], discount_rate: float = 0.05) -> list[dict[str, Any]]:
    """Evaluate the selected portfolio under transparent parameter scenarios.

    The scenarios are not forecasts. They show how the same selected project set
    responds to bounded changes in investment, annual saving, operating cost and
    annual abatement, so the reader can see whether the conclusion depends on a
    narrow set of assumptions.
    """
    scenarios = (
        {"name": "保守情景", "capex": 1.15, "saving": 0.80, "opex": 1.10, "abatement": 0.90,
         "note": "投资上浮15%，节省下降20%，运维上浮10%，减排下降10%"},
        {"name": "基准情景", "capex": 1.00, "saving": 1.00, "opex": 1.00, "abatement": 1.00,
         "note": "按当前录入参数"},
        {"name": "改善情景", "capex": 0.95, "saving": 1.10, "opex": 1.00, "abatement": 1.05,
         "note": "投资下降5%，节省上升10%，减排上升5%"},
    )
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        capex = abatement = annual_net = npv_cost = 0.0
        for project in selected_projects:
            life = max(1, int(project.get("lifetime_years") or 10))
            adjusted_capex = float(project.get("capex_10k_cny") or 0) * float(scenario["capex"])
            # selected project metrics already store net benefit; reconstructing
            # savings/opex is impossible here, so apply the conservative benefit
            # multiplier directly and document the convention.
            base_net = float(project.get("annual_net_benefit_10k_cny") or 0)
            benefit_factor = float(scenario["saving"]) / max(float(scenario["opex"]), 1e-9)
            adjusted_net = base_net * benefit_factor
            capex += adjusted_capex
            annual_net += adjusted_net
            abatement += float(project.get("annual_abatement_tco2") or 0) * float(scenario["abatement"])
            npv_cost += adjusted_capex - adjusted_net * annuity_factor(discount_rate, life)
        rows.append({
            "name": scenario["name"],
            "note": scenario["note"],
            "capex_10k_cny": round(capex, 4),
            "annual_abatement_tco2": round(abatement, 4),
            "annual_net_benefit_10k_cny": round(annual_net, 4),
            "npv_cost_10k_cny": round(npv_cost, 4),
            "simple_payback_years": None if annual_net <= 0 else round(capex / annual_net, 3),
        })
    return rows

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .utils import safe_float, safe_int, truthy


@dataclass(frozen=True)
class DataGateResult:
    ready: bool
    missing: tuple[dict[str, str], ...]
    checked: tuple[str, ...]


GATE_RULES = (
    ("park_name", "园区标准名称", "园区管委会", "正式园区名称及唯一标识"),
    ("boundary_confirmed", "核算边界", "园区管委会/自然资源", "批复四至、红线图或GIS文件"),
    ("enterprise_list_confirmed", "纳入企业清单", "园区管委会/市场监管", "企业名称、统一社会信用代码、行业及纳入状态"),
    ("baseline_year", "基准年", "园区统计/发改", "明确统计年度并与全部活动数据一致"),
    ("energy_tce", "综合能源消费量", "发改/统计/园区", "分能源品种台账、折标系数及汇总表"),
    ("scope1_tco2", "范围一排放", "重点企业/园区", "燃料和过程活动数据、排放因子及计算底稿"),
    ("scope2_tco2", "范围二排放", "供电/供热/园区", "购售电热台账、绿电凭证和排放因子版本"),
    ("process_tco2", "工业过程排放", "重点企业", "碳酸盐分解、化学反应或其他过程活动数据"),
)


def data_gate(payload: dict[str, Any]) -> DataGateResult:
    missing: list[dict[str, str]] = []
    checked: list[str] = []
    for key, name, owner, material in GATE_RULES:
        value = payload.get(key)
        is_ok = truthy(value) if key.endswith("confirmed") else value not in (None, "", 0, 0.0)
        if key == "process_tco2":
            is_ok = value not in (None, "")  # zero is a valid confirmed value
        if key in {"scope1_tco2", "scope2_tco2"}:
            is_ok = value not in (None, "")
        if is_ok:
            checked.append(key)
        else:
            missing.append({
                "field": key,
                "name": name,
                "priority": "P0",
                "owner": owner,
                "minimum_material": material,
                "due": "3个工作日",
            })
    return DataGateResult(ready=not missing, missing=tuple(missing), checked=tuple(checked))


def emissions_inventory(payload: dict[str, Any]) -> dict[str, float]:
    gate = data_gate(payload)
    if not gate.ready:
        raise ValueError("formal accounting requires a confirmed boundary, year, enterprise list and complete emissions data")
    scope1 = safe_float(payload.get("scope1_tco2"), 0.0) or 0.0
    scope2 = safe_float(payload.get("scope2_tco2"), 0.0) or 0.0
    process = safe_float(payload.get("process_tco2"), 0.0) or 0.0
    removals = safe_float(payload.get("verified_removals_tco2"), 0.0) or 0.0
    total = scope1 + scope2 + process - removals
    if total < 0:
        raise ValueError("verified removals cannot exceed gross emissions in this screening model")
    return {
        "scope1_tco2": round(scope1, 4),
        "scope2_tco2": round(scope2, 4),
        "process_tco2": round(process, 4),
        "verified_removals_tco2": round(removals, 4),
        "gross_emissions_tco2": round(scope1 + scope2 + process, 4),
        "net_emissions_tco2": round(total, 4),
    }


def national_indicator_gaps(payload: dict[str, Any]) -> dict[str, Any]:
    inv = emissions_inventory(payload)
    energy_tce = safe_float(payload.get("energy_tce"), 0.0) or 0.0
    if energy_tce <= 0:
        raise ValueError("energy_tce must be positive")
    intensity = inv["net_emissions_tco2"] / energy_tce
    if 200_000 <= energy_tce < 1_000_000:
        target = 0.2
        scale_note = "综合能源消费量20万—100万吨标准煤"
    elif energy_tce >= 1_000_000:
        target = 0.3
        scale_note = "综合能源消费量100万吨标准煤及以上"
    else:
        target = None
        scale_note = "综合能源消费量低于20万吨标准煤；国家试行指标中的核心阈值需结合申报要求确认"
    rows: list[dict[str, Any]] = [{
        "metric": "单位能耗碳排放",
        "current": round(intensity, 6),
        "unit": "tCO₂/tce",
        "target": target,
        "gap": None if target is None else round(max(0.0, intensity - target), 6),
        "status": "待确认" if target is None else ("达到" if intensity <= target else "未达到"),
        "nature": "核心指标",
    }]
    product = str(payload.get("product_energy_status") or "未提供")
    rows.append({
        "metric": "园区企业产出产品单位能耗",
        "current": product,
        "unit": "状态",
        "target": "达到或优于二级能耗限额；不适用时说明",
        "gap": None,
        "status": "达到" if product in {"达标", "达到", "优于", "不适用"} else "未完成判断",
        "nature": "引导指标",
    })
    for field, metric, target_value in (
        ("clean_energy_pct", "清洁能源消费占比", 90.0),
        ("solid_waste_pct", "工业固体废弃物综合利用率", 80.0),
        ("waste_energy_pct", "余热/余冷/余压综合利用率", 50.0),
        ("water_reuse_pct", "工业用水重复利用率", 80.0),
    ):
        current = safe_float(payload.get(field))
        rows.append({
            "metric": metric,
            "current": current,
            "unit": "%",
            "target": target_value,
            "gap": None if current is None else round(max(0.0, target_value - current), 4),
            "status": "缺数据" if current is None else ("达到" if current >= target_value else "未达到"),
            "nature": "引导指标",
        })
    reductions_needed = None if target is None else max(0.0, inv["net_emissions_tco2"] - target * energy_tce)
    return {
        "inventory": inv,
        "energy_tce": energy_tce,
        "intensity_tco2_per_tce": round(intensity, 6),
        "core_target": target,
        "scale_note": scale_note,
        "annual_reduction_needed_tco2": None if reductions_needed is None else round(reductions_needed, 4),
        "rows": rows,
    }


def economic_intensity(payload: dict[str, Any]) -> dict[str, Any] | None:
    output = safe_float(payload.get("economic_output_10k_cny"))
    if output is None or output <= 0:
        return None
    inv = emissions_inventory(payload)
    return {
        "economic_output_10k_cny": output,
        "emissions_tco2_per_10k_cny": round(inv["net_emissions_tco2"] / output, 8),
    }

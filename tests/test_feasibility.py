from __future__ import annotations

import unittest

from park_observer.feasibility import assess, classify_measure


MEASURES = [
    {"tech_id": "T1", "一级方向": "数据基础", "二级措施": "分级计量与能碳管理", "适用园区": "全部", "对象/工艺": "公共设施", "关键输入参数": "点表", "减排计算逻辑": "基线对比", "经济性指标": "节省", "主要约束": "数据接口", "成熟度": "成熟", "参数状态": "指南级"},
    {"tech_id": "T2", "一级方向": "绿色供能", "二级措施": "绿电直连", "适用园区": "全部", "对象/工艺": "电力系统", "关键输入参数": "源荷曲线", "减排计算逻辑": "电量乘因子", "经济性指标": "电价", "主要约束": "网架、计量、结算", "成熟度": "条件成熟", "参数状态": "指南级"},
]


class FeasibilityTests(unittest.TestCase):
    def test_missing_data_returns_tasks_not_formal_gap(self) -> None:
        result = assess({"park_name": "测试园区"}, MEASURES)
        self.assertEqual(result["mode"], "data_completion")
        self.assertTrue(result["five_questions"]["数据够不够"]["tasks"])
        self.assertEqual(result["five_questions"]["差距在哪里"]["rows"], [])
        self.assertIn("暂不具备", result["feasibility"]["conclusion"])

    def test_formal_scenario_returns_portfolio(self) -> None:
        payload = {
            "park_name": "测试园区", "boundary_confirmed": True, "enterprise_list_confirmed": True,
            "baseline_year": 2025, "energy_tce": 500000, "scope1_tco2": 40000, "scope2_tco2": 70000,
            "process_tco2": 0, "budget_10k_cny": 120, "annual_target_tco2": 50,
            "projects": [{"project_id": "P1", "name": "设备改造", "capex_10k_cny": 100, "annual_abatement_tco2": 60,
                          "annual_saving_10k_cny": 20, "annual_opex_10k_cny": 2, "lifetime_years": 10, "start_year": 2027,
                          "evidence_level": "可研参数"}],
        }
        result = assess(payload, MEASURES)
        self.assertEqual(result["mode"], "formal")
        portfolio = result["five_questions"]["花多少钱"]["portfolio"]
        self.assertTrue(portfolio["meets_target"])
        self.assertEqual(portfolio["project_ids"], ["P1"])
        self.assertEqual(len(portfolio["sensitivity"]), 3)

    def test_green_power_is_conditional(self) -> None:
        self.assertEqual(classify_measure(MEASURES[1]), "条件实施型")

    def test_demonstration_scenario_is_not_formal_conclusion(self) -> None:
        payload = {
            "scenario_type": "demonstration", "park_name": "示范园区",
            "boundary_confirmed": True, "enterprise_list_confirmed": True,
            "baseline_year": 2025, "energy_tce": 500000, "scope1_tco2": 40000,
            "scope2_tco2": 70000, "process_tco2": 0,
            "projects": [{"project_id": "P1", "name": "示例项目", "capex_10k_cny": 100,
                          "annual_abatement_tco2": 60, "annual_saving_10k_cny": 20,
                          "annual_opex_10k_cny": 2, "lifetime_years": 10,
                          "evidence_level": "演示参数"}],
        }
        result = assess(payload, MEASURES)
        self.assertEqual(result["mode"], "demonstration")
        self.assertIn("不构成园区可行性结论", result["feasibility"]["conclusion"])
        self.assertTrue(any(r["dimension"] == "示范数据" for r in result["feasibility"]["risks"]))


if __name__ == "__main__":
    unittest.main()

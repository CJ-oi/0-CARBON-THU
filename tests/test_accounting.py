from __future__ import annotations

import unittest

from park_observer.accounting import data_gate, national_indicator_gaps


class AccountingTests(unittest.TestCase):
    def base(self) -> dict:
        return {
            "park_name": "示范园区",
            "boundary_confirmed": True,
            "enterprise_list_confirmed": True,
            "baseline_year": 2025,
            "energy_tce": 500000,
            "scope1_tco2": 40000,
            "scope2_tco2": 70000,
            "process_tco2": 0,
            "clean_energy_pct": 88,
            "product_energy_status": "达标",
            "solid_waste_pct": 82,
            "waste_energy_pct": 45,
            "water_reuse_pct": 85,
        }

    def test_missing_boundary_stops_formal_gate(self) -> None:
        payload = self.base()
        payload["boundary_confirmed"] = False
        result = data_gate(payload)
        self.assertFalse(result.ready)
        self.assertIn("boundary_confirmed", {row["field"] for row in result.missing})

    def test_zero_process_emissions_is_valid(self) -> None:
        result = data_gate(self.base())
        self.assertTrue(result.ready)

    def test_indicator_gaps(self) -> None:
        result = national_indicator_gaps(self.base())
        self.assertAlmostEqual(result["intensity_tco2_per_tce"], 0.22)
        self.assertEqual(result["core_target"], 0.2)
        self.assertAlmostEqual(result["annual_reduction_needed_tco2"], 10000)
        rows = {row["metric"]: row for row in result["rows"]}
        self.assertEqual(rows["单位能耗碳排放"]["status"], "未达到")
        self.assertEqual(rows["工业固体废弃物综合利用率"]["status"], "达到")
        self.assertEqual(rows["余热/余冷/余压综合利用率"]["gap"], 5)


if __name__ == "__main__":
    unittest.main()

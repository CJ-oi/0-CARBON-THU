from __future__ import annotations

import unittest

from park_observer.recommendations import build_reduction_recommendations
from park_observer.utils import PROJECT_ROOT, read_csv


class RecommendationTests(unittest.TestCase):
    def test_recommendations_are_gap_linked_and_non_numeric(self) -> None:
        measures = read_csv(PROJECT_ROOT / "data/technology_guidance.csv")
        result = build_reduction_recommendations(
            {"rows": [{"metric": "余热/余冷/余压综合利用率", "status": "未达到"}]},
            measures,
            {"industry": "全部", "green_power_conditions_confirmed": False},
        )
        self.assertTrue(result)
        self.assertTrue(any("余热" in str(row.get("measure")) or "蒸汽" in str(row.get("measure")) for row in result))
        self.assertTrue(all("未取得项目实测参数" in row["quantitative_note"] for row in result))


if __name__ == "__main__":
    unittest.main()

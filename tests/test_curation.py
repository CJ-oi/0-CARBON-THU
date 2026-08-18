from __future__ import annotations

import unittest

from park_observer.curation import collapse_duplicates, curate_record


class CurationTests(unittest.TestCase):
    def test_unrelated_innovation_policy_is_excluded(self) -> None:
        row = curate_record({
            "title": "北京经开区发布智能经济与脑机接口创新政策",
            "summary": "支持科技企业和创新创业活动。",
            "publisher": "北京经济技术开发区",
            "published_date": "2026-08-01",
            "url": "https://example.com/1",
        })
        self.assertEqual(row["relevance_status"], "exclude")

    def test_facility_record_precedes_notice_word(self) -> None:
        row = curate_record({
            "title": "关于推进园区余热回收与蒸汽系统节能改造的通知",
            "summary": "部署余热、凝结水和蒸汽管网改造项目。",
            "publisher": "某经济技术开发区",
            "published_date": "2026-08-01",
            "url": "https://example.com/2",
        })
        self.assertEqual(row["category"], "技术与设施")
        self.assertEqual(row["relevance_status"], "include")

    def test_same_event_is_collapsed(self) -> None:
        rows = [
            curate_record({"title": "广东推动绿电直连发展有关事项的通知", "summary": "园区绿电直连政策。", "publisher": "广东省发展改革委", "published_date": "2026-07-01", "url": "https://a.example/x"}),
            curate_record({"title": "广东省发展改革委关于推动绿电直连发展有关事项的通知", "summary": "园区绿电直连政策解读。", "publisher": "广东省能源局", "published_date": "2026-07-01", "url": "https://b.example/y"}),
        ]
        collapsed, count = collapse_duplicates(rows, threshold=0.72)
        self.assertEqual(len(collapsed), 1)
        self.assertEqual(count, 1)
        self.assertEqual(len(collapsed[0].get("related_materials", [])), 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from park_observer.archive import merge_records


class ArchiveTests(unittest.TestCase):
    def test_canonical_url_dedup_and_version(self) -> None:
        existing = [{
            "url": "http://example.com/a/?utm_source=x",
            "title": "旧标题",
            "summary": "旧摘要",
            "content_hash": "old",
            "published_date": "2026-08-01",
            "first_seen": "2026-08-01T00:00:00+00:00",
        }]
        incoming = [{
            "url": "https://EXAMPLE.com/a#top",
            "title": "新标题",
            "summary": "新摘要",
            "content_hash": "new",
            "published_date": "2026-08-02",
        }]
        rows, stats = merge_records(existing, incoming)
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(rows[0]["canonical_url"], "https://example.com/a")
        self.assertEqual(rows[0]["version_count"], 2)
        self.assertEqual(rows[0]["previous_content_hash"], "old")

    def test_archive_limit(self) -> None:
        incoming = [
            {"url": f"https://example.com/{i}", "title": str(i), "summary": "x", "published_date": f"2026-08-{i+1:02d}"}
            for i in range(4)
        ]
        rows, _ = merge_records([], incoming, max_records=3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["published_date"], "2026-08-04")


if __name__ == "__main__":
    unittest.main()

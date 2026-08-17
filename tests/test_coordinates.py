from __future__ import annotations

import unittest

from park_observer.utils import PROJECT_ROOT, read_csv


class CoordinateTests(unittest.TestCase):
    def test_coordinate_ranges_and_metadata(self) -> None:
        rows = read_csv(PROJECT_ROOT / "data/park_catalog.csv")
        self.assertEqual(len(rows), 79)
        for row in rows:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            self.assertGreaterEqual(lat, -90)
            self.assertLessEqual(lat, 90)
            self.assertGreaterEqual(lon, -180)
            self.assertLessEqual(lon, 180)
            self.assertTrue(row.get("coordinate_precision"))
            self.assertTrue(row.get("coordinate_status"))
        domestic = [row for row in rows if row.get("region_scope") == "国内园区"]
        self.assertTrue(all(70 <= float(row["longitude"]) <= 140 and 15 <= float(row["latitude"]) <= 55 for row in domestic))


if __name__ == "__main__":
    unittest.main()

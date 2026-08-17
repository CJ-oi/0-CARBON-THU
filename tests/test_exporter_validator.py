from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from park_observer.exporter import export_site
from park_observer.feasibility import assess
from park_observer.utils import PROJECT_ROOT, read_csv, read_json
from park_observer.validator import validate_site


class ExporterValidatorTests(unittest.TestCase):
    def test_build_and_validate_site(self) -> None:
        payload = read_json(PROJECT_ROOT / "data/assessments/example.json", {})
        result = assess(payload, read_csv(PROJECT_ROOT / "data/technology_guidance.csv"))
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "site"
            manifest = export_site(PROJECT_ROOT, output, feasibility_result=result)
            self.assertGreater(manifest["archive_records"], 0)
            validation = validate_site(output)
            self.assertTrue(validation["ok"], validation)
            dashboard = json.loads((output / "data/dashboard.json").read_text(encoding="utf-8"))
            self.assertEqual(len(dashboard["parks"]), 79)
            self.assertTrue((output / "reports/weekly-latest.html").exists())
            self.assertTrue((output / "reports/feasibility-latest.md").exists())


if __name__ == "__main__":
    unittest.main()

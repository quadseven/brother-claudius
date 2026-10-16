"""Keep the lane validation contract aligned with pull-request CI."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValidationContractTests(unittest.TestCase):
    def test_contract_runs_pull_request_checks_in_workflow_order(self) -> None:
        contract = (ROOT / ".loom" / "validation.conf").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        commands = (
            "python -m json.tool hooks/hooks.json >/dev/null",
            "bash -n hooks/scripts/*.sh",
            "sed -n '/<script>/,/<\\/script>/p' index.html | sed '1d;$d' | node --check -",
            "python -m unittest discover -s tests -v",
        )

        positions = [contract.index(command) for command in commands]
        self.assertEqual(positions, sorted(positions))
        for command in commands:
            with self.subTest(command=command):
                self.assertIn(command, workflow)
                self.assertIn(command, contract)
        self.assertIn(".github/workflows/test.yml", contract)
        self.assertIn("Validate hook configuration", contract)
        self.assertIn("Validate shell syntax", contract)
        self.assertIn("Validate landing-page JavaScript syntax", contract)
        self.assertIn("Run regression contracts", contract)


if __name__ == "__main__":
    unittest.main()

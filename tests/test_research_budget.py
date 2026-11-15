"""Offline tests for explicit research allocations (no model calls)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openprover.budget import Budget, ResearchBudget


class ResearchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_new_token_budget(self):
        budget = ResearchBudget(self.root, "tokens", 100)
        self.assertEqual(budget.state["allocation"], 1)
        self.assertEqual(budget.total_output_tokens, 0)
        self.assertFalse(budget.should_conclude())
        self.assertEqual(ResearchBudget.load_state(self.root)["status"], "running")

    def test_resume_restores_usage(self):
        first = ResearchBudget(self.root, "tokens", 100)
        first.add_output_tokens(40)
        first.save("paused")
        second = ResearchBudget(self.root, "tokens", 100, resume=True)
        self.assertEqual(second.total_output_tokens, 40)
        self.assertEqual(second.state["allocation"], 1)

    def test_resume_does_not_reset_deadline(self):
        with patch("openprover.budget.time.time", return_value=1000), \
             patch("openprover.budget.time.monotonic", return_value=100):
            ResearchBudget(self.root, "time", 100)
        with patch("openprover.budget.time.time", return_value=1040), \
             patch("openprover.budget.time.monotonic", return_value=500):
            resumed = ResearchBudget(self.root, "time", 100, resume=True)
            self.assertAlmostEqual(resumed.fraction_spent(), 0.4)
            self.assertEqual(resumed.state["started_at"], 1000)
        with patch("openprover.budget.time.time", return_value=1200):
            expired = ResearchBudget(self.root, "time", 100, resume=True)
            self.assertTrue(expired.is_exhausted())

    def test_continuation_grants_only_new_allocation(self):
        first = ResearchBudget(self.root, "tokens", 100)
        first.add_output_tokens(105)
        first.save("finished")
        (self.root / "WHITEBOARD.md").write_text("Keep my findings")
        second = ResearchBudget(self.root, "tokens", 50, resume=True, renew=True)
        self.assertEqual(second.state["allocation"], 2)
        self.assertEqual(second.total_output_tokens, 0)
        self.assertEqual(second.limit, 50)
        self.assertEqual((self.root / "WHITEBOARD.md").read_text(), "Keep my findings")
        previous = json.loads((self.root / "reports/allocation_001.json").read_text())
        self.assertEqual(previous["output_tokens"], 105)

    def test_continuation_can_switch_budget_kind(self):
        first = ResearchBudget(self.root, "tokens", 100)
        first.save("finished")
        second = ResearchBudget(self.root, "time", 60, resume=True, renew=True)
        self.assertEqual(second.mode, "time")
        self.assertFalse(second.is_exhausted())

    def test_cannot_renew_active_allocation(self):
        ResearchBudget(self.root, "tokens", 100)
        with self.assertRaisesRegex(ValueError, "finished"):
            ResearchBudget(self.root, "tokens", 100, resume=True, renew=True)

    def test_cannot_change_resume_budget(self):
        ResearchBudget(self.root, "tokens", 100)
        before = (self.root / ResearchBudget.STATE_FILE).read_bytes()
        with self.assertRaisesRegex(ValueError, "Cannot change"):
            ResearchBudget(self.root, "tokens", 200, resume=True)
        self.assertEqual(before, (self.root / ResearchBudget.STATE_FILE).read_bytes())

    def test_cannot_reset_existing_allocation(self):
        ResearchBudget(self.root, "tokens", 100)
        with self.assertRaisesRegex(ValueError, "already"):
            ResearchBudget(self.root, "tokens", 100)

    def test_missing_or_corrupt_state_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            ResearchBudget(self.root, "tokens", 100, resume=True)
        (self.root / ResearchBudget.STATE_FILE).write_text('{"bad":true}')
        with self.assertRaisesRegex(ValueError, "refusing"):
            ResearchBudget(self.root, "tokens", 100, resume=True)

    def test_empty_and_malformed_json(self):
        for contents in ("", "null", "[]", "{broken"):
            with self.subTest(contents=contents):
                (self.root / ResearchBudget.STATE_FILE).write_text(contents)
                with self.assertRaisesRegex(ValueError, "Invalid research state"):
                    ResearchBudget.load_state(self.root)

    def test_invalid_limits_rejected(self):
        for limit in (0, -1, 1.5, True):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    ResearchBudget(self.root, "tokens", limit)

    def test_report_reserve_uses_existing_threshold(self):
        budget = ResearchBudget(self.root, "tokens", 100, conclude_after=0.9)
        budget.add_output_tokens(90)
        self.assertTrue(budget.should_conclude())
        self.assertFalse(budget.is_exhausted())

    def test_finished_state_is_preserved_on_load(self):
        budget = ResearchBudget(self.root, "tokens", 100)
        budget.save("finished")
        loaded = ResearchBudget(self.root, "tokens", 100, resume=True)
        self.assertEqual(loaded.state["status"], "finished")

    def test_legacy_budget_unchanged(self):
        first = Budget("tokens", 100)
        first.add_output_tokens(30)
        self.assertEqual(first.fraction_spent(), 0.3)
        self.assertEqual(Budget("tokens", 100).total_output_tokens, 0)


if __name__ == "__main__":
    unittest.main()

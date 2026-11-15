"""Exercise the real planner loop and CLI with deterministic offline clients."""
import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from openprover import cli
from openprover.budget import Budget, ResearchBudget
from openprover.prover import Prover
from openprover.research import ResearchProver, _ResearchPlanner, planner_instructions
from openprover.tui import HeadlessTUI


SAVE = '''<OPENPROVER_ACTION>
action = "write_items"
summary = "Save conditional progress"
[[items]]
slug = "candidate"
content = "Summary: Conditional result. Lemma A remains open."
</OPENPROVER_ACTION>'''
SUBMIT = '''<OPENPROVER_ACTION>
action = "submit_proof"
summary = "Attempt premature termination"
proof_slug = "candidate"
</OPENPROVER_ACTION>'''
NOTE = '''<OPENPROVER_ACTION>
action = "write_whiteboard"
summary = "Record the gap"
whiteboard = "Conditional result [[candidate]]; Lemma A remains open."
</OPENPROVER_ACTION>'''
SPAWN = '''<OPENPROVER_ACTION>
action = "spawn"
[[tasks]]
summary = "Inspect a lemma"
description = "Determine whether the proposed inequality holds."
</OPENPROVER_ACTION>'''


class FakeClient:
    model = "offline-test"
    context_length = 200000
    answer_reserve = 10
    total_cost = 0.0

    def __init__(self, answers=(), tokens=10):
        self.answers = iter(answers)
        self.tokens = tokens
        self.calls = []
        self.call_count = 0

    def call(self, **kwargs):
        self.calls.append(kwargs)
        self.call_count += 1
        label = kwargs.get("label", "")
        if label in ("research_report", "discussion"):
            result = "# Final report\nConditional progress; Lemma A remains open."
        elif label.startswith("verifier_"):
            result = "VERDICT: NEEDS MINOR FIXES - the lemma remains unresolved"
        elif label.startswith("worker_"):
            result = "Conditional progress only; the lemma remains unresolved."
        else:
            result = next(self.answers)
        return {"result": result, "thinking": "", "cost": 0.0, "duration_ms": 1,
                "raw": {"model": self.model, "usage": {
                    "input_tokens": 5, "output_tokens": self.tokens}},
                "finish_reason": "stop"}

    def cleanup(self):
        pass

    def clear_interrupt(self):
        pass


class ResearchModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        self.root.mkdir()

    def make_prover(self, answers=(SAVE, SUBMIT, NOTE), *, limit=30,
                    resume=False, renew=False, tokens=10, conclude_after=1.0):
        planner = FakeClient(answers, tokens=tokens)
        worker = FakeClient(tokens=tokens)
        budget = ResearchBudget(self.root, "tokens", limit, conclude_after,
                                resume=resume, renew=renew)
        prover = ResearchProver(
            work_dir=self.root, theorem_text="Improve a bound without extra assumptions.",
            mode="research", make_llm=lambda path: planner,
            make_worker_llm=lambda path: worker, model_name="offline-test",
            budget=budget, autonomous=True, verbose=False, tui=HeadlessTUI(),
            isolation=True, resumed=resume,
        )
        return prover, planner, worker

    def test_candidate_and_submission_do_not_end_run(self):
        prover, planner, _ = self.make_prover()
        with contextlib.redirect_stdout(io.StringIO()):
            prover.run()
        self.assertEqual(planner.call_count, 3)
        self.assertTrue((self.root / "repo/candidate.md").exists())
        self.assertFalse((self.root / "PROOF.md").exists())
        self.assertIn("Lemma A", prover.whiteboard)
        self.assertTrue(prover.is_finished)
        self.assertTrue((self.root / "DISCUSSION.md").exists())
        self.assertTrue((self.root / "reports/allocation_001.md").exists())

    def test_existing_worker_and_review_phases_still_execute(self):
        prover, _, worker = self.make_prover((SPAWN,))
        with contextlib.redirect_stdout(io.StringIO()):
            prover.run()
        self.assertEqual(worker.call_count, 2)
        self.assertTrue(any(c["label"].startswith("verifier_") for c in worker.calls))
        self.assertEqual(prover.budget.total_output_tokens, 30)
        self.assertTrue(prover.is_finished)

    def test_final_synthesis_uses_reserve_and_is_not_periodic(self):
        prover, planner, _ = self.make_prover((SAVE, NOTE, NOTE), limit=100,
                                             tokens=30, conclude_after=0.9)
        # A report call uses ten output tokens, matching its explicit reserve.
        original = planner.call
        def call(**kwargs):
            previous = planner.tokens
            if kwargs.get("label") == "research_report":
                planner.tokens = 10
            try:
                return original(**kwargs)
            finally:
                planner.tokens = previous
        planner.call = call
        prover._write_discussion()
        self.assertFalse((self.root / "DISCUSSION.md").exists())
        with contextlib.redirect_stdout(io.StringIO()):
            prover.run()
        reports = [c for c in planner.calls if c.get("label") == "research_report"]
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["max_tokens"], 10)
        self.assertEqual(prover.budget.total_output_tokens, 100)
        self.assertIn("Lemma A", (self.root / "DISCUSSION.md").read_text())
        prover._write_discussion()
        self.assertEqual(len(planner.calls), 4)

    def test_explicit_continuation_preserves_findings_history_and_reports(self):
        first, _, _ = self.make_prover()
        with contextlib.redirect_stdout(io.StringIO()):
            first.run()
        report = first.report_path.read_bytes()
        second, planner, _ = self.make_prover((NOTE,), limit=10, resume=True, renew=True)
        self.assertIn("Lemma A", second.whiteboard)
        with contextlib.redirect_stdout(io.StringIO()):
            second.run()
        self.assertEqual(second.step_num, 4)
        self.assertEqual(planner.call_count, 1)
        self.assertEqual(second.budget.total_output_tokens, 10)
        self.assertEqual((self.root / "reports/allocation_001.md").read_bytes(), report)
        self.assertTrue((self.root / "reports/allocation_002.md").exists())

    def test_interruption_pauses_without_final_report(self):
        prover, _, _ = self.make_prover()
        def pause():
            prover.budget.add_output_tokens(5)
            prover.shutting_down = True
            return "stop"
        with patch.object(prover, "_do_step", side_effect=pause), \
             contextlib.redirect_stdout(io.StringIO()):
            prover.run()
        self.assertEqual(prover.budget.state["status"], "paused")
        self.assertFalse((self.root / "DISCUSSION.md").exists())
        resumed, _, _ = self.make_prover(resume=True)
        self.assertEqual(resumed.budget.total_output_tokens, 5)

    def test_finished_run_cannot_spend_again(self):
        prover, planner, _ = self.make_prover()
        prover.budget.save("finished")
        with self.assertRaisesRegex(ValueError, "--continue"):
            prover.run()
        self.assertEqual(planner.call_count, 0)

    def test_stray_proof_and_report_files_do_not_finish_research(self):
        prover, _, _ = self.make_prover()
        (self.root / "PROOF.md").write_text("Not an allocation status")
        (self.root / "DISCUSSION.md").write_text("Previous report")
        self.assertFalse(prover.is_finished)
        self.assertFalse(cli._is_finished(self.root, "research"))
        self.assertEqual(prover._handle_submit_lean_proof({}, self.root), "continue")

    def test_legacy_prove_mode_still_terminates_on_proof(self):
        planner = FakeClient((SAVE, SUBMIT))
        prover = Prover(work_dir=self.root, theorem_text="A theorem", mode="prove",
                        make_llm=lambda path: planner, model_name="offline-test",
                        budget=Budget("tokens", 1000), autonomous=True,
                        verbose=False, tui=HeadlessTUI(), isolation=True)
        with contextlib.redirect_stdout(io.StringIO()):
            prover.run()
        self.assertTrue((self.root / "PROOF.md").exists())
        self.assertEqual(prover.step_num, 2)
        self.assertTrue(cli._is_finished(self.root, "prove"))

    def test_planner_prompt_does_not_change_worker_or_global_prompt(self):
        from openprover import prompts
        original = prompts.planner_system_prompt(isolation=True)
        prover, planner, worker = self.make_prover()
        self.assertEqual(original, prompts.planner_system_prompt(isolation=True))
        self.assertIs(prover.worker_llm, worker)
        self.assertNotIn("**submit_proof**", planner_instructions())
        underlying = Mock()
        adapter = _ResearchPlanner(underlying, "research instructions")
        adapter.chat([{"role": "system", "content": "old"},
                      {"role": "user", "content": "task"}])
        self.assertEqual(underlying.chat.call_args.kwargs["messages"][0]["content"],
                         "research instructions")

    def seed_cli_state(self, status="finished"):
        (self.root / "THEOREM.md").write_text("Research objective")
        (self.root / "WHITEBOARD.md").write_text("Existing progress")
        (self.root / "run_config.toml").write_text('mode = "research"\n')
        ResearchBudget(self.root, "tokens", 30).save(status)

    def test_cli_inspection_does_not_require_credentials(self):
        self.seed_cli_state()
        with patch("sys.argv", ["openprover", str(self.root), "--headless"]), \
             patch.object(cli, "OpenAIClient", side_effect=AssertionError("API client created")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main()
        self.assertIn("--continue", output.getvalue())

    def test_cli_continuation_requires_explicit_new_budget(self):
        self.seed_cli_state()
        with patch("sys.argv", ["openprover", str(self.root), "--continue"]), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                cli.main()
        self.assertEqual(error.exception.code, 2)

    def test_cli_does_not_silently_accept_a_replacement_budget(self):
        self.seed_cli_state()
        with patch("sys.argv", ["openprover", str(self.root), "--max-time=1h"]), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                cli.main()
        self.assertEqual(error.exception.code, 2)

    def test_cli_cannot_continue_an_active_allocation(self):
        self.seed_cli_state("paused")
        with patch("sys.argv", ["openprover", str(self.root), "--continue", "--max-tokens", "50"]), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main()

    def test_cli_parses_equal_sign_budget_flags(self):
        with patch("sys.argv", ["openprover", "run", "--max-tokens=100"]):
            self.assertTrue(cli._cli_flag_given("--max-tokens"))

    def test_mode_resolution_preserves_research_and_legacy_modes(self):
        self.seed_cli_state("paused")
        args = argparse.Namespace(run_dir=str(self.root), theorem=None,
                                  lean_theorem=None, proof=None, read_only=False, mode=None)
        parser = argparse.ArgumentParser()
        self.assertEqual(cli._resolve_inputs(parser, args)[4], "research")
        (self.root / "run_config.toml").write_text('mode = "prove"\n')
        self.assertEqual(cli._resolve_inputs(parser, args)[4], "prove")
        (self.root / "THEOREM.lean").write_text("theorem example : True := by trivial")
        self.assertEqual(cli._resolve_inputs(parser, args)[4], "prove_and_formalize")
        (self.root / "PROOF.md").write_text("A proof")
        self.assertEqual(cli._resolve_inputs(parser, args)[4], "formalize_only")


if __name__ == "__main__":
    unittest.main()

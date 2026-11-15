"""Offline research-policy and feedback tests. No API credentials or requests."""

import contextlib
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from openprover import cli, prompts
from openprover.budget import ResearchBudget
from openprover.feedback import FeedbackInbox, main as feedback_main
from openprover.prover import Prover
from openprover.research import (
    ResearchProver, _ResearchPlanner, planner_instructions, worker_instructions,
)
from openprover.tui import HeadlessTUI

SPAWN = '''<OPENPROVER_ACTION>
action = "spawn"
[[tasks]]
summary = "Test a construction"
description = "Audit [[lemma]] without extra assumptions."
</OPENPROVER_ACTION>'''
NOTE = '''<OPENPROVER_ACTION>
action = "write_whiteboard"
summary = "Record next question"
whiteboard = "Keep distinct routes and check the exact gap."
</OPENPROVER_ACTION>'''


class Client:
    model = "offline"
    context_length = 200000
    answer_reserve = 10
    total_cost = 0.0

    def __init__(self, answers=()):
        self.answers = iter(answers)
        self.calls = []
        self.call_count = 0
        self.on_call = lambda kwargs: None

    def call(self, **kwargs):
        self.calls.append(kwargs)
        self.call_count += 1
        self.on_call(kwargs)
        label = kwargs.get("label", "")
        result = ("VERDICT: INCONCLUSIVE - remaining uniformity gap"
                  if label.startswith("verifier_") else
                  "Concrete conditional derivation; uniformity remains open."
                  if label.startswith("worker_") else next(self.answers))
        return {"result": result, "thinking": "", "cost": 0.0, "duration_ms": 1,
                "raw": {"usage": {"input_tokens": 5, "output_tokens": 10}},
                "finish_reason": "stop"}

    def cleanup(self):
        pass

    def clear_interrupt(self):
        pass


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inbox = FeedbackInbox(self.root)

    def prover(self, answers=(SPAWN,), limit=30, resume=False):
        planner, worker = Client(answers), Client()
        prover = ResearchProver(
            work_dir=self.root, theorem_text="Fixed objective: no extra assumptions.",
            mode="research", make_llm=lambda _: planner, make_worker_llm=lambda _: worker,
            model_name="offline", budget=ResearchBudget(self.root, "tokens", limit, 1.0,
                                                        resume=resume),
            autonomous=True, verbose=False, tui=HeadlessTUI(), isolation=True,
            resumed=resume,
        )
        return prover, planner, worker

    def run_quietly(self, prover):
        with contextlib.redirect_stdout(io.StringIO()):
            prover.run()

    def test_concurrent_senders_publish_complete_distinct_messages(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            identifiers = list(pool.map(self.inbox.send, [f"message {i}" for i in range(12)]))
        self.assertEqual(len(set(identifiers)), 12)
        self.assertEqual(len(self.inbox.active()), 12)
        (self.inbox.root / "messages/.pending-partial").write_text('{"unfinished":')
        self.assertEqual(len(self.inbox.messages()), 12)

    def test_invalid_messages_are_rejected(self):
        for text in ("  ", "a" * 16001):
            with self.subTest(text_length=len(text)), self.assertRaises(ValueError):
                self.inbox.send(text)
        with self.assertRaisesRegex(ValueError, "Unknown feedback ID"):
            self.inbox.send("replacement", "missing")

    def test_superseded_guidance_is_archived_not_reinjected(self):
        first = self.inbox.send("Favor family A")
        second = self.inbox.send("Favor family B", supersedes=first)
        self.assertEqual([m["id"] for m in self.inbox.active()], [second])
        self.assertEqual(len(self.inbox.messages()), 2)
        self.assertNotIn("Favor family A", self.inbox.render(self.inbox.active()))

    def test_receipts_are_idempotent_and_survive_restart(self):
        identifier = self.inbox.send("Try symmetry")
        self.inbox.record((identifier,), "delivered", 2)
        self.assertEqual(self.inbox.acknowledged_ids(), ())
        self.inbox.record((identifier,), "acknowledged", 3)
        self.inbox.record((identifier,), "acknowledged", 4)
        reopened = FeedbackInbox(self.root)
        self.assertEqual(reopened.acknowledged_ids(), (identifier,))
        self.assertEqual(reopened.receipts()[identifier]["acknowledged"], 3)

    def test_feedback_before_planning_is_delivered_and_acknowledged(self):
        prover, planner, _ = self.prover()
        identifier = self.inbox.send("Keep another proof route alive")
        self.run_quietly(prover)
        self.assertIn(identifier, planner.calls[0]["prompt"])
        self.assertEqual(self.inbox.receipts()[identifier], {"delivered": 1, "acknowledged": 1})
        self.assertEqual(prover.budget.total_output_tokens, 30)

    def test_feedback_during_workers_preserves_results_and_changes_next_round(self):
        prover, planner, worker = self.prover((SPAWN, NOTE), limit=40)
        ids = []
        def during_work(kwargs):
            if kwargs["label"].startswith("worker_"):
                ids.append(self.inbox.send("Explore an incompatible formulation"))
        worker.on_call = during_work
        self.run_quietly(prover)
        result = self.root / "steps/step_001/workers/result_0.md"
        self.assertIn("Concrete conditional", result.read_text())
        self.assertEqual(worker.call_count, 2)  # Research and review both finish.
        self.assertIn(ids[0], planner.calls[1]["prompt"])
        self.assertEqual(prover.budget.limit, 40)
        self.assertTrue(prover.is_finished)

    def test_feedback_during_planning_prevents_stale_dispatch(self):
        prover, planner, worker = self.prover((SPAWN, SPAWN), limit=40)
        ids = []
        def during_plan(kwargs):
            if not ids:
                ids.append(self.inbox.send("Do not repeat the old family"))
        planner.on_call = during_plan
        self.run_quietly(prover)
        self.assertFalse((self.root / "steps/step_001/workers").exists())
        self.assertTrue((self.root / "steps/step_002/workers/result_0.md").exists())
        self.assertEqual(worker.call_count, 2)
        self.assertIn(ids[0], planner.calls[1]["prompt"])
        self.assertEqual(self.inbox.receipts()[ids[0]]["acknowledged"], 2)

    def test_feedback_is_checked_again_immediately_before_dispatch(self):
        prover, planner, worker = self.prover((NOTE + "\n" + SPAWN, SPAWN), limit=40)
        original = prover._handle_write_whiteboard
        def write_then_feedback(plan):
            original(plan)
            self.inbox.send("Redirect the next batch")
        with patch.object(prover, "_handle_write_whiteboard", side_effect=write_then_feedback):
            self.run_quietly(prover)
        self.assertFalse((self.root / "steps/step_001/workers").exists())
        self.assertEqual(worker.call_count, 2)
        self.assertIn("Redirect the next batch", planner.calls[1]["prompt"])

    def test_worker_and_reviewer_share_frozen_objective_and_references(self):
        prover, _, worker = self.prover()
        prover.repo.write_item("lemma", "Summary: Original statement.\nOLD EVIDENCE")
        def mutate_after_dispatch(kwargs):
            if kwargs["label"].startswith("worker_"):
                prover.repo.write_item("lemma", "Summary: Changed statement.\nNEW EVIDENCE")
        worker.on_call = mutate_after_dispatch
        self.run_quietly(prover)
        for call in worker.calls:
            self.assertIn("Fixed objective: no extra assumptions.", call["prompt"])
            self.assertIn("OLD EVIDENCE", call["prompt"])
            self.assertNotIn("NEW EVIDENCE", call["prompt"])
            self.assertEqual(call["prompt"].count("# Fixed research objective"), 1)
        self.assertIn("independent adversarial", worker.calls[1]["system_prompt"])
        self.assertIn("INCONCLUSIVE", worker.calls[1]["system_prompt"])
        saved = (self.root / "steps/step_001/workers/task_0.md").read_text()
        self.assertIn("OLD EVIDENCE", saved)
        self.assertEqual(prover._task_packet(saved), saved)

    def test_registry_persists_and_is_included_in_planner_context(self):
        prover, planner, _ = self.prover((NOTE,), limit=10)
        prover.repo.write_item("approaches", "Summary: Portfolio.\nFamily A differs from family B.")
        self.run_quietly(prover)
        self.assertIn("Family A differs from family B.", planner.calls[0]["prompt"])

    def test_delivered_but_unacknowledged_feedback_is_replayed_after_restart(self):
        prover, _, _ = self.prover((NOTE,), limit=20)
        identifier = self.inbox.send("Revisit with a new mechanism")
        prover.step_num = 1
        prover._planner_context()  # Simulate a crash after delivery, before a valid plan.
        prover.budget.add_output_tokens(5)
        prover.budget.save("paused")
        restarted, planner, _ = self.prover((NOTE, NOTE), limit=20, resume=True)
        self.assertTrue(restarted._new_feedback())
        self.assertEqual(restarted.budget.total_output_tokens, 5)
        with patch.object(Prover, "_maybe_respawn_interrupted_workers") as respawn:
            restarted._maybe_respawn_interrupted_workers()
            respawn.assert_not_called()
        self.run_quietly(restarted)
        self.assertIn(identifier, planner.calls[0]["prompt"])
        self.assertIn("acknowledged", self.inbox.receipts()[identifier])

    def test_acknowledged_guidance_remains_active_across_new_allocations(self):
        prover, _, _ = self.prover((NOTE,), limit=10)
        identifier = self.inbox.send("Preserve independent approaches")
        self.run_quietly(prover)
        self.assertIn(identifier, FeedbackInbox(self.root).render(self.inbox.active()))
        self.assertEqual(self.inbox.acknowledged_ids(), (identifier,))

    def test_cli_can_queue_and_list_on_finished_run_without_spending(self):
        prover, _, _ = self.prover()
        prover.budget.save("finished")
        state_before = (self.root / "research_state.json").read_bytes()
        with patch.object(cli, "OpenAIClient", side_effect=AssertionError("must not create client")), \
             patch("sys.argv", ["openprover", "feedback", str(self.root), "--message", "Try duality"]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main()
        self.assertIn("Queued F-", output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            feedback_main([str(self.root), "--list"])
        self.assertIn("[queued] Try duality", output.getvalue())
        self.assertEqual((self.root / "research_state.json").read_bytes(), state_before)

    def test_cli_file_and_supersedes(self):
        self.prover()
        first = self.inbox.send("Old guidance")
        file = self.root / "note.md"
        file.write_text("New guidance", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            feedback_main([str(self.root), "--file", str(file), "--supersedes", first])
        self.assertEqual([m["message"] for m in self.inbox.active()], ["New guidance"])

    def test_cli_rejects_nonresearch_directory(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            feedback_main([str(self.root), "--message", "message"])
        self.assertFalse((self.root / "feedback").exists())

    def test_research_prompts_preserve_distinct_routes_and_honest_audit(self):
        policy = planner_instructions()
        for phrase in ("[[approaches]]", "symmetries", "incompatible routes", "Cross-pollinate",
                       "theorem-strength gap", "NOT RUN", "assembled proof"):
            self.assertIn(phrase, policy)
        self.assertIn("Exploration may return explicit conjectures", worker_instructions())
        self.assertNotIn("lean_verify", worker_instructions())
        self.assertIn("lean_verify", worker_instructions(True))
        self.assertNotIn("Research policy:", prompts.planner_system_prompt())

    def test_planner_chat_continuation_includes_latest_context_without_mutation(self):
        client = Mock()
        adapter = _ResearchPlanner(client, "policy", context=lambda: "live guidance")
        messages = [{"role": "system", "content": "old"}, {"role": "user", "content": "task"}]
        adapter.chat(messages)
        actual = client.chat.call_args.kwargs["messages"]
        self.assertEqual(actual[0]["content"], "policy")
        self.assertEqual(actual[-1]["content"], "live guidance")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["content"], "old")

    def test_truncated_review_keeps_inconclusive_option(self):
        prover, _, worker = self.prover()
        worker.call = Mock(side_effect=[
            {"result": "Partial audit", "thinking": "", "cost": 0, "duration_ms": 1,
             "raw": {}, "finish_reason": "length"},
            {"result": "VERDICT: INCONCLUSIVE - needs further checking", "thinking": "",
             "cost": 0, "duration_ms": 1, "raw": {}, "finish_reason": "stop"},
        ])
        response = prover._run_verifier("Audit [[lemma]]", "candidate", "verifier_test")
        self.assertIn("INCONCLUSIVE", response["result"])
        for call in worker.call.call_args_list:
            self.assertIn("INCONCLUSIVE", call.kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()

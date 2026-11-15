"""Budget-driven research using the existing Prover loop and file repository.

The planner adapter supplies mode-specific instructions through the existing
client factory. It does not monkey-patch global prompts or duplicate the loop.
"""

from . import prompts
from .budget import ResearchBudget
from .llm import Interrupted
from .prover import Prover


def planner_instructions(*, isolation=True, lean_items=False):
    """Reuse the existing action protocol, excluding theorem submission."""
    actions = [a for a in prompts.ACTIONS
               if a not in ("submit_proof", "submit_lean_proof")
               and (a != "literature_search" or not isolation)]
    return (
        "You coordinate an open-ended mathematical research effort. The supplied "
        "THEOREM is the fixed research objective, not an assertion with a known proof.\n"
        "Use the existing workers and independent reviewers. Preserve assumptions "
        "and quantifiers. Save conjectures, partial results, obstructions, failed "
        "attempts, and candidate proofs with explicit status and unresolved gaps.\n"
        "A discovery does not terminate research: save it with write_items, request "
        "independent review, and investigate the next useful question. There is no "
        "submit or finish action in this mode. The host ends the allocation at its "
        "budget threshold and writes one final report. Do not request periodic reports "
        "or a fresh allocation. Ignore inherited instructions to submit a final proof.\n"
        "Keep WHITEBOARD concise and link to detailed repo items. Workers see only "
        "their assigned task and referenced [[items]]; supply sufficient context.\n\n"
        "Available actions:\n"
        + prompts._build_actions(lean_mode="research", has_lean=False,
                                 isolation=isolation)
        + "\nRepository format:\n"
        + prompts._build_repo_items_section(lean_items=lean_items)
        + "\nOutput one or more TOML blocks, each wrapped in "
        "<OPENPROVER_ACTION>...</OPENPROVER_ACTION>. Each block has action and "
        "summary; for spawn, put summary and description on each [[tasks]] entry. "
        "At most one spawn block per step. Valid actions: " + ", ".join(actions)
        + "\n\nFields:\n"
        + prompts._build_toml_fields(lean_mode="research", has_lean=False,
                                    isolation=isolation, lean_items=lean_items)
    )


class _ResearchPlanner:
    """Change only the planner instructions; delegate API/lifecycle behavior."""

    def __init__(self, client, instructions):
        self.client = client
        self.instructions = instructions

    def __getattr__(self, name):
        return getattr(self.client, name)

    def call(self, prompt, system_prompt="", **kwargs):
        return self.client.call(prompt=prompt, system_prompt=self.instructions, **kwargs)

    def chat(self, messages, **kwargs):
        # The base loop can use chat() to complete a truncated planner response.
        messages = [{"role": "system", "content": self.instructions}] + [
            message for message in messages if message.get("role") != "system"
        ]
        return self.client.chat(messages=messages, **kwargs)


class ResearchProver(Prover):
    """Reuse delegation, review, memory, and inspection without proof termination."""

    def __init__(self, **kwargs):
        if kwargs.get("mode") != "research" or not isinstance(kwargs["budget"], ResearchBudget):
            raise ValueError("ResearchProver requires research mode and ResearchBudget")
        factory = kwargs["make_llm"]
        instructions = planner_instructions(
            isolation=kwargs.get("isolation", True),
            lean_items=kwargs.get("lean_items", False),
        )
        kwargs["make_llm"] = lambda path: _ResearchPlanner(factory(path), instructions)
        # Workers retain their own role, even when no separate factory is supplied.
        kwargs["make_worker_llm"] = kwargs.get("make_worker_llm") or factory
        # The legacy constructor only recognizes theorem modes when creating
        # its initial whiteboard. Bootstrap that generic state, then switch to
        # research before running any planner/worker calls. No global prompt
        # changes or duplicated initialization are needed.
        kwargs["mode"] = "prove"
        super().__init__(**kwargs)
        self.mode = "research"
        if not self.resumed:
            self.whiteboard = (
                f"## Research objective\n\n{self.theorem_text}\n\n"
                "## Approaches\n\n## Findings and evidence\n\n"
                "## Open obligations\n\n## Failed attempts\n\n## Next questions\n"
            )
            (self.work_dir / "WHITEBOARD.md").write_text(self.whiteboard, encoding="utf-8")

    @property
    def is_finished(self):
        return self.budget.state["status"] == "finished"

    def _handle_submit_proof(self, plan, step_dir):
        self._push_output("Submission is disabled in research mode. Save the candidate "
                          "with write_items, request review, and continue research.")
        return "continue"

    def _handle_submit_lean_proof(self, plan, step_dir):
        return self._handle_submit_proof(plan, step_dir)

    def _check_completion(self, feedback):
        self._push_output(feedback)
        return "continue"

    def _restore_budget_tokens(self):
        # ResearchBudget already restores only this allocation's recorded usage.
        # Replaying all step metadata would charge prior allocations again.
        pass

    def _maybe_respawn_interrupted_workers(self):
        if not self.budget.should_conclude():
            super()._maybe_respawn_interrupted_workers()

    def _do_step(self):
        # Base run() checks exhaustion, but not the final-report reserve, at entry.
        if self.budget.should_conclude():
            return "stop"
        return super()._do_step()

    @property
    def report_path(self):
        return self.work_dir / "reports" / f"allocation_{self.budget.state['allocation']:03d}.md"

    def _save_report(self, text):
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (self.report_path, self.work_dir / "DISCUSSION.md"):
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)

    def _checkpoint_report(self, reason):
        return (
            f"# Research allocation {self.budget.state['allocation']}\n\n"
            f"{reason}\n\nBudget: {self.budget.summary_str()}\n\n"
            "This is a saved research checkpoint, not a certification of its claims.\n\n"
            f"## Research state\n\n{self.whiteboard}\n\n"
            f"## Evidence index\n\n{self.repo.list_summaries()}\n"
        )

    def _write_discussion(self):
        # The base loop invokes this on errors too; pauses must not generate reports.
        if not self.budget.should_conclude() or self.report_path.exists():
            return
        text = self._checkpoint_report("Allocation ended; no report synthesis budget remained.")
        if not self.budget.is_exhausted() and not self._spending_limit_hit and not self._llm_error_exit:
            client = self.planner_llm.client
            cap = getattr(client, "answer_reserve", 4096) or 4096
            if self.budget.mode == "tokens":
                cap = min(cap, self.budget.limit - self.budget.total_output_tokens)
            try:
                response = client.call(
                    prompt=text,
                    system_prompt=(
                        "Write the final report for this research allocation. Separate "
                        "supported results, conjectures, conditional progress, failed "
                        "approaches, and next questions. Link to the supplied evidence. "
                        "Do not invent proof details or assert correctness from file names. "
                        "Do not use planner action blocks or propose automatic continuation."
                    ),
                    label="research_report", max_tokens=cap,
                    archive_path=self.work_dir / "reports" /
                        f"allocation_{self.budget.state['allocation']:03d}_call.md",
                )
                self._track_output_tokens(response)
                if response.get("result") and response.get("finish_reason", "stop") == "stop":
                    text = response["result"]
                else:
                    text = self._checkpoint_report("Report synthesis was incomplete; saved checkpoint below.")
            except (Interrupted, RuntimeError) as exc:
                text = self._checkpoint_report(f"Report synthesis did not complete ({type(exc).__name__}).")
        self._save_report(text)

    def run(self):
        if self.is_finished:
            raise ValueError("Allocation finished. Use --continue with a new explicit budget.")
        self.budget.save("running")
        try:
            super().run()
        finally:
            if self.budget.should_conclude():
                # Includes exhausted allocations resumed after downtime and report failures.
                if not self.report_path.exists():
                    self._save_report(self._checkpoint_report("Allocation ended; saved checkpoint below."))
                self.budget.save("finished")
            else:
                self.budget.save("paused")

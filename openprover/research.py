"""Budget-driven research using the existing Prover loop and file repository.

The planner adapter supplies mode-specific instructions through the existing
client factory. It does not monkey-patch global prompts or duplicate the loop.
"""

from . import prompts
from .budget import ResearchBudget
from .feedback import FeedbackInbox
from .llm import Interrupted
from .prover import Prover


RESEARCH_POLICY = """
Research policy:
- Begin with a genuinely diverse portfolio: different formulations, symmetries,
  constructions, or proof mechanisms, not differently worded variants.
- Maintain [[approaches]] as the explicit approach-family registry. For each
  family record its mechanism, linked attempts, strongest evidence, decisive
  gap, and next discriminating question. Group by mathematical idea. Redirect
  excess workers when they converge on one family.
- Keep several incompatible routes alive through multiple rounds. Give fresh
  explorers only the fixed objective and relevant context, not the favored proof
  transcript. Cross-pollinate after independent routes expose strengths and gaps.
  Archive decisively refuted routes rather than preserving them to meet a quota.
- Reason mathematically to synthesize, challenge, and redirect. Delegate substantial
  proofs/calculations; your own new claims also require independent review.
- Use adversarial review throughout, including counterexamples to sublemmas and
  review of the assembled proof, not just isolated components. Every candidate
  proof needs analytic audit and numerical checks of meaningful specializations,
  including admissible edge cases. If no execution tool is available, explicitly
  record the numerical check as NOT RUN and queue it; never invent execution.
  Numerical evidence is not proof of a universal or asymptotic claim.
- Require concrete lemmas, constructions, equations, derivations, or counterexamples.
  Reject status-only reports and vague optimism. Unproved global compatibility is
  an explicit gap, never 'routine'. Distinguish refutation from an incomplete proof.
- Repeatedly synthesize and launch new rounds within the allocation. Failure of a
  wave or a theorem-strength gap is not a stopping condition. Seek fresh mechanisms;
  reopen a blocked route only with a specific change addressing its recorded gap.
- Preserve exact assumptions, quantifiers, and parameter regimes. Repair concrete
  objections; do not repeat an unchanged failed attempt. Fully audit any proposed
  improved bound, including compatibility of all parameter choices.
- At allocation end, report a complete proof only if it survives audit, distinguishing
  informal review from formal checking. Otherwise report the strongest supported
  derivation and its exact remaining gap. Budget limits still govern termination.
"""

WORKER_POLICY = """You are a research mathematician investigating the assigned task.
Use the fixed objective, the assignment, and supplied evidence; you do not receive
other agents' private histories. Exploration may return explicit conjectures and
partial derivations. A claimed proof must be complete and checkable. Return concrete
lemmas, constructions, equations, or counterexamples; no status-only optimism.
State every extra assumption, parameter restriction, and missing step. Never call
an unresolved global compatibility claim routine. Distinguish an obstruction to
this argument from a refutation of the target. A repair must address the specific
previous objection with a genuinely new mechanism or correction.
Use only the tools actually provided. For candidate proofs, test meaningful small
and boundary cases; save executed code and outputs. Without an execution tool,
label numerical tests NOT RUN and specify the experiment for a later task. Analytic
special cases should still be checked. Numerical success is not a universal proof.
Cite supplied sources precisely; mark any unsupplied or unchecked citation unverified.
Do not claim access to papers, web, or Python absent an actual tool or supplied text.
End with the strongest supported result, exact remaining obligations, and evidence.
You are one worker: do not spawn agents. Use LaTeX for mathematical statements.
"""

REVIEWER_POLICY = """You are an independent adversarial mathematical reviewer.
Check the candidate against the FIXED OBJECTIVE and the frozen reference material,
not merely the author's restatement. Reconstruct the decisive derivation. Check
quantifiers, hidden assumptions, adaptive conditioning, constants, feasible parameter
choices, edge cases, circular dependencies, and any unproved compatibility bridge.
State precisely what you checked, the strongest conclusion supported, each objection
and its location, and what remains unverified. Do not silently repair the argument.
Explicit conditional progress can be valid without solving the objective. Do not
mistake incompleteness for falsity, or numerical evidence for proof. Require numerical
checks of meaningful specializations and edge cases; inspect actual code/results.
You have no execution tools in this review call: missing tests are NOT RUN, not passed.
Where computation is inapplicable explain why and audit analytic special cases.
Check formal statements match the intended claim even when a kernel checked the code.
Never treat another model's favorable verdict as a proof certificate.
End with one line: VERDICT: CORRECT (only within the explicitly checked scope),
VERDICT: CRITICALLY FLAWED - <specific reason>, VERDICT: NEEDS MINOR FIXES - <reason>,
or VERDICT: INCONCLUSIVE - <unchecked obligations>. When unsure use INCONCLUSIVE.
"""


def worker_instructions(use_tools=False):
    # Retain upstream's actual Lean tool instructions without its competition-style role.
    tools = (prompts.worker_system_prompt(lean_worker_tools=True)[
        len(prompts.worker_system_prompt(lean_worker_tools=False)):] if use_tools else "")
    return WORKER_POLICY + tools


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
        + RESEARCH_POLICY + "\nAvailable actions:\n"
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

    def __init__(self, client, instructions, context=None):
        self.client = client
        self.instructions = instructions
        self.context = context or (lambda: "")

    def __getattr__(self, name):
        return getattr(self.client, name)

    def call(self, prompt, system_prompt="", **kwargs):
        return self.client.call(prompt=prompt + "\n\n" + self.context(),
                                system_prompt=self.instructions, **kwargs)

    def chat(self, messages, **kwargs):
        # The base loop can use chat() to complete a truncated planner response.
        messages = [{"role": "system", "content": self.instructions}] + [
            message for message in messages if message.get("role") != "system"
        ]
        context = self.context()
        if context:
            messages.append({"role": "user", "content": context})
        return self.client.chat(messages=messages, **kwargs)


class ResearchProver(Prover):
    """Reuse delegation, review, memory, and inspection without proof termination."""

    def __init__(self, **kwargs):
        if kwargs.get("mode") != "research" or not isinstance(kwargs["budget"], ResearchBudget):
            raise ValueError("ResearchProver requires research mode and ResearchBudget")
        self.feedback = FeedbackInbox(kwargs["work_dir"])
        self._feedback_ids = self.feedback.acknowledged_ids()
        factory = kwargs["make_llm"]
        instructions = planner_instructions(
            isolation=kwargs.get("isolation", True),
            lean_items=kwargs.get("lean_items", False),
        )
        kwargs["make_llm"] = lambda path: _ResearchPlanner(factory(path), instructions, self._planner_context)
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

    def _planner_context(self):
        messages = self.feedback.active()
        self._feedback_ids = tuple(m["id"] for m in messages)
        self.feedback.record(self._feedback_ids, "delivered", self.step_num)
        registry = self.repo.read_item("approaches") or "Create [[approaches]] with the initial portfolio."
        return f"# Approach-family registry\n{registry}\n\n" + self.feedback.render(messages)

    def _new_feedback(self):
        return tuple(m["id"] for m in self.feedback.active()) != self._feedback_ids

    def _replan_for_feedback(self):
        self.tui.log("New human feedback queued; replanning before new work.")
        self._push_output("Human feedback arrived after planning. Preserve existing results "
                          "and reconsider the next assignments with the new guidance.")
        return "continue"

    def _execute_plans(self, plans, step_dir, resp):
        if self._new_feedback():
            return self._replan_for_feedback()
        # Receipt means the context produced an accepted plan, not guaranteed compliance.
        self.feedback.record(self._feedback_ids, "acknowledged", self.step_num)
        return super()._execute_plans(plans, step_dir, resp)

    def _task_packet(self, description):
        prefix = f"# Fixed research objective\n\n{self.theorem_text}\n\n# Assignment\n\n"
        if description.startswith(prefix):
            return description  # An archived task resumed after interruption.
        refs = self.repo.resolve_wikilinks(description)
        return prefix + description + (f"\n\n# Frozen referenced materials\n\n{refs}" if refs else "")

    def _handle_spawn(self, plan, step_dir, planner_resp=None):
        if self._new_feedback():
            return self._replan_for_feedback()
        # Freeze before launching threads: the worker and its reviewer see identical evidence.
        plan = {**plan, "tasks": [
            {**task, "description": self._task_packet(task.get("description", ""))}
            for task in plan.get("tasks", [])
        ]}
        return super()._handle_spawn(plan, step_dir, planner_resp)

    def _handle_literature_search(self, plan, step_dir, planner_resp=None):
        if self._new_feedback():
            return self._replan_for_feedback()
        return super()._handle_literature_search(plan, step_dir, planner_resp)

    def _run_worker(self, task, worker_id, archive_path=None):
        prompt = self._task_packet(task.get("description", ""))
        native_tools = self.lean_worker_tools and (
            getattr(self.worker_llm, "vllm", False) or getattr(self.worker_llm, "mistral", False))
        mcp_tools = self.lean_worker_tools and bool(getattr(self.worker_llm, "mcp_config", None))
        instructions = worker_instructions(native_tools or mcp_tools)
        if native_tools:
            return self._run_worker_multi_turn(prompt, instructions, worker_id, archive_path)
        return self._run_worker_single_turn(prompt, instructions, worker_id, archive_path,
                                            use_mcp_tools=bool(mcp_tools))

    def _run_verifier(self, task_desc, worker_output, verifier_id, archive_path=None):
        # Reuse the existing call/retry/truncation path, in a fresh context with no tools.
        prompt = self._task_packet(task_desc) + f"\n\n# Candidate output\n\n{worker_output}"
        return self._run_worker_single_turn(prompt, REVIEWER_POLICY, verifier_id, archive_path)

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
        if not self.budget.should_conclude() and not self._new_feedback():
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

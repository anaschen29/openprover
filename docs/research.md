# Open-ended research mode

This mode reuses OpenProver's planner, workers, independent reviewers, whiteboard,
repository, and saved step history. It adds a budget-driven lifecycle rather than
a second supervisor. Normal theorem-proving and Lean modes remain unchanged.

## Start an allocation

Write a research objective in `objective.md`, including the fixed assumptions and
what would count as progress. Then run:

```bash
openprover --mode research --theorem objective.md \
  --max-time 8h --headless -P 3
```

The positional objective file is also supported. Use a named directory for a
predictable location:

```bash
openprover runs/my-research --mode research --theorem objective.md \
  --max-tokens 200000 --headless -P 3
```

As in existing runs, `--headless` implies autonomous operation. The objective is
snapshotted as `THEOREM.md` for compatibility. Do not modify it during a campaign.
The upper- and lower-bound projects should use separate objective files and run
directories; no new mathematical framework or cross-run messaging is introduced.

## Termination: budget, not proof submission

The planner saves candidate arguments, conjectures, conditional results,
counterexamples, and failed approaches using the existing `write_items` action.
Both `submit_proof` and `submit_lean_proof` are unavailable and are rejected by the
executor if a model nevertheless emits them. Recording a discovery does not stop
research. Review and further investigation can continue until the allocation's
budget threshold. Ordinary interruption and fatal errors can still pause a run.

`--conclude-after` retains the existing final-report reserve (default 0.99).
Budgets are checked at step boundaries: a running model call or parallel batch can
exceed that boundary. **This PR does not provide a hard wall-clock or dollar cap.**
`--max-tokens` is an output-token allocation, not a billable-total-token limit.
Request-level accounting and stricter cancellation remain separate work.

## Continuation: explicit

Resume an interrupted allocation without granting new resources:

```bash
openprover runs/my-research --headless
```

Recorded token usage and the original wall-clock deadline are retained. Downtime
counts against a time allocation. If its budget expired while stopped, the next
invocation finalizes it without launching new research workers.

Opening a finished allocation only prints inspection/continuation instructions;
it makes no model calls and does not require API credentials. Full history is
available with `openprover inspect runs/my-research`.

Grant another allocation only with **both** `--continue` and an explicit budget:

```bash
openprover runs/my-research --continue --max-time 8h --headless
# Or switch the new allocation to an output-token budget:
openprover runs/my-research --continue --max-tokens 200000 --headless
```

The whiteboard, research repository, and step numbering continue from the prior
allocation. Its usage and reports are retained, but its spent tokens are not
charged against the newly authorized allocation. A budget flag without
`--continue`, or `--continue` without a new budget, is rejected. An unfinished
allocation must be resumed, not renewed. `--read-only` cannot be combined with
`--continue`. Do not run two processes against the same directory.

## Reporting: final only

There are no periodic report calls. At the end of each completed allocation:

- `reports/allocation_NNN.md` retains that allocation's final report.
- `DISCUSSION.md` contains the latest final report for compatibility.
- `research_state.json` records allocation status and its budget.

When a report can be synthesized within the remaining token reserve, its usage is
recorded. If the budget is exhausted or synthesis fails, a clearly labeled saved
whiteboard/evidence checkpoint is written instead, without additional model calls.
An interrupted, unfinished allocation remains paused and does not generate a
final report. A report's presence is not a completion signal; explicit state is.

Reports separate findings from conditional claims and unresolved obligations.
They are not proof certificates. Fixed Lean theorem/proof input flags cannot be
combined with research mode; optional Lean tools remain available for research
items through the existing tool configuration.

## Tests

No credentials or paid model calls are needed:

```bash
python -m pytest tests/test_research_budget.py tests/test_research_mode.py
python -m pytest tests -q --ignore=tests/test_tui_keys.py
```

The tests exercise the actual planner loop with deterministic fake clients,
including worker/reviewer execution, rejected early submission, final reporting,
continuation, interruption, and legacy mode behavior.

`tests/test_tui_keys.py` is a pre-existing manual keyboard/terminal playground,
so it is excluded from headless CI rather than treated as an automated test.

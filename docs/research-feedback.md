# Research policy and live feedback

Research mode keeps distinct mathematical approach families in `repo/approaches.md`
(`[[approaches]]`). The coordinator sees the full registry each round and maintains
mechanisms, evidence, gaps, and next questions. Independent exploration precedes
cross-pollination; failed waves trigger new rounds within the authorized budget.
Researchers must return concrete mathematics, not status-only optimism. Reviews
include the assembled proof and can conclude `INCONCLUSIVE`. These are informal
reviews, not formal proof certificates.

Each dispatched task snapshots the fixed objective and its referenced repo items.
The researcher and its independent reviewer receive that same evidence, even if
an item changes later. Unrelated approach histories and other reviewers' judgments
are not automatically shared. Normal theorem-proving modes are unchanged.

Numerical checks are required where meaningful, including edge cases. No Python
or web tools are added here. Without execution tools, agents must label numerical
checks **NOT RUN**, provide a test plan, and keep that obligation open. They must
never claim that proposed code was executed. Passing numerical tests is not proof.

## Send guidance without cancelling work

Run these commands on the machine hosting the run, in another terminal (or over
SSH), using the same run directory. No service, API key, or model call is needed.

```bash
openprover feedback runs/lower --message \
  "Keep the strongest construction, but explore a genuinely different family."

openprover feedback runs/lower --file guidance.md
openprover feedback runs/lower --list

# Replace an earlier instruction using its returned F-... identifier:
openprover feedback runs/lower --message "Focus on duality instead" \
  --supersedes F-EXISTING-ID
```

Messages are atomically published under `feedback/messages/`. The coordinator
checks them when planning and again before dispatching new work. If guidance
arrives during planning, it replans rather than dispatching stale assignments.
Already-running researchers and their reviews finish normally; their results are
retained. This is scheduling-boundary steering, not mid-response interruption.

`feedback/receipts.json` records first delivery and the accepted planning step.
`--list` shows **queued**, **delivered**, **acknowledged**, or **superseded**.
Acknowledged means the planner returned an accepted plan using that context;
it does not certify compliance. The prompt asks it to record each ID and its
response in the whiteboard, which remains inspectable. Delivery may repeat after
a crash; message IDs and receipts prevent mistaking a replay for a new instruction.

Active guidance remains in subsequent planner contexts and across restarts until
superseded. Superseding preserves the original message in the archive. Keep notes
short and supersede stale guidance to avoid accumulating unnecessary context.
Messages are limited to 16,000 characters each. One coordinator writes receipts;
multiple senders may queue messages concurrently. Do not edit published messages.

Feedback does not reset the budget, change the fixed objective, erase findings, or
restart a finished run. A finished run still requires `--continue` and a new budget.
Human mathematical suggestions must be audited like other claims. Conflicts with
the fixed objective must be made explicit, not silently resolved by adding assumptions.

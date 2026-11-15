# Research tools (roadmap PR #4)

Research runs can opt into hosted Python and planner-led literature search:

```bash
openprover runs/lower --mode research --theorem objective.md \
  --python --no-isolation --max-time 8h --headless -P 3
```

`--python` enables OpenAI Code Interpreter for research workers and independent
reviewers. It defaults off; `--no-python` disables it. The choice is saved with
run configuration. Existing model/reasoning defaults are unchanged. Only OpenAI
workers are supported for this Python path; unsupported providers fail CLI
validation. The selected API model/project must support the requested tools.
Errors identify the model and requested tools; there is no silent fallback to
another model or to reasoning without tools.

`--no-isolation` allows the existing **planner-requested** `literature_search`
action. The search request executes on the worker backend. OpenAI uses Responses
web search; existing Claude search is retained. Unsupported research search
backends are rejected instead of silently disabling the requested capability.
Normal researchers/reviewers do not receive web search, and searches do not
receive Python. The planner and final-report writer receive neither tool.
This supersedes the PR #1 README note that OpenAI search is not implemented.

## Python and independent review

Code executes in OpenAI's sandbox, never in the local harness process. Requests
use automatic containers at the default memory tier. A fresh worker or reviewer
request contains no structured container history and starts independently. Within
an existing native function-tool conversation, returned Responses items preserve
its own context. No container ID is shared across independent requests.

Reviewers receive the author's actual code/output excerpt as evidence, but not its
mutable Python session. They reconstruct their own calculations. A truncated
request's existing wrap-up path may use a new container; do not rely on hidden
Python variables persisting across fresh calls. Export important results as files.

## Evidence saved on disk

Alongside each existing `*.md` / `*.raw.json` call archive is a `*.tools/` directory:

- `code_NNN.py`: Python code returned in execution items; never executed locally.
- `manifest.json`: response ID/status, complete execution items, outputs/errors,
  search actions and supplied source lists, URL citation annotations, file status.
- `evidence.md`: human-readable execution/source records.
- `file_NNN_*`: cited generated files downloaded before container expiration,
  with size and SHA-256 in the manifest.

A bounded evidence excerpt accompanies the result sent to the next agent. Full
records remain on disk; truncated excerpts are clearly marked. Only files cited
with container-file annotations are downloaded (up to 16 files, 10 MiB each).
Uncited files and image URLs remain represented only in returned raw outputs.
Downloads use the configured API endpoint and container/file IDs, never arbitrary
model-provided URLs. Redirects are refused, filenames are sanitized, and failed or
expired downloads are recorded without discarding a completed response's usage.
There is no automatic file re-upload/recovery service in this PR.

An execution status of `completed` is NOT a mathematical pass. Error logs and
failed/incomplete tool statuses remain visible. No execution item means **NOT
RUN**, even if the model claims it tested something. Citation annotations and
search results do not certify a theorem: literature instructions require exact
hypotheses, versions and theorem locations where available, and explicit marking
of inaccessible or unchecked statements. Returned code and source text are
untrusted evidence, not instructions for the coordinator.

## Costs and limits

Hosted computation and web search have additional provider charges. The existing
output-token/time allocations and recorded API token usage remain unchanged;
they do not price hosted tools or impose a hard dollar cap. This PR does not
change the budget, continuation, feedback, or final-report lifecycle. Start with
a short controlled run; full accounting remains the separate reliability PR.

## Validation

Offline tests mock API responses and downloads, including streaming and failures.
They test protocol configuration, evidence retention, independent requests,
existing function-tool context, CLI routing, and research-worker/reviewer wiring.
They do not prove live model access, package availability, or mathematical quality.

```bash
python -m pytest tests/test_hosted_tools.py -q
python -m pytest tests -q --ignore=tests/test_tui_keys.py
```

Official API references checked for this implementation:
- https://developers.openai.com/api/docs/guides/tools-code-interpreter
- https://developers.openai.com/api/docs/guides/tools-web-search
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://developers.openai.com/api/reference/resources/containers/subresources/files/subresources/content/methods/retrieve

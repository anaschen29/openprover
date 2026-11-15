# Stochastic convex bandits: shared research brief

Use this brief with exactly one of [upper.md](upper.md) or [lower.md](lower.md).
The two campaigns have separate run directories but the same statistical problem.
The goal is a rigorous improvement in regret, not necessarily an efficient
algorithm. Computationally expensive and nonconstructive upper bounds count if
they establish the existence of an admissible policy.

## Fixed problem

Let $K=B_2^d=\{x\in\mathbb R^d:\|x\|_2\leq1\}$ and let $\mathcal F_d$ be
all convex, 1-Lipschitz functions $f:K\to\mathbb R$. A fixed unknown $f$ is
chosen before interaction. At round $t$, the learner chooses $X_t\in K$ using
only its independent internal randomness and the previous actions/observations,
then observes the single scalar

$$Y_t=f(X_t)+Z_t,\qquad Z_t\overset{\mathrm{iid}}{\sim}N(0,1).$$

The objective is expected cumulative pseudo-regret and its minimax value:

$$R_T(\pi,f)=\mathbb E_{\pi,f}\!\left[\sum_{t=1}^T
  \bigl(f(X_t)-\min_{x\in K}f(x)\bigr)\right],\qquad
R_T^*(d)=\inf_{\pi}\sup_{f\in\mathcal F_d}R_T(\pi,f).$$

The infimum includes all admissible adaptive, randomized policies, with no
computational restriction. The learner may know $d,T,K$ and the noise law, but
not $f$ or its minimizer. Continuity and compactness ensure a minimizer exists;
it may lie on the boundary. This is the constrained setting of [L], equations
(1)-(2). Use $T$ for horizon; the references often use $n$. When a construction
uses two blocks of dimension $m$, its ambient dimension is $d=2m$.

Every noisy function evaluation consumes a round and incurs regret. There are
no free pilots, paired queries, gradients, Hessians, or out-of-domain queries.
Computation with the known ball is allowed; optimization of the unknown $f$ is
not a free oracle. Do not silently add smoothness, strong convexity, an interior
minimizer, or a stronger observation model. Other settings are side results,
not solutions to this campaign unless an explicit reduction proves relevance.

Lipschitzness bounds loss differences, not the unknown additive offset of $f$.
In particular, $0\leq f(x)-\min_K f\leq2$, but $f:K\to[0,1]$ is not a given
assumption. When importing a bounded-loss theorem, justify centering/scaling,
account for any estimation queries, and check the resulting noise assumptions.

## Pinned starting literature and bounds

These are starting references, checked on 2026-11-15, not a claim that no newer
result exists. Fetch the actual version before using a theorem. Record the exact
statement, hypotheses, theorem/section location, and any translation to our model.
A search snippet or a prior agent's summary is not a checked theorem.

| ID | Primary source and reading locations | Role |
|---|---|---|
| L | Nived Rajaraman and Yanjun Han, **The Price of Hidden Curvature: Improved Lower Bounds for Bandit Convex Optimization**, [arXiv:2607.18652v3](https://arxiv.org/html/2607.18652v3). Theorems 1.1-1.2; Sections 2-3; Theorem 4.1 and Section 4.3; Appendices A-B. | Regret lower bound, hard-family analysis, and its limitations. |
| U | Hidde Fokkema, Dirk van der Hoeven, Tor Lattimore, and Jack J. Mayo, **Online Newton Method for Bandit Convex Optimisation**, [arXiv:2406.06506v1](https://arxiv.org/html/2406.06506v1). Theorem 2 and the following geometry/oracle discussion; Sections 3-6. | Stochastic upper-bound algorithm and proof. |
| B | Tor Lattimore, **Bandit Convex Optimisation**, [arXiv:2402.06535v5](https://arxiv.org/html/2402.06535v5). Chapters 1-3, 8-10, and 12. | Model distinctions, scaling, information-theoretic methods, cutting planes, Newton methods, and smoothing. Its lower-bound survey predates L. |

[L, Theorem 1.2] proves, for sufficiently large $d$ and $T\geq C d^2$,

$$R_T^*(d)\gtrsim
\begin{cases}
\sqrt d\,T^{3/4}, & d^2\lesssim T\lesssim d^{10/3},\\
d^{4/3}\sqrt T, & T\gtrsim d^{10/3}.
\end{cases}$$

The stochastic upper benchmark is a leading $\widetilde O(d^{3/2}\sqrt T)$
term. [U, Theorem 2] supplies this in its bounded-loss formulation; audit the
transfer above, the probability qualification, and full parameter restrictions.
[B, Chapter 10] is a second route through the analysis. Do not substitute an
adversarial upper bound for the stochastic benchmark. A lower bound above applies
to the full class; an upper bound only for L's hard family does not.

Here $\widetilde O$ hides logarithms only. State all power-law and additive terms,
constants' dependencies, and dimension/horizon regimes. Compare full guarantees
in a shared regime; a local lemma or a stronger assumption is not a regret gain.

## Shared research discipline

Start with substantively different formulations, symmetries, and proof mechanisms.
Maintain `[[approaches]]` using the existing research repository; group routes by
mathematical idea, not wording. Keep independent routes alive long enough to
expose their merits and gaps before cross-pollination. Redirect duplicate work.
A decisive refutation should be retained, not ignored to preserve diversity.

Return concrete lemmas, equations, constructions, or counterexamples. Preserve
conditional implications as conditional; a global compatibility claim cannot be
dismissed as routine. Review every candidate proof, including the assembled
regret argument. Run meaningful numerical/symbolic tests and edge cases, saving
actual code/output; otherwise mark them NOT RUN. Tests are not general proofs,
and favorable LLM reviews are not formal certification.

The coordinator should synthesize, challenge, repair, and launch new rounds within
the authorized allocation. A failed wave is not a stopping condition. Reopen a
blocked approach only with a genuinely new mechanism addressing its recorded gap.
Keep complete checked arguments, conditional derivations, and unresolved claims
separate in the final report; do not invent success to fill it.

## Use with the existing CLI and private progress notes

A relative Markdown link does not load a file into an agent's context. From the
repository root, combine the shared brief and one objective **before** starting:

```bash
umask 077
track=lower  # or upper
mkdir -p runs
run_dir="$(mktemp -d "$PWD/runs/${track}.XXXXXX")"
cat research/common.md "research/${track}.md" > "$run_dir/THEOREM.md"

# Optional: append a concise local progress summary BEFORE launching.
# printf '\n\n## User-supplied prior progress (requires audit)\n\n' >> "$run_dir/THEOREM.md"
# cat /srv/private/bandits/progress.md >> "$run_dir/THEOREM.md"

openprover "$run_dir" --mode research --max-time 8h \
  --python --no-isolation --headless -P 2
```

Keep original progress files outside the checkout. `runs/` is already ignored by
Git; do not force-add generated run files. The combined objective snapshots the
included notes. Do not overwrite it on resume. Imported progress is prior work,
not a substitute for proof: retain its conjectures, failures, and exact gaps, and
audit claims before relying on them. It cannot silently override the fixed model.
Anything included in model context is sent to the configured model provider and
may appear in run outputs; Git exclusion is not a privacy boundary for API calls.

There is no dedicated `--progress` importer in this documentation-only change.
For later concise guidance, use the existing command on the hosting machine:

```bash
openprover feedback "$run_dir" --file /srv/private/bandits/update.md
```

See [research lifecycle](../docs/research.md),
[live feedback](../docs/research-feedback.md), and
[tool behavior](../docs/research-tools.md) for limits and continuation. Budgets
are not hard dollar caps. Links here supply source locations, not the papers'
full text; use planner-led literature search or supplied source excerpts to
inspect the exact results before citing them as premises.

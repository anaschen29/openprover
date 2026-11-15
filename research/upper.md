# Upper-bound campaign: improve stochastic convex bandit regret

Run together with [common.md](common.md); its model, definitions, and evidence
rules are binding. This is an open research objective, not an assertion that a
particular conjectured rate must be true.

## Objective and current upper-bound summary

Find an admissible policy $\pi$ and prove a uniform guarantee

$$\sup_{f\in\mathcal F_d} R_T(\pi,f)\leq U(d,T)$$

that genuinely improves the applicable full regret benchmark. Computational
efficiency is **not required**: expensive optimization, minimax/existence
arguments, and nonconstructive policies are eligible, provided the policy is
well-defined, measurable, and uses only permitted observations.

The preferred long-horizon target is a dimension-power improvement over the
$\widetilde O(d^{3/2}\sqrt T)$ leading term, such as
$\widetilde O(d^{3/2-\eta}\sqrt T)$ for fixed $\eta>0$. This expression is a
search target, not a promised result. Other genuine regime-specific regret
improvements are useful; disclose any worsening elsewhere, horizon thresholds,
and additional terms. Constants, logarithms, empirical gains, and intermediate
lemmas should be recorded honestly, not relabeled as a dimension-power gain.

[U: Fokkema et al., Theorem 2](https://arxiv.org/html/2406.06506v1) gives a
high-probability stochastic guarantee $M d^2\sqrt T\,\mathrm{polylog}(T,d,1/\delta)$
for bounded convex losses. Its geometry factor satisfies
$M\in[d^{-1/2},d^{-1/4}]$: $M=d^{-1/2}$ is available without an efficiency
requirement, and efficiently for symmetric domains with the specified oracles.
The Euclidean ball is symmetric. The method combines convex extensions,
surrogate losses, and online Newton analysis; Sections 3-6 develop these pieces.
Do not confuse this geometry factor $M$ with our ambient dimension or a generic
numerical test instance.

[B: Lattimore, Chapter 10](https://arxiv.org/html/2402.06535v5) develops the
stochastic Newton argument; Chapter 12 covers Gaussian smoothing and estimators.
Use Chapters 8-9 for genuinely different information-theoretic and cutting-plane
routes. These are reading directions, not a requirement to stay within Newton
methods. Keep the bounded-loss normalization distinct from our fixed model.

## First tasks: establish a comparable baseline, then isolate losses

Reconstruct the reference guarantee with exact assumptions and all terms. Resolve
the unknown additive offset, constant noise normalization, allowed geometric
oracles, and any initialization cost. A proposed centering reduction must estimate
its center from counted observations rather than assume knowledge of $f(0)$.

Convert any high-probability result to the expected-regret objective explicitly.
For this unit-ball Lipschitz class the deterministic bound is $2T$, so a regret
guarantee $B(d,T,\delta)$ outside an event of probability $\delta$ gives

$$\mathbb E[\mathrm{Reg}_T]\leq B(d,T,\delta)+2T\delta.$$

Track any additional failure events and initialization separately. This inequality
does not by itself justify transferring the source theorem's assumptions.

Make a compact account of where dimension enters the complete proof: estimation,
concentration, geometry, smoothing, localization, and parameter constraints.
For each proposed saving, identify the exact term and propagate it through the
whole bound. Do not spend every round refining one term while another dominates.

## Initial portfolio, not a fixed assignment scheme

Explore materially different mechanisms: sharpen a specific proof inequality;
change the estimator or exploration geometry; use a localization/cutting-plane
formulation; or pursue an information-theoretic/existence argument without a
runtime constraint. Symmetries, duality, and adaptive changes of coordinates may
suggest additional routes. These examples are starting ideas, not evidence that
any route works or a limit on the number of families.

Keep several independent approaches through multiple rounds, using the common
approach registry. Cross-pollinate only after the actual mechanisms and gaps are
visible. Modern full-information optimizers are inspiration, not bandit algorithms
until their required feedback and estimation error are accounted for.

## Required result and adversarial audit

A candidate improvement must contain the exact theorem and regime; a policy or
valid existence argument; every observation it needs; the full regret proof;
parameter choices satisfying all constraints; and a like-for-like comparison to
the reference bound. A restricted-family guarantee is not a full-class upper bound.

Challenge the candidate on boundary minimizers, flat directions, nonsmooth losses,
small dimensions/horizons, and feasible transition regimes. Verify that projection,
conditioning, stopping times, restarts, or approximation errors do not hide the
claimed saving. Out-of-domain evaluations and extra function samples are not free.
Numerical tests must have actual tool output and must not be treated as proof.

If only an intermediate statement survives, save its proof and the exact missing
implication to regret. Feed concrete reviewer objections into repair tasks or new
formulations. Continue within the authorized budget; the final report must say
whether the improvement is complete, conditional, or refuted.

Optional private progress supplied with this objective is starting evidence to
re-audit, not a mandate to keep working on the same family or to assume its
unproved inequalities. Never commit private summaries to the repository.

# Lower-bound campaign: improve stochastic convex bandit minimax regret

Run together with [common.md](common.md); its model, definitions, and evidence
rules are binding. This campaign is independent of the upper-bound campaign.

## Objective and current lower-bound summary

Prove a stronger minimax expected cumulative-regret lower bound:

$$\forall\pi\ \exists f\in\mathcal F_d:\quad R_T(\pi,f)\geq L(d,T),$$

where $\pi$ ranges over **all** permitted adaptive, randomized policies, without
computational restrictions. The hard instance may depend on $d,T$ and the policy,
but must be fixed before interaction, not chosen in response to realized noise.
A prior-based proof must have the quantifiers needed to imply this statement.

[L: Rajaraman-Han v3, Theorem 1.2](https://arxiv.org/html/2607.18652v3) is the
pinned regret benchmark:

$$L_0(d,T)\asymp
\begin{cases}
\sqrt d\,T^{3/4}, & d^2\lesssim T\lesssim d^{10/3},\\
d^{4/3}\sqrt T, & T\gtrsim d^{10/3},
\end{cases}$$

for sufficiently large dimension and the theorem's constant-factor restrictions.
This notation specifies the order of the established lower bound, **not** the
minimax value of the full class. The preferred long-horizon target is a power
improvement, for example $d^{4/3+\eta}\sqrt T$ with fixed $\eta>0$, on a precisely
stated nonempty regime. The target is not an assumption. Check compatibility with
known upper bounds and the trivial $2T$ ceiling. Keep simple regret and cumulative
regret separate; an estimation theorem is not the desired conclusion on its own.

## What the reference construction teaches

L hides a quadratic signal behind an unknown linear-map tube. Sections 2-3 use
adaptive information and estimation arguments; Appendix A checks the family.
Theorem 4.1 and Appendix B give a matching, up-to-logs upper bound **for that
bounded family**, with the scale parameters $(r,\varepsilon)$ known to the learner.
Section 4.3 explains why tuning its tube width alone does not improve the exponent;
some proposed-extension objections there are explicitly heuristic. Preserve those
qualifications rather than treating them as a universal impossibility theorem.

Read the family-specific upper-bound policy as an adversarial attack on a proposed
construction. A new lower-bound mechanism must explain what changes and why the
old escape strategy no longer applies. Unknown-scale mixtures or other alterations
need their own argument; renaming a parameter is not a new mechanism.

Useful additional background is
[B: Lattimore, Chapters 2, 7-9](https://arxiv.org/html/2402.06535v5), especially
linear/quadratic comparisons, Bayesian formulations, and information methods.
That book predates L; its older lower-bound summary is not the campaign target.

## Obligations every successful route must close

1. **Admissibility:** define the functions, observation laws, parameter ranges,
   and prior/packing. Prove convexity, the unit Lipschitz bound, feasible minima,
   and the fixed unit-Gaussian noise model. Account for ambient dimension and
   any conditioning/truncation of a prior. Function rescaling changes signal to
   noise; instance-dependent offsets can change observable information.
2. **Adaptive hardness:** identify what the learner must learn and bound the
   information obtainable under arbitrary history-dependent actions. A fixed-design
   calculation or a lower bound for one algorithm is insufficient.
3. **Regret consequence:** prove the cost of exploration and/or acting without
   the needed information, over the full trajectory. State and prove any
   testing/estimation-to-cumulative-regret reduction instead of assuming it.
4. **Feasible optimization:** choose all scales together, verify every inequality,
   and compare the resulting full bound to $L_0$ on the declared regime. Preserve
   dimensional losses from geometry, normalization, and boundary cases.

For example, for the *same* policy and two fixed functions with unit Gaussian
observations, the sequential KL identity is

$$D_{\mathrm{KL}}(P_f^\pi\|P_g^\pi)
=\frac12\,\mathbb E_f^\pi\sum_{t=1}^T(f(X_t)-g(X_t))^2.$$

The expectation is under the history-dependent actions induced by $f$, not a
fixed query design. Any useful uniform bound on this expression still needs proof.
Other information methods are welcome; do not force all families into this identity.

## Exploration and audit policy

Start independent routes with different geometric, information-theoretic, or
variational mechanisms. Possible directions include altered hiding mechanisms,
convex-envelope constructions with compatible global geometry, multiscale
families, and dual/Bayesian formulations. These are proposals, not established
constructions. Maintain the family registry and redirect superficial duplicates.

Use adversarial workers to seek informative query locations, inexpensive adaptive
strategies, and counterexamples to the claimed separation or information inequality.
Check low-dimensional instances and limiting/transition scales with executable
calculations where meaningful. Finite experiments cannot establish the universal
policy quantifier; an explicit counterexample can refute a proposed sublemma.

Reject parameter-counting alone, sums of incompatible local constructions, an
unproved global compatibility claim called routine, and unexplained conversion
from sample complexity to regret. Record an obstruction with its exact scope:
a failure of one proof is not automatically a failure of the whole family.

Every round must return concrete mathematics and the first unresolved implication.
Repair a route only with a new ingredient that addresses its known objection;
otherwise launch a different formulation. Continue until the authorized allocation
ends. Report a complete proof only if the assembled argument survives audit;
otherwise give the strongest supported derivation and its exact remaining gap.

Private progress notes may supply useful constructions and counterexamples. Keep
them outside Git, retain their qualifications, and re-audit decisive claims before
using them as premises. Do not let earlier summaries collapse all workers into one
route before independent exploration has occurred.

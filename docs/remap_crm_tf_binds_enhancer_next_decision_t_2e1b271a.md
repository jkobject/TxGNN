# ReMap CRM `tf_binds_enhancer` next-route decision

Kanban task: `t_2e1b271a`
Status: `route C complete`; full CRM remains `support-only`; no full edge/evidence build authorized; no active execution supervision.

## Decision

Choose route C for the full/unbounded ReMap CRM line: keep the full ReMap CRM artifact as a sharded support/QA sidecar only until a stricter reduction policy exists.

Route C is complete as the current product/control-plane outcome. Existing scientific artifacts and receipts remain preserved, but ReMap now has no active watchdog, resume path, SSH-liveness check, health verdict, recovery reason, or notification route. Any future aggregate reducer or external full materialization is a new explicitly approved project, not continuation of an active ReMap lane.

This does not reverse the ontology direction from the bounded pilot: reviewed ReMap CRM/peak evidence can support the canonical relation label `tf_binds_enhancer` when the edge/evidence semantics are explicitly scoped and validated. It only says the current full/unbounded CRM artifact must not be converted into active `tf_binds_enhancer` graph topology by semantic shortcut.

## Evidence reread

- Bounded pilot `t_a405fe3b` and reviewer `t_95856c15`: accepted as `pilot accepted` / `staged-only`, with 1,224,536 `tf_binds_enhancer` edges and 6,356,561 evidence rows over the bounded first80 chr1 CRM/peak scope. The reviewer independently validated endpoint anti-joins, duplicate/integrity checks, evidence support gates, motif-only=0, and report/code presence.
- Full feasibility gate `t_f8cc9e4b` and reviewers `t_6835ea5c` / `t_f11856d2`: accepted as a validated feasibility/policy gate, not a full edge/evidence artifact. Preserving the bounded per-observed-peak/CRM evidence semantics at full scale implies 24,453,482,386 candidate rows and about 4,853.33 GiB lower-bound parquet before observed-peak evidence multiplicity.
- Sidecar promotion state `t_f2a2952e`: full/unbounded CRM support sidecar has been written under `gs://jouvencekb/kg/v2/features/remap_crm_tf_enhancer_support_full/` with 24 chromosome summary shards plus `tf_global_summary.parquet`, but it is `review-required` and explicitly support-only/non-topological. It is not `observed_binding`, not `tf_binds_enhancer` edge/evidence, and not inferred edges.

## Why not route A now

Route A would authorize a compact aggregate staged edge/evidence schema by changing semantics from per-observed-peak evidence to aggregate CRM support evidence. That may be useful later, but it is a new biological/ML policy decision: the full aggregate artifact would no longer preserve the accepted bounded pilot evidence model. No task should silently create active graph edges from the compact sidecar until a reduction policy defines which aggregates become graph assertions, how evidence rows encode loss of peak multiplicity, leakage controls, score calibration, and reviewer acceptance gates.

## Why not route B now

Route B would require external chunked compute/storage plus full all-peak overlap acquisition for a tens-of-billions-row materialization. The current board has no explicit product approval or infrastructure budget for a 24.45B-row / multi-TiB edge/evidence build, and reviewers already classified this as a policy/resource gate. Do not create build cards for this path without explicit human approval.

## Operating policy from this decision

- Label the full CRM sidecar as `support-only` / feature-QA material.
- Keep the bounded `t_a405fe3b` artifact as `pilot accepted` / `staged-only`; it is not canonical/full production.
- Keep full CRM-derived `tf_binds_enhancer` graph topology `blocked` until a future human-approved reduction policy or external-materialization authorization exists.
- Do not create dev/test/review build cards from this decision. The next actionable work is policy design only if Jérémie explicitly wants aggregate reduction semantics, or infrastructure planning only if he explicitly wants full materialization.
- Do not claim `production/full done`, canonical edge promotion, or canonical evidence promotion for ReMap-derived `tf_binds_enhancer` from this line.

## Residual options requiring future approval

1. `review-required` aggregate-reduction policy: define a compact staged edge/evidence schema, reduction thresholds, leakage guardrails, score fields, and validation gates before any builder materializes active graph edges.
2. External full materialization: provision compute/storage and acquire/recompute full all-peak overlap inputs before any tens-of-billions-row build card.

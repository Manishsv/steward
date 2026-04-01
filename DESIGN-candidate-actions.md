# Phase 2 (Draft): Candidate Action Planning

Goal: bridge natural-language user requests to a **small set of governed candidate actions**, then pick the safest effective allowed action.

## Problem

Today Steward governs **explicit** `proposal.action` calls (e.g. `openshell.draft_policy.get`). Users, however, ask natural-language requests like:

> “Please make npm installs work in this sandbox.”

We need a path that:
- proposes multiple possible next actions
- evaluates each candidate under governance
- selects the safest allowed option
- executes it (or returns “needs approval” / “denied” with a clear next step)

## Candidate Action Model

A candidate represents *one possible next action*:

- `candidate_id` (string)
- `label` (short human description)
- `proposal` (existing Steward `ActionProposal`)

Steward evaluation returns:
- `decision` (`allow|deny|needs_approval`)
- `rationale`
- `audit_id`

## Evaluation endpoint

Add a bulk endpoint to evaluate multiple candidates at once:

- `POST /action/evaluate`
  - request: `{ "candidates": [ { "id": "...", "label": "...", "proposal": { ... } } ] }`
  - response: `{ "evaluations": [ { "id": "...", "label": "...", "decision": "...", "rationale": "...", "audit_id": "..." } ] }`

This does not change existing `/action/*` API shapes.

## Narrow initial candidate set (npm installs)

For request: “make npm installs work in this sandbox”:

- **Approve the npm registry rule** (best-effort, governed mutation)
  - action: `openshell.draft_policy.approve_matching`
  - parameters: `sandbox_name`, `match.host=registry.npmjs.org`, `match.port=443`, `match.binary_path=/usr/local/bin/node`

- **Fetch draft policy** (read-only, informational)
  - action: `openshell.draft_policy.get`

- **Inspect sandbox mode** (placeholder; likely unsupported in Phase 2)
  - action: `openshell.sandbox.inspect_mode` (expected deny-by-default until implemented)

- **Request sandbox mode patch** (placeholder; expected deny-by-default)
  - action: `openshell.sandbox.request_mode_patch`

## Selection logic (NemoClaw)

Selection runs in NemoClaw:
- Prefer **allowed** candidates that directly satisfy the request (for npm: approve_matching).
- Fall back to the safest allowed informational candidate (`draft_policy.get`) if no effective mutation is allowed.

Operator mode should show all candidate evaluations and the selected candidate.


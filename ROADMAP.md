# Steward Roadmap

This document describes the **next governance expansion** beyond Phase 1A draft-policy actions.

## Current scope (Phase 1A)

- Steward governs OpenShell **draft network-policy chunks**:
  - `openshell.draft_policy.get`
  - `openshell.draft_policy.approve` / `reject` / `edit`
  - `openshell.draft_policy.approve_all` / `clear`
- NemoClaw/OpenClaw triggers these via `/nemoclaw policy ...`
- Steward calls OpenShell over gRPC and records an audit record per authorize/execute.

## Recommended next governed action family (Phase 1B): sandbox lifecycle changes

The narrowest next “high-value” family is **OpenShell sandbox lifecycle operations** invoked by NemoClaw’s blueprint runner:

- create sandbox (`openshell sandbox create …`)
- stop sandbox (`openshell sandbox stop …`)
- remove sandbox (`openshell sandbox remove …`)

Why this next:
- It is **user-triggered** and has clear blast radius (creates/removes execution environment).
- It’s already a critical boundary in the stack: these actions control *where* code runs.
- It’s a small and coherent family with clear risk tiers.

### Proposed Steward action shapes

All remain compatible with the existing Steward API (`proposal.action`, `proposal.purpose`, `proposal.context`, `proposal.parameters`).

- **Create**
  - `proposal.action`: `openshell.sandbox.create`
  - `proposal.parameters`:
    - `sandbox_name` (string)
    - `from_image` (string)
    - `forward_ports` (list[int], optional)

- **Stop**
  - `proposal.action`: `openshell.sandbox.stop`
  - `proposal.parameters`: `sandbox_name`

- **Remove**
  - `proposal.action`: `openshell.sandbox.remove`
  - `proposal.parameters`: `sandbox_name`

### Risk classification (initial)

- `openshell.sandbox.create`: **medium**
- `openshell.sandbox.stop`: **medium**
- `openshell.sandbox.remove`: **high** (destructive)

### Steward decision path

Initial governance rules (minimal, safe defaults):
- Require `purpose` to be non-empty.
- Require `role=operator` for stop/remove by default (or `needs_approval`).
- Never auto-allow destructive remove without explicit approval in non-operator contexts.

### NemoClaw hook points (smallest insertion)

NemoClaw currently performs these operations in the blueprint runner:

- `NemoClaw/nemoclaw/src/blueprint/runner.ts`
  - `actionApply()`:
    - calls `openshell sandbox create …`
  - `actionRollback()`:
    - calls `openshell sandbox stop …`
    - calls `openshell sandbox remove …`

Smallest insertion point:
- Wrap each lifecycle call with a Steward authorize/execute roundtrip, mirroring the draft-policy flow:
  1) construct `ActionProposal`
  2) call `/action/authorize`
  3) if allowed, call `/action/execute` (Steward performs the OpenShell operation)

Note: this requires Steward to gain an OpenShell integration for sandbox lifecycle operations. This can be done either via:
- OpenShell gRPC (preferred if APIs exist), or
- a constrained “OpenShell CLI adapter” (last resort; keep disabled by default).

### User-visible behavior

Business mode:
- “Sandbox creation started / blocked / approval required”
- “This is a high-impact operation” banner for remove

Operator/details mode:
- show correlation ids (authorize/execute audit ids)
- show OpenShell response payload


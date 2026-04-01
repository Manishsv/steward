# Steward Milestone Checkpoint (Phase 1A)

This is a release-style checkpoint for the first credible Steward milestone: **governed OpenShell draft-policy actions exposed via NemoClaw/OpenClaw**.

## What is complete

- **Steward service**
  - FastAPI endpoints:
    - `POST /action/authorize`
    - `POST /action/simulate`
    - `POST /action/execute`
    - `GET /audit/{id}`
  - Phase 1A governance for OpenShell draft-policy actions:
    - get / approve / reject / edit / approve_all / clear
  - Stable proposal hashing (`proposal_id`) and canonicalization.
  - Structured identity parsing for `requested_by` / `approved_by`.
  - Consistent external refs for sandbox / chunk / operation.
  - Safer failure shaping: OpenShell errors are returned as **HTTP 403** with `detail.audit_id`, plus a `result` payload for diagnostics.

- **NemoClaw / OpenClaw integration**
  - `/nemoclaw policy ...` routes through Steward before OpenShell.
  - Fail-closed behavior when Steward is unavailable.
  - Business-friendly default output for `policy get`, with explicit operator/detail and raw modes.
  - Deployment workflow scripted for rapid iteration (`scripts/deploy-nemoclaw-plugin.sh`).

## Current trust model (explicit)

- **OpenShell** enforces runtime constraints (sandboxing, network policy).
- **Steward** decides and audits “should we do this?” and *then* executes the OpenShell action (Phase 1A: draft policy gRPC).
- **OpenClaw/NemoClaw** is user-facing; it must:
  - call Steward first,
  - present outcomes clearly,
  - hide sensitive correlation ids by default.

## How approvals work (Phase 1A)

- Draft-policy actions are assigned risk tiers.
- High-risk (`approve_all`, `clear`) are not auto-allowed.
- When Steward returns `needs_approval`, NemoClaw stops and instructs the user/operator on next steps.

## Audit persistence (current)

- Audit store is **in-memory**. Restarting Steward clears `/audit/{id}`.

## How to run and test (quick)

### Host: run Steward

```bash
cd Steward
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn steward_service.main:app --reload --host 0.0.0.0 --port 8000
```

### Sandbox: run OpenClaw TUI

```bash
env STEWARD_URL="http://host.openshell.internal:8000" \
  OPENCLAW_STATE_DIR="/sandbox/.openclaw-data" \
  OPENCLAW_CONFIG_PATH="/sandbox/.openclaw-data/openclaw.json" \
  openclaw tui
```

### TUI: governed policy commands

- `/nemoclaw policy get <sandbox>`
- `/nemoclaw policy get <sandbox> details`
- `/nemoclaw policy get <sandbox> raw`
- `/nemoclaw policy approve <sandbox> <chunk_id>`
- `/nemoclaw policy reject <sandbox> <chunk_id> <reason...>`
- `/nemoclaw policy edit <sandbox> <chunk_id> <json>`
- `/nemoclaw policy approve-all <sandbox>`
- `/nemoclaw policy clear <sandbox>`

## Remaining backlog after this milestone

- **Audit durability**: persist audit records (file/SQLite) and add retention policy.
- **Approval workflow**: real “approval state” storage and explicit approval endpoints (beyond “needs_approval” return value).
- **Next governed family (Phase 1B)**: sandbox lifecycle operations (see `ROADMAP.md`).
- **Observability**: structured logging and optional trace id propagation end-to-end.
- **Hardening**: rate limiting, authn/z for Steward endpoints, and tighter schema validation at the boundary.


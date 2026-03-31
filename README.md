# Steward

Steward is the governance plane between agents and execution.

It answers the question: **“Should this action be allowed, and under what approvals?”** and produces an **auditable record** of that decision and the attempted execution.

Position in the stack:

Agent
→ Steward
→ OpenShell
→ Domain systems / tools / registries / APIs

Responsibilities:
- evaluate proposed actions
- authorize or deny actions
- require approval where needed
- simulate actions before execution
- record audit trails
- attach purpose, role, and context to actions

## Why Steward is required

OpenShell is an enforcement runtime (sandbox + network/process/policy enforcement). Steward sits *above* it to provide:

- **Consistent governance**: one place to apply policy logic across many action types.
- **Human-in-the-loop controls**: force approvals for risky operations (bulk changes, security-flagged changes, destructive actions).
- **Traceability**: stable proposal identifiers, decisions, and external references for incident review and compliance.

## Practical examples

### Financial agent (high stakes)

Scenario: the agent needs to pull market data, read a bank statement export, and draft a transfer request.

- **Network expansions**: if a new API host is blocked, OpenShell surfaces draft policy chunks; Steward can require an operator to approve only the specific endpoint/binary pair (and record why).
- **Bulk approvals blocked**: `approve_all` / `clear` are high risk in Phase 1A and won’t be auto-allowed, reducing “approve everything” mistakes.
- **Auditability**: every allow/deny/execute has an `audit_id` and stable `proposal_id` for review.

### Personal assistant (privacy-sensitive)

Scenario: the assistant needs to connect to email/calendar providers and occasionally to a new SaaS domain.

- **Least privilege by default**: new outbound endpoints start blocked; approvals are explicit and scoped.
- **Role-aware gating**: non-operator callers can be forced into `needs_approval` for policy mutations.
- **Traceability**: `external_refs` capture sandbox name + operation so you can answer “what changed and when?” quickly.

### Dev assistant (day-to-day engineering)

Scenario: the agent needs to install packages, call GitHub APIs, and fetch docs from the internet.

- **Fast iteration**: use `openshell.draft_policy.get` to see what was blocked, then approve targeted chunks.
- **Safety rails**: keep high-risk bulk operations behind explicit approvals.

## Minimal service (scaffold)

### Quick setup (local)

```bash
cd Steward
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn steward_service.main:app --reload --port 8000
```

### Make Steward reachable from a sandbox

If OpenClaw/NemoClaw runs inside an OpenShell sandbox, `127.0.0.1:8000` is **inside the sandbox**, not your host.
Run Steward bound to all interfaces on the host:

```bash
uvicorn steward_service.main:app --reload --host 0.0.0.0 --port 8000
```

From inside the sandbox, the usual host bridge name is:

- `http://host.openshell.internal:8000`

### API surface (stable)
- `POST /action/authorize`
- `POST /action/simulate`
- `POST /action/execute`
- `GET /audit/{id}`

The service stores audit records **in-memory** in this scaffold. Restarting `uvicorn` clears previous `/audit/{id}` records.

## Phase 1A (OpenShell draft policy governance)

Phase 1A focuses on governing OpenShell’s **draft network-policy chunks** (approve/reject/edit) via gRPC.

Supported `proposal.action` values:

- `openshell.draft_policy.get` (low risk)
- `openshell.draft_policy.approve` / `reject` / `edit` (medium risk)
- `openshell.draft_policy.approve_all` / `clear` (high risk; never auto-allowed in Phase 1A)

What Steward does in Phase 1A:
- **Plans** the intended OpenShell operation(s) (`/action/simulate`)
- **Authorizes** based on risk tier + role (`/action/authorize`)
- **Executes** the gRPC call when allowed (`/action/execute`)
- **Audits**: stores decision basis + external refs (`/audit/{id}`)

### Configure OpenShell gRPC (mTLS)

OpenShell gRPC typically requires **mTLS**. Steward reads these env vars at startup (restart `uvicorn` after changes):

```bash
export STEWARD_OPENSHELL_GRPC_ENDPOINT="localhost:8080"
export STEWARD_OPENSHELL_TLS_TARGET_NAME="localhost"   # must match server cert SAN/CN
export STEWARD_OPENSHELL_TLS_CA_PATH="$HOME/.config/openshell/gateways/<gateway>/mtls/ca.crt"
export STEWARD_OPENSHELL_TLS_CERT_PATH="$HOME/.config/openshell/gateways/<gateway>/mtls/tls.crt"
export STEWARD_OPENSHELL_TLS_KEY_PATH="$HOME/.config/openshell/gateways/<gateway>/mtls/tls.key"
```

To discover `<gateway>`:

```bash
ls "$HOME/.config/openshell/gateways"
```

### Test (read-only)

```bash
curl -sS -X POST localhost:8000/action/execute \
  -H 'content-type: application/json' \
  -d '{"proposal":{"action":"openshell.draft_policy.get","purpose":"mtls test","role":"operator","context":{"requested_by":"user:me"},"parameters":{"sandbox_name":"manz"}}}' | jq .
```

If successful, you’ll see an `executed` response with `result.steps[0]` containing `draft_version` and `chunks`.

## NemoClaw / OpenClaw integration quickstart (draft-policy only)

This is the first OpenClaw-visible integration stage: a user triggers a draft-policy action (like “get”), NemoClaw calls Steward first, then (if allowed) Steward calls OpenShell via gRPC.

### 1) Trust the NemoClaw plugin explicitly

OpenClaw warns if `plugins.allow` is empty. In the sandbox, edit:

- `/sandbox/.openclaw-data/openclaw.json`

Ensure it includes:

```json
{
  "plugins": {
    "allow": ["nemoclaw"]
  }
}
```

Then fully restart `openclaw tui`.

### 2) Ensure NemoClaw can find Steward

Preferred: set the env var when launching the OpenClaw TUI inside the sandbox:

```bash
env STEWARD_URL="http://host.openshell.internal:8000" \
  OPENCLAW_STATE_DIR="/sandbox/.openclaw-data" \
  OPENCLAW_CONFIG_PATH="/sandbox/.openclaw-data/openclaw.json" \
  openclaw tui
```

Notes:
- Some environments sanitize extension env vars. NemoClaw is implemented to default to `http://host.openshell.internal:8000` when it detects it’s running in the OpenShell sandbox, but setting `STEWARD_URL` is still recommended.

### 3) Run the governed flow

In the OpenClaw TUI:

- `/nemoclaw policy get <sandbox_name>`

Example:

- `/nemoclaw policy get manz`

### 4) If you see “Steward unavailable”

From inside the sandbox, check reachability:

```bash
curl -sS -i "http://host.openshell.internal:8000/openapi.json" | head -n 1
```

- If it’s not `200`, Steward isn’t reachable (wrong bind address, wrong URL, or host firewall).

### 5) If you see 403 from inside the sandbox

This is usually OpenShell network policy blocking the sandbox process (often `/usr/local/bin/node`) from reaching Steward on the host.
Fetch the latest draft chunks (`/nemoclaw policy get ...`) and approve the chunk that corresponds to `host.openshell.internal:8000` for the relevant binary.

### If a call returns 403

Steward returns a structured `403` with an `audit_id` when:
- the governance decision is not allowed, or
- an upstream OpenShell call fails (connectivity, TLS, auth, etc.)

Inspect the underlying error via:

```bash
curl -sS localhost:8000/audit/<audit_id> | jq '.payload.result'
```

Also useful:

```bash
curl -sS localhost:8000/audit/<audit_id> | jq '.payload.audit'
```

This includes stable identifiers (like `proposal_id`) and consistent `external_refs` (sandbox name, chunk id, and the OpenShell operation).

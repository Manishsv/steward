# Steward

Steward is the governance plane between agents and execution.

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

## Minimal service (scaffold)

Run:

```bash
cd Steward
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn steward_service.main:app --reload --port 8000
```

Endpoints:
- `POST /action/authorize`
- `POST /action/simulate`
- `POST /action/execute`
- `GET /audit/{id}`

## Phase 1A (OpenShell draft policy governance)

Steward supports a draft-policy subset of OpenShell via gRPC:

- `openshell.draft_policy.get` (low risk)
- `openshell.draft_policy.approve` / `reject` / `edit` (medium risk)
- `openshell.draft_policy.approve_all` / `clear` (high risk; never auto-allowed in Phase 1A)

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

### If a call returns 403

Steward returns a structured `403` with an `audit_id` when:
- the governance decision is not allowed, or
- an upstream OpenShell call fails (connectivity, TLS, auth, etc.)

Inspect the underlying error via:

```bash
curl -sS localhost:8000/audit/<audit_id> | jq '.payload.result'
```

### Notes

- **Audit storage is in-memory** in this scaffold. Restarting `uvicorn` clears previous `/audit/{id}` records.
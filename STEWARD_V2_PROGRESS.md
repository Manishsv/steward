# Steward v2 implementation progress

## Milestone: Full approval happy path (proven)

**What was fixed / tightened**

1. **`steward_resume_proposal_id` resolution** — `/action/execute` resume now uses the same `_resolve_governance_proposal_for_approval` logic as `POST /approval-requests` (storage UUID, `decision_record_id`, or stable content `proposal_id`). Resume and approval creation stay aligned.
2. **Effective governance decision on approved execute** — When an `ApprovalRequest` is `approved` and execute applies the bypass, a **new `DecisionRecord`** is persisted with `decision=allow` (`plan_exec`), so `GET /decision-records/{id}` on the **execute** audit matches runtime (the authorize-time record can remain `needs_approval` for history).

**Tests added:** `tests/test_approval_happy_path.py` (`TestApprovalHappyPath`)

**Approval lifecycle status:** **Fully proven in tests** for: authorize → `POST /approval-requests` → `POST .../decision` (approved) → `/action/execute` with `steward_resume_proposal_id` + `approval_request_id`; blocked execute without valid approval; resume using content hash for `steward_resume_proposal_id`.

**Exact curl (replace sandbox + chunk)**

```bash
BASE=http://127.0.0.1:8000
# 1) Authorize (agent + approve → needs_approval)
AUTH_JSON=$(curl -sS -X POST "$BASE/action/authorize" -H 'content-type: application/json' -d '{
  "proposal": {
    "action": "openshell.draft_policy.approve",
    "purpose": "approval path",
    "role": "agent",
    "parameters": { "sandbox_name": "YOUR_SBX", "chunk_id": "YOUR_CHUNK" }
  }
}')
AUDIT_ID=$(echo "$AUTH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['audit_id'])")
AUDIT=$(curl -sS "$BASE/audit/$AUDIT_ID")
GP=$(echo "$AUDIT" | python3 -c "import sys,json; print(json.load(sys.stdin)['governance_proposal_id'])")

# 2) Approval request + approve
AR_JSON=$(curl -sS -X POST "$BASE/approval-requests" -H 'content-type: application/json' \
  -d "{\"governance_proposal_id\":\"$GP\"}")
AR_ID=$(echo "$AR_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -sS -X POST "$BASE/approval-requests/$AR_ID/decision" -H 'content-type: application/json' \
  -d '{"decision":"approved","decided_by":"operator"}'

# 3) Execute with resume + approval binding
curl -sS -X POST "$BASE/action/execute" -H 'content-type: application/json' -d "{
  \"proposal\": {
    \"action\": \"openshell.draft_policy.approve\",
    \"purpose\": \"approval path\",
    \"role\": \"agent\",
    \"context\": {
      \"steward_resume_proposal_id\": \"$GP\",
      \"approval_request_id\": \"$AR_ID\"
    },
    \"parameters\": { \"sandbox_name\": \"YOUR_SBX\", \"chunk_id\": \"YOUR_CHUNK\" }
  }
}"

# 4) Verify decision record on execute audit shows allow (use audit_id from execute response)
```

Use the same Steward process for all steps (in-memory store; avoid `uvicorn --reload` between steps).

### NemoClaw / OpenClaw: same lifecycle via helpers (proven in unit tests)

**Client:** `NemoClaw/nemoclaw/src/steward/client.ts`

- **`parseGovernanceProposalIdFromAudit(audit)`** — reads `governance_proposal_id` from `GET /audit/{id}` (top-level or `payload.audit`).
- **`stewardCompleteApprovalAndExecute(base, authAuditId, decidedBy?)`** — `stewardGetAudit` → `stewardCreateApprovalRequest` → `stewardPostApprovalDecision("approved")` → **`stewardExecuteWithGovernanceResume`** (still **`POST /action/execute`** with resume context).
- **`stewardCompleteApprovalFromAuthorizeAuditId(authorizeAuditId, decidedBy?)`** — same chain; **proposal replayed from audit** via **`parseActionProposalFromAudit`** (used by TUI).
- **First-class proposal APIs (optional migration):** **`stewardPostGovernanceProposal`**, **`stewardGetGovernanceProposal`** → `POST/GET /proposals`.

**Tests:** `nemoclaw/src/steward/client.test.ts` — parsing + approval chains.

**OpenClaw TUI (operator, explicit):** **`/nemoclaw approval complete <authorize-audit-id>`** — requires **`isAuthorizedSender`**; runs the Steward approval lifecycle above. **`/nemoclaw policy`** is unchanged: wrapper + **fail-closed** on `needs_approval` (no auto-approval).

**User-testable in TUI:** run a governed action that yields `needs_approval`, copy the **authorize** `audit_id` from details/audit output, then **`/nemoclaw approval complete <that-id>`** as an operator.

**Helper-only (no slash):** `stewardPostGovernanceProposal` / `stewardGetGovernanceProposal`; programmatic **`stewardCompleteApprovalAndExecute`** when the caller already has the `ActionProposal` object.

---

## What is fully proven vs wrapper-based

| Area | Fully proven | Still wrapper-based |
|------|----------------|---------------------|
| Steward server | Proposal store, ApprovalRequest, Decision/Execution records, resume execute, curl + pytest | — |
| NemoClaw TUI | **`/nemoclaw approval complete`** (operator) + Vitest in **`slash.test.ts`** | **`/nemoclaw policy`** / **`request`** still `/action/*` first |
| NemoClaw client | Approval-from-audit id + **`parseActionProposalFromAudit`** | Proposal CRUD helpers without slash |
| Registry | **`registry_catalog.py`**: **`ROLES`**, **`POLICIES`**, **`CAPABILITIES`**, **`TOOLS`** seeds; **`GET /roles|policies|capabilities|tools/{id}`** | **`capability_registry.py`** holds merge helpers + re-exports **`CAPABILITIES`/`TOOLS`**; no persisted registry or admin APIs |

---

## Registry-backed definitions — next implementation step (started)

**In catalog now (`registry_catalog.py`):**

- **`ROLES`** — `RoleDefinition` rows (+ **`version`**); **`GET /roles/{role_id}`**.
- **`POLICIES`** — `PolicyDefinition` rows; **`GET /policies/{policy_id}`**.
- **`CAPABILITIES`** / **`TOOLS`** — `CapabilityDefinition` (+ **`version`**) / `ToolDefinition`; **`GET /capabilities/{id}`**, **`GET /tools/{id}`**; **`capability_registry.py`** imports these for **`capability_and_tool_for_action`** and re-exports the dicts.

**Tests:** `tests/test_registry_policy_definition.py` (policies, roles, capabilities).

**Recommended follow-up (not implemented):**

1. **`InMemoryRegistryStore`** (or per-entity stores) with `PUT`/`GET`/`list` for policies, roles, capabilities, tools; pin **`policy_version`** / **`role_definition_id`** on decisions.
2. ~~Move **`CAPABILITIES` / `TOOLS`** into **`registry_catalog.py`**~~ **Done** (merge helpers remain in **`capability_registry.py`**).
3. **`EffectivePolicy`** resolution reads **`policy_id`** / **`role_id`** from proposal context and loads registry rows + constitution merge.

---

## Final summary

**Completed phases (1–10, prototype depth):**

| Phase | Title                         | Status |
|------:|-------------------------------|--------|
| 1     | Proposal lifecycle foundation | Done   |
| 2     | DecisionRecord / ExecutionRecord | Done |
| 3     | ApprovalRequest               | Done   |
| 4     | EffectivePolicy resolution    | Done (merge + autonomy ceiling + API) |
| 5     | Capability-aware decisioning  | Done (capability/tool ids + risk merge from capability defaults) |
| 6     | CandidateActionSet            | Done (persist + GET; `/action/evaluate` shared impl) |
| 7     | Role / procedure / skill      | Partial (skill profile + governance outcome hints in context; RoleDefinition registry only) |
| 8     | Identity hardening            | Partial (`steward_identity_trusted=false` deny path; no full identity service) |
| 9     | Registry foundation         | Partial (**`registry_catalog`**: roles + policies; caps/tools in **`capability_registry`**) |
| 10    | NemoClaw integration          | Done (TUI **`approval complete`** + client helpers + Vitest) |

**Remaining gaps**

- ProcedureDefinition and formal procedure evaluation are not implemented.
- SkillProfile is context-string driven only (`steward_skill_profile`); no persisted SkillProfile objects.
- Identity is a single trust flag; no acting-for, attested roles, or issuer validation.
- Candidate-set storage does not yet link per-candidate governance proposals/decision records (Phase 6 stretch).
- EffectivePolicy does not yet model constitution/role/local as separate persisted documents.
- `/action/evaluate` still does not attach Steward v2 proposal rows per candidate (noted for future).
- Auto-approval on `needs_approval` for **`/nemoclaw policy`** is intentionally not default; operators use **`/nemoclaw approval complete`** or helpers.

**Recommended next migration steps**

1. **NemoClaw (optional):** Slash subcommand to **`POST /proposals`** with evaluate, or surface **`governance_proposal_id`** inline on `needs_approval` for easier copy/paste into **`approval complete`**.
2. **NemoClaw:** Wire **`stewardPostGovernanceProposal`** / **`stewardGetGovernanceProposal`** into a dedicated slash or CLI subcommand.
3. **Steward:** Implement persisted registry store + version pins on decisions (see “Registry-backed definitions” above).
4. Extend CandidateActionSet with per-candidate governance proposal links when evaluate is upgraded.
5. Replace `steward_identity_trusted` with a small identity token or service abstraction.

---

## Phase 1 — Proposal lifecycle foundation

**Summary:** `GovernanceProposalRecord` with full lifecycle; in-memory store; `POST/GET /proposals`; `/action/authorize|simulate|execute` create/link proposals.

**Files changed:** `domain.py`, `proposal_store.py`, `proposal_service.py`, `main.py`, `audit_store.py`, `tests/test_proposal_phase1.py`

**Tests:** `tests/test_proposal_phase1.py`

**Manual verify:**

```bash
cd Steward && uvicorn steward_service.main:app --reload --port 8000
curl -s -X POST localhost:8000/proposals -H 'content-type: application/json' -d '{"proposal":{"action":"openshell.draft_policy.get","purpose":"t","role":"operator","parameters":{"sandbox_name":"s"}},"evaluate":true}'
```

**Assumptions:** In-memory stores only; ids are UUIDs.

---

## Phase 2 — DecisionRecord and ExecutionRecord

**Summary:** Separate stores and `GET /decision-records/{id}`, `GET /execution-records/{id}`; audit payload carries both ids; execute always writes an execution record (governance deny vs runtime failure distinguishable).

**Files changed:** `domain.py`, `decision_store.py`, `execution_store.py`, `main.py`, `audit_store.py`, `tests/test_proposal_phase2.py`

**Tests:** `tests/test_proposal_phase2.py`

**Manual verify:** Execute an unknown action; open audit and fetch decision + execution records by id from JSON.

---

## Phase 3 — ApprovalRequest

**Summary:** `ApprovalRequestRecord` with states including `expired`; `POST/GET /approval-requests`, `POST .../decision`; execute uses `steward_resume_proposal_id` + `approval_request_id` to reuse a proposal and bypass `needs_approval` when the request is approved; `proposal_id` hash excludes those context keys.

**Files changed:** `domain.py`, `approval_store.py`, `proposal_service.py`, `main.py`, `tests/test_proposal_phase3.py`

**Tests:** `tests/test_proposal_phase3.py`

**Manual verify:**

```bash
# After authorize returns needs_approval, read audit for governance_proposal_id, then:
curl -s -X POST localhost:8000/approval-requests -H 'content-type: application/json' -d '{"governance_proposal_id":"<gp>"}'
curl -s -X POST localhost:8000/approval-requests/<ar>/decision -H 'content-type: application/json' -d '{"decision":"approved","decided_by":"op"}'
# Execute with same action/purpose/parameters/role and context:
# {"steward_resume_proposal_id":"<gp>","approval_request_id":"<ar>"}
```

**Assumptions:** Rejected approval marks proposal `denied`; expired requests are created with `expires_at` in the past.

---

## Phase 4 — EffectivePolicy

**Summary:** `effective_policy.py` merges constitution default with role and `steward_local_policy.autonomy_ceiling` (local cannot widen past constitution). `risk_exceeds_autonomy_ceiling` drives mandatory approval for tier vs ceiling. `POST /effective-policy/resolve`, `GET /effective-policy`.

**Files changed:** `effective_policy.py`, `governance.py`, `main.py`, `tests/test_effective_policy_phase4.py`

**Tests:** `tests/test_effective_policy_phase4.py`

**Manual verify:** `curl -s -X POST localhost:8000/effective-policy/resolve -d '{"role":"agent","context":{"steward_local_policy":{"autonomy_ceiling":"low"}}}' -H 'content-type: application/json'`

---

## Phase 5 — Capability-aware decisioning

**Summary:** `capability_registry.py` maps actions to `capability_id` / `tool_id`; `ExecutionPlan` carries both; merged risk = max(action table, capability default). Registry `GET /capabilities/{id}` (capability rows live in **`registry_catalog.py`** as of operator milestone Phase 7).

**Files changed:** `capability_registry.py`, `registry_catalog.py`, `domain.py`, `governance.py`, `main.py`, `tests/test_steward_v2_phases_5_9.py`

**Tests:** `test_steward_v2_phases_5_9.py::TestPhase5CapabilityMetadata`

---

## Phase 6 — CandidateActionSet

**Summary:** `CandidateActionSetRecord` + `InMemoryCandidateSetStore`; `POST /candidate-sets/evaluate` (shared evaluator with `/action/evaluate`); `GET /candidate-sets/{id}`.

**Files changed:** `domain.py`, `candidate_set_store.py`, `main.py`, `tests/test_steward_v2_phases_5_9.py`

**Tests:** `TestPhase6CandidateSets`

---

## Phase 7 — Role, procedure, skill (partial)

**Summary:** Context hooks: `steward_skill_profile=review_required` adds operator approval; `steward_governance_outcome_hint` supports `escalate`, `defer`, `simulate_only`, `recommend` (recommend on mutation path). Role definitions exposed via `GET /roles/{id}`.

**Files changed:** `governance.py`, `capability_registry.py`, `main.py`, `tests/test_steward_v2_phases_5_9.py`

**Tests:** `TestPhase7SkillAndOutcomes`

---

## Phase 8 — Identity (partial)

**Summary:** Explicit `steward_identity_trusted: false` in proposal context denies supported draft-policy actions after sandbox validation.

**Files changed:** `governance.py`, `tests/test_steward_v2_phases_5_9.py`

**Tests:** `TestPhase8IdentityTrust`

---

## Phase 9 — Registry (partial)

**Summary:** Static in-code maps for capabilities, tools, roles, policies; lookup APIs; `GET /effective-policy` convenience. Seeds in **`registry_catalog.py`** (`ROLES`, `POLICIES`, `CAPABILITIES`, `TOOLS`); **`capability_registry.py`** provides action→cap/tool mapping and re-exports catalog dicts for imports.

**Files changed:** `capability_registry.py`, `registry_catalog.py`, `domain.py`, `main.py`, `tests/test_steward_v2_phases_5_9.py`, `tests/test_registry_policy_definition.py`

**Tests:** `TestPhase9Registry`, `test_registry_policy_definition.py`

---

## Phase 10 — NemoClaw integration

**Summary:** `nemoclaw/src/steward/client.ts` + `nemoclaw/src/commands/slash.ts`

- Compatibility: `stewardAuthorize`, `stewardExecute`, `stewardEvaluateCandidates`.
- Approval: `stewardGetAudit`, `parseGovernanceProposalIdFromAudit`, `parseActionProposalFromAudit`, `stewardCreateApprovalRequest`, `stewardPostApprovalDecision`, `stewardExecuteWithGovernanceResume`.
- **Orchestrators:** `stewardCompleteApprovalAndExecute(base, authAuditId, decidedBy?)`, **`stewardCompleteApprovalFromAuthorizeAuditId(authorizeAuditId, decidedBy?)`** (audit → replay proposal).
- **TUI:** **`/nemoclaw approval complete <authorize-audit-id>`** (operator-only); **`/nemoclaw records audit|decision|execution <id>`** (operator-only).
- **First-class proposals (helper):** `stewardPostGovernanceProposal`, `stewardGetGovernanceProposal`.
- **Approval outcome type:** `StewardApprovalCompleteResponse` includes **`governance_proposal_id`**, **`approval_request_id`**, **`resumed_*`** for TUI copy.

**Files changed:** `nemoclaw/src/steward/client.ts`, `nemoclaw/src/steward/client.test.ts`, `nemoclaw/src/commands/slash.ts`, `nemoclaw/src/commands/slash.test.ts`, `nemoclaw/src/commands/policy-render.ts`, `nemoclaw/src/commands/records-render.ts`

**Tests:** `npx vitest run nemoclaw/src/steward/client.test.ts nemoclaw/src/commands/slash.test.ts`

**Manual verify (chat):** after `needs_approval`, use **`/nemoclaw approval complete <audit_id>`** as an authorized operator (same Steward process / `STEWARD_URL`).

No OpenShell changes; Steward URL via `STEWARD_URL` unchanged.

---

## Milestone: Full approval-aware governed workflow in OpenClaw

**What is user-testable in TUI**

1. `/nemoclaw policy approve-all <sandbox>` (or other mutates) when Steward returns **`needs_approval`** → **Approval required** with sandbox, rationale, **authorize audit id**, exact **`/nemoclaw approval complete <id>`**, and pointer to **`/nemoclaw records`**.
2. `/nemoclaw approval complete <authorize-audit-id>` as an authorized operator → Steward **GET /audit** → **POST /approval-requests** → **POST …/decision** (approved) → **POST /action/execute** with **`steward_resume_proposal_id`** + **`approval_request_id`** (same replayed proposal). Output summarizes **what was requested**, **what was approved**, **what executed**, success vs **governance allowed after approval but runtime failed**.
3. `/nemoclaw records audit <id>`, **`records decision <id>`**, **`records execution <id>`** → readable summaries; audit includes **`operator_hints`** when Steward provides them.

**Still wrapper-based:** `/nemoclaw policy` and `/nemoclaw request` still use **`/action/authorize`**, **`/action/execute`**, **`/action/evaluate`** first; no requirement to use **`POST /proposals`** for this milestone.

**Registry-backed:** **`registry_catalog.py`** is the seed catalog for **`ROLES`**, **`POLICIES`**, **`CAPABILITIES`**, **`TOOLS`**. **`GET /roles/{id}`**, **`GET /policies/{id}`**, **`GET /capabilities/{id}`**, **`GET /tools/{id}`**. Role and capability JSON include **`version`** (`"1"`). **`capability_registry.py`** keeps **`capability_and_tool_for_action`** and risk merge; re-exports **`CAPABILITIES`** / **`TOOLS`** for compatibility.

**Steward ergonomics for the loop:** **`GET /audit/{id}`** returns **`operator_hints`** (e.g. **`nemoclaw_approval_complete`**, **`governance_proposal_id`**, linked record ids). When execute fails after governance **allow**, HTTP **403** **`detail`** includes **`audit_id`**, **`decision_record_id`**, **`execution_record_id`**, **`user_hint`**.

**Gaps before next milestone:** No persisted registry store; **`/nemoclaw request`** **`needs_approval`** path does not yet duplicate the full “copy/paste approval complete” block (evaluate audits are separate from policy authorize audits); **`ToolDefinition`** has no version field; no raw-json mode on **`records`**.

**Manual verification**

1. `cd Steward && uvicorn steward_service.main:app --reload --port 8000`
2. Point OpenClaw/NemoClaw at Steward (`STEWARD_URL` if not default).
3. **Agent:** `/nemoclaw policy approve_all <sandbox>` → expect **Approval required**, backticked **authorize audit** id, line **`/nemoclaw approval complete <id>`**.
4. **Operator:** `/nemoclaw approval complete <id>` → expect **Approval completed and execution finished** (or **runtime** failure section with **execute audit** and **records** hints if OpenShell fails).
5. **Operator:** `/nemoclaw records audit <authorize-or-execute-audit-id>` → linked ids and hints.

**Expected outputs (shape):** Policy **`needs_approval`** includes **Operator handle** and **Next step (operator):** **`/nemoclaw approval complete …`**. Approval complete includes **Governance** (proposal id, approval request id) and **Execution** (execute audit, runtime line). Runtime failure after approval: title **Approval completed; execution failed (runtime)** and **Governance allowed**.

**Recommended next milestone:** Persisted registry + admin APIs; align **`/nemoclaw request`** **`needs_approval`** UX with policy (surface evaluate **audit_id** + **`nemoclaw approval complete`** or document evaluate-specific flow); optional **`ToolDefinition.version`**.

---

### Operator milestone — Phase 1 (reference)

Explicit **`/nemoclaw approval complete`** + client chain (already covered in “Phase 10 — NemoClaw integration” and “Milestone: Full approval happy path” above).

### Operator milestone — Phase 2: TUI lifecycle output

| | |
|--|--|
| **Files changed** | `NemoClaw/nemoclaw/src/commands/policy-render.ts`, `nemoclaw/src/commands/slash.ts` |
| **Behavior** | Policy **`needs_approval`**: status, sandbox, rationale, operator handle, exact **`nemoclaw approval complete`**; policy **get** short path includes handle when approval needed; approval complete success: structured governance + execution; **403** with governance **allow** → runtime-failure wording. |
| **Tests** | `nemoclaw/src/commands/slash.test.ts` (updated + integration-style cases) |
| **Manual** | Agent policy mutate → operator **`approval complete`**. |
| **Assumptions / gaps** | Request/candidate **`needs_approval`** messaging unchanged in this pass. |

### Operator milestone — Phase 3: Record inspection

| | |
|--|--|
| **Files changed** | `nemoclaw/src/steward/client.ts`, `nemoclaw/src/commands/records-render.ts`, `nemoclaw/src/commands/slash.ts`, `slash.test.ts` |
| **Behavior** | **`/nemoclaw records audit|decision|execution <id>`** (operator); GET **`/audit`**, **`/decision-records`**, **`/execution-records`**. |
| **Tests** | `slash.test.ts` **`describe("records")`** |
| **Manual** | After a run, **`/nemoclaw records audit <execute-audit-id>`**. |
| **Gaps** | No **`--json`** on records. |

### Operator milestone — Phase 4: NemoClaw integration tests

| | |
|--|--|
| **Files changed** | `nemoclaw/src/commands/slash.test.ts` |
| **Behavior** | Mocked full path: policy **`needs_approval`** then **`approval complete`**; asserts execute body **`steward_resume_proposal_id`** / **`approval_request_id`**; mocked **403** after approval → operator copy. |
| **Tests** | Same file (**`integration:`** cases) |
| **Manual** | `npx vitest run nemoclaw/src/commands/slash.test.ts` |

### Operator milestone — Phase 5: Steward compatibility

| | |
|--|--|
| **Files changed** | `Steward/steward_service/main.py`, `Steward/tests/test_approval_happy_path.py` |
| **Behavior** | **`AuditRecord.operator_hints`**; execute failure **403** **`detail.decision_record_id`** / **`execution_record_id`**. **Correctness:** when execute resumes with an approved `ApprovalRequest`, the execute-side plan/audit/DecisionRecord rationale reflects the effective **allow after approval** (not the authorize-time `needs_approval` rationale). |
| **Tests** | `test_approval_happy_path.py` (hints on authorize audit) |
| **Manual** | **`GET /audit/{id}`** after authorize **`needs_approval`**. |
| **Manual (rationale)** | Run `needs_approval` authorize, approve the request, execute with resume. Verify: `GET /audit/<authorize>` has rationale about unmet requirements; `GET /audit/<execute>` and `GET /decision-records/<execute decision_record_id>` have rationale starting with **“Approved via approval request …”**. |

### Operator milestone — Phase 6: RoleDefinition registry

| | |
|--|--|
| **Files changed** | `Steward/steward_service/domain.py`, `registry_catalog.py`, `main.py`, `tests/test_registry_policy_definition.py` |
| **Behavior** | **`RoleDefinition.version`**; **`GET /roles/{id}`** returns **`version`**. |
| **Tests** | **`TestRoleDefinitionRegistryCatalog.test_get_operator_from_registry_catalog`** |
| **Manual** | **`curl -s localhost:8000/roles/operator`** |

### Operator milestone — Phase 7: CapabilityDefinition registry

| | |
|--|--|
| **Files changed** | `registry_catalog.py`, `capability_registry.py`, `domain.py`, `main.py`, `tests/test_registry_policy_definition.py` |
| **Behavior** | **`CAPABILITIES`** / **`TOOLS`** defined in catalog; **`CapabilityDefinition.version`**; **`GET /capabilities/{id}`** returns **`version`**. |
| **Tests** | **`TestCapabilityDefinitionRegistryCatalog`** |
| **Manual** | **`curl -s localhost:8000/capabilities/cap.openshell.draft_policy.read`** |

### Operator milestone — Phase 8: Checkpoint

Documented in **“Milestone: Full approval-aware governed workflow in OpenClaw”** above.

---

## Next milestone: approval-aware candidate-action lifecycle for `/nemoclaw request`

**Goal:** When `/nemoclaw request ...` selects a candidate with `needs_approval`, NemoClaw surfaces an operator-ready handle (**authorize audit id**) and the exact next step (**`/nemoclaw approval complete <id>`**), reusing the same approval/resume model as explicit policy commands.

**Files changed:** `NemoClaw/nemoclaw/src/commands/slash.ts`, `NemoClaw/nemoclaw/src/commands/slash.test.ts`

**Behavior changed:**
- If the selected candidate decision is `needs_approval`, output now includes:
  - the original request
  - selected candidate + selection rationale
  - governance note
  - **Operator handle (authorize audit)** and the exact next step:
    - **`/nemoclaw approval complete <audit-id>`**
- Approval completion replays the selected candidate proposal by reading `GET /audit/{id}` and executing with `steward_resume_proposal_id` + `approval_request_id`.

**Tests updated:**
- `slash.test.ts`: request `needs_approval` output includes audit handle + next-step command.
- `slash.test.ts`: integration-style flow: request → needs_approval → approval complete replays selected proposal.

**Manual verification (TUI):**
1. `/nemoclaw request <sandbox> <natural language request>`
2. If `needs_approval`, copy the **Operator handle (authorize audit)**.
3. `/nemoclaw approval complete <that-audit-id>` as operator.
4. Verify approval output shows the resumed action matches the selected candidate.

**Remaining gaps:**
- `/nemoclaw request` does not yet automatically “retry” post-approval; operator re-runs request if needed.

# Steward — Deep architecture and implementation review

**Scope:** `steward/` repository only. `PROGRESS.md` used as the intended framework narrative. OpenShell runtime is out of scope (client interface reviewed only). NemoClaw integration is **not** verified from code here; only Steward-side hints (`operator_hints`, HTTP contracts) are assessed.

**Test run:** `pytest tests/` — **62 passed** (includes SQLite durability + institution engine; run locally to confirm).

---

## Remediation (changelog)

The following items from the original review were **fixed** in code and docs:

| Issue | Change |
|-------|--------|
| Stale `ApprovalRequestRecord.decision_record_id` after approved execute | `main.py` `execute`: when `used_approval`, after `_persist_decision` for the allow snapshot, update the `ApprovalRequestRecord` keyed by `approval_request_id` to set `decision_record_id` to the new id. Covered in `tests/test_approval_happy_path.py`. |
| `/action/simulate` persisted GP + DR | **Contract:** simulate is **ephemeral** for governance artifacts — `build_execution_plan` only; **no** `evaluate_content`, **no** `_persist_decision`, **no** `_link_proposal_audit`. Still writes one **audit** row. Documented in `README.md`, `PROGRESS.md` §0, handler docstring. Tests: `tests/test_action_simulate_contract.py`. |
| `approve_all` / `clear` auto-allowed for operator | **Enforced:** unconditional `ApprovalRequirement` in `governance.py` for `DRAFT_APPROVE_ALL` and `DRAFT_CLEAR` → always `needs_approval`. Tests: `tests/test_governance_bulk_approval_required.py`. |
| Missing `senior_engineer` institutional rule | **Now in JSON** `data/institution_expenditure_rules.json` (plus `registry_catalog.ROLES` metadata); evaluated by `institution_engine.py`. Tests: `tests/test_institution_expenditure.py`, `test_institution_engine.py`. |
| `PROGRESS.md` vs code drift | `PROGRESS.md` **§0** updated for durable storage + declarative institution. |
| **`/action/evaluate` audits not approval-capable** | **Fixed:** each candidate uses **`evaluate_content`** + **`_persist_decision`** + audit linkage (same as authorize). |
| **Durable governance** | **`storage/`** protocols, **`SqliteConnection`** + table stores, **`build_storage_bundle()`** (`STEWARD_STORAGE_BACKEND`, `STEWARD_SQLITE_PATH`). **`tests/test_sqlite_storage_durability.py`** — approval/proposal/decision survive `importlib.reload`. |
| **Declarative institution** | **`institution_expenditure_rules.json`** is source of truth; **`GET /policies/institution.expenditure.v1`** registered at startup. |

**Still open:** default **memory** in dev; **SQLite** single-writer limits; new GP per `/action/*` (and per evaluate candidate); **`build_execution_plan`** still not reading capability/tool registry rows; no HTTP auth; institutional `decision_record_id` naming; unused approval states; **Postgres/HA** not implemented.

---

## Executive summary

Steward **does implement** a coherent governance plane between HTTP clients (agents / NemoClaw / curl) and OpenShell: **deny-by-default** action policies, **`ExecutionPlan`** with separated **`AuthorizationDecision`** vs **`ApprovalState`**, **governance `DecisionRecord`** vs **`ExecutionRecord`**, **approval gating** with **`ApprovalRequestRecord`**, **resume execute**, **candidate evaluation** with proposal-backed audits, **EffectivePolicy** merge, **institutional expenditure** from **declarative JSON** + dedicated store/API, **`/action/simulate`** ephemeral preview, **bulk draft-policy actions always `needs_approval`**, **optional SQLite durability** for all governance artifacts, and **registry GET** APIs (draft-policy metadata still **code-driven** except **`institution.expenditure.v1`** policy record from JSON).

Remaining gaps: **draft-policy** behavior not loaded from registry files; **GP deduplication**; **multi-worker / Postgres**; HTTP auth.

---

## What is definitely implemented

| Area | Evidence |
|------|----------|
| **FastAPI app + versioning** | `steward_service/main.py` — `FastAPI(title="Steward", version="0.0.1")` |
| **`/action/authorize`, `/action/simulate`, `/action/execute`** | `main.py` handlers; simulate returns `simulation` from audit payload plan **without** persisting GP/DR |
| **`/audit/{id}`** | `get_audit` — public audit shape with `operator_hints` for `needs_approval` |
| **Governance proposal record + lifecycle enum** | `domain.py` `GovernanceProposalRecord`, `ProposalLifecycleState`; `proposal_service.py` transitions |
| **`POST /proposals`, `GET /proposals/{id}`** | `main.py` — draft/submit/evaluate flags |
| **`DecisionRecord` vs `ExecutionRecord`** | `domain.py`; `main.py` `_persist_decision`, `_persist_execution`; `GET /decision-records/{id}`, `GET /execution-records/{id}` |
| **`ApprovalRequest` CRUD + decision** | `POST /approval-requests`, `GET /approval-requests/{id}`, `POST /.../decision`; `approval_store.py`, `domain.py` `ApprovalRequestState` |
| **Resume execute + approval binding** | `main.py` `_maybe_resume_proposal`, `_effective_plan_for_execute`; `_resolve_governance_proposal_for_approval` accepts storage id, decision record id, or content hash |
| **OpenShell draft-policy action set** | `governance.py` `StewardActions`, `build_execution_plan`, `execute_plan`; gRPC + `MockOpenShellClient` in `openshell_client.py` |
| **Deny-by-default unknown actions** | `governance.py` — actions not in allowlist → `Decision.deny` |
| **EffectivePolicy** | `effective_policy.py` — `POST /effective-policy/resolve`, `GET /effective-policy` |
| **Candidate evaluation** | `main.py` `_evaluate_candidates_impl`; `POST /action/evaluate` — **per-candidate** `GovernanceProposalRecord` + `DecisionRecord` + audit linkage (approval targets match authorize semantics) |
| **Candidate set persistence** | `POST /candidate-sets/evaluate`, `GET /candidate-sets/{set_id}`; `candidate_set_store.py`, `CandidateActionSetRecord` |
| **Institutional expenditure slice** | `data/institution_expenditure_rules.json`, `institution_engine.py`, `POST /institution/authorize`, `GET /institution/decision-records/{id}`; store via `StorageBundle.institution` |
| **Registry read APIs** | `GET /roles|capabilities|tools/{id}` — `registry_catalog.py` (metadata). **`GET /policies/institution.expenditure.v1`** — version/display from JSON via `register_expenditure_policy_metadata`. |
| **Durable storage (optional)** | `storage/factory.py`, `storage/sqlite_backend.py`, `storage/serialize.py`; env `STEWARD_STORAGE_BACKEND=sqlite`, `STEWARD_SQLITE_PATH` |
| **Governance context + identity parsing** | `governance_context.py`, `identity.py`; audit payload `requested_by` / `approved_by` |
| **Skill / trust / outcome hints (technical)** | `governance.py` — `steward_skill_profile`, `steward_identity_trusted`, `steward_governance_outcome_hint` |
| **Execute failure UX** | `main.py` `_execute_user_hint`; HTTP 403 `detail` with `user_hint` on failure paths |

---

## What is partially implemented

| Area | What exists | What is missing / weak |
|------|-------------|-------------------------|
| **Proposal lifecycle** | Full enum in `domain.py`; transitions in `proposal_service.py`; execute path updates state | **`/action/*` bypasses long-lived draft**: `evaluate_content` always creates a **new** `GovernanceProposalRecord` per call. No “single proposal per content” invariant. |
| **Approval workflow** | Create request, approve/reject, execute with `approval_request_id`; **AR `decision_record_id` updated** to post-approval allow DR | **GP state** stays `approval_pending` until execute calls `mark_proposal_approved_after_external_ok`. |
| **EffectivePolicy “registry”** | Merge logic + API | **Not loaded from** `registry_catalog.ROLES` / `POLICIES`. **Constitution is hard-coded** `DEFAULT_CONSTITUTION` in `effective_policy.py`. Role ceiling is **`_role_policy`** (operator → high, else medium), not catalog entries. |
| **Registry-backed governance** | `registry_catalog.py` + GET handlers | **Draft-policy:** definitions are **metadata**; **`governance.py` does not consult** those rows. **Exception:** **`institution.expenditure.v1`** rules are **authoritative JSON** driving `institution_engine` (not `governance.py`). |
| **Institutional governance** | Expenditure rules **JSON-driven**; single domain `institution.expenditure.v1` | **No** other institutional domains; facts not fetched from external services. |
| **Procedure / skill (framework)** | Context keys influence **technical** plans | **No institutional procedure engine**; institution path only checks `procedure` / `procedure_state` strings present. |
| **Identity hardening** | `steward_identity_trusted`, structured `requested_by` | **Role on proposal is caller-supplied**; no entitlement service, no JWT validation in Steward. |
| **ApprovalRequestState** | Enum includes `under_review`, `revoked` | **Only** `requested`, `approved`, `rejected`, `expired` used in `main.py` |

---

## What appears missing or regressed (vs aspirational framework)

1. **Registry-backed draft-policy rules** — `governance.py` allowlist/risk still **code**; only **institution expenditure** is JSON-backed today.

2. **Stable single proposal for repeated `/action/authorize`** — Not implemented; each call creates new storage row (see Architectural weaknesses).

3. **Persistent audit / proposals / approvals** — **All stores are `InMemory*`** (`main.py` module globals).

4. **`GET /effective-policy` query variant** — Exists but **ignores** richer context (only `role` query param); `POST /effective-policy/resolve` accepts full context.

---

## Architectural strengths

- **Clear seam:** HTTP → `build_execution_plan` → `execute_plan` (OpenShell). Runtime failures mapped to structured `result` (`external_call_failed`, etc.).
- **Domain model expressiveness:** `ExecutionPlan` carries both external `decision` and internal `authorization_decision` / `approval_state` (`domain.py`).
- **Compatibility + v2 APIs coexist:** `/action/*` for legacy/simple clients; `/proposals`, `/approval-requests`, `/decision-records`, `/execution-records` for structured inspection.
- **Resolution helpers:** `_resolve_governance_proposal_for_approval` and execute resume accept **storage id, decision record id, or content hash** — pragmatic for operator error (`main.py`).
- **Institutional vs technical separation:** Separate outcome enum and store avoids overloading `allow|deny|needs_approval` for `escalate|defer` (`InstitutionAuthorizeResponse` vs `AuthorizeResponse`).
- **Tests align with critical paths:** approval happy path, candidate selection, effective policy ceiling, mock OpenShell gRPC path.

---

## Architectural weaknesses / risks

1. **New governance proposal per `/action/*` call** — `proposal_service.evaluate_content` always `create_draft` → `submit` → `apply_evaluation`. Repeated authorizations for the same logical intent produce **many** `GovernanceProposalRecord` rows with the same **content** `proposal_id` (`proposal_store.find_by_content_proposal_id` used only for approval resolution heuristics).

2. **Decision record proliferation** — Every `authorize` and `execute` (non-resume) calls `_persist_decision`. **`/action/simulate` does not** (remediated).

3. **Naming collision:** `InstitutionAuthorizeResponse.decision_record_id` is an **institutional** record id, not `GET /decision-records/{id}`. Easy to misuse in clients.

4. **Policy duplication:** Action allowlist and risk live in `governance.py`; capability/tool mapping in `capability_registry.py` + `registry_catalog.py`; effective policy in `effective_policy.py`. **No single source of truth.**

5. **Thread safety:** In-memory stores use `Lock` per store, but **cross-store updates** (e.g. proposal + decision + audit) are **not atomic** as a unit.

6. **Production readiness:** No authn/z on HTTP API, no rate limits, no durable storage — expected for scaffold but blocks “enterprise” claims without work.

---

## API surface review

**Implemented routes** (from `steward_service/main.py`):

| Method | Path | Notes |
|--------|------|--------|
| POST | `/proposals` | Create draft; optional submit/evaluate; may persist decision when `evaluate=True` |
| GET | `/proposals/{proposal_id}` | Storage id |
| POST | `/action/authorize` | Creates GP + decision + audit |
| POST | `/action/simulate` | **Ephemeral:** no GP/DR; audit only; same plan shape as authorize |
| POST | `/action/execute` | Full chain; 403 with structured `detail` on failure |
| POST | `/action/evaluate` | Candidate bulk evaluate; **does not** persist candidate set |
| GET | `/audit/{id}` | |
| POST | `/approval-requests` | Body `governance_proposal_id` (flexible resolver) |
| GET | `/approval-requests/{ar_id}` | |
| POST | `/approval-requests/{ar_id}/decision` | `approved` / `rejected` |
| GET | `/decision-records/{record_id}` | Governance decision snapshot |
| GET | `/execution-records/{record_id}` | Runtime outcome |
| POST | `/effective-policy/resolve` | |
| GET | `/effective-policy` | Query: `role` only |
| POST | `/candidate-sets/evaluate` | Same logic as `/action/evaluate` + persists `CandidateActionSetRecord` |
| GET | `/candidate-sets/{set_id}` | |
| GET | `/capabilities/{cap_id}` | Seed catalog |
| GET | `/tools/{tool_id}` | Seed catalog |
| GET | `/roles/{role_id}` | Seed catalog; lookup **lower-cased** |
| GET | `/policies/{policy_id}` | Seed catalog |
| POST | `/institution/authorize` | Institutional outcomes |
| GET | `/institution/decision-records/{record_id}` | JSON dict (not shared response model with governance DR) |

**Not present:**

- No `GET /proposals` list.
- No `PATCH` / state transition APIs for proposals beyond implicit flows.
- No `DELETE` or revocation APIs for approvals (enum has `revoked` unused).

---

## Data model and persistence review

**First-class models** (`steward_service/domain.py`): `Proposal`, `ExecutionPlan`, `ExecutionStep`, `AuditRecord`, `GovernanceProposalRecord`, `DecisionRecord`, `ExecutionRecord`, `ApprovalRequestRecord`, `CandidateActionSetRecord`, capability/tool/role/policy **definition** dataclasses, `InstitutionalDecisionRecord`.

**Stores:** Selected at process start via `build_storage_bundle()` (`main.py`).

| Logical store | In-memory impl | SQLite impl |
|---------------|----------------|-------------|
| audit | `audit_store.py` | `SqliteAuditStore` |
| proposals | `proposal_store.py` | `SqliteProposalStore` (+ `content_proposal_id` index) |
| decisions | `decision_store.py` | `SqliteDecisionStore` |
| executions | `execution_store.py` | `SqliteExecutionStore` |
| approvals | `approval_store.py` | `SqliteApprovalStore` |
| candidate_sets | `candidate_set_store.py` | `SqliteCandidateSetStore` |
| institution | `institution_store.py` | `SqliteInstitutionStore` |

**Restart:** With **memory**, all state is lost. With **sqlite** + same `STEWARD_SQLITE_PATH`, state survives process restart (see durability test).

**ID coherence:**

- `audit_id` — per request UUID.
- `governance_proposal_id` — storage UUID; linked from audit and decision/execution records.
- `content_proposal_id` — SHA-256 over canonical proposal content (`main.py` `_stable_proposal_id`); excludes `steward_resume_proposal_id` and `approval_request_id` from context.
- **Execute after approval** — new `DecisionRecord` id for the allow snapshot; **execution record** references the new id; **`ApprovalRequestRecord.decision_record_id` updated** to match (remediated).

---

## Correctness review (specific issues)

1. **Institutional `decision_record_id` naming** — Same field name as governance decision records but different resource family and GET path (`/institution/decision-records/...`).

2. **Candidate evaluation** — Does **not** create/update `GovernanceProposalRecord` per candidate; only audit records + selection logic. **Selection** uses hard-coded goal heuristics (`npm`, `git clone`) in `main.py` — **brittle** but tested.

3. **Registry driving behavior** — **False** for core paths; risk/action allowlist in `governance.py` + `effective_policy.py` only.

---

## Framework alignment (`PROGRESS.md`)

| Framework concept | Alignment |
|-------------------|-----------|
| Layered stack (agent → Steward → OpenShell) | **Strong** in code structure |
| Proposal lifecycle | **Partial** — enum complete; `/action/*` pattern creates duplicate GPs |
| Approval workflow | **Strong** — happy path + **AR `decision_record_id`** aligned to post-approval DR |
| Decision vs execution separation | **Strong** — models and tests (`test_approval_happy_path.py`) |
| EffectivePolicy | **Medium** — merge real; not connected to published registry |
| CandidateActionSet | **Strong** for evaluate + persist; selection rules ad hoc |
| Institutional governance | **Expenditure** — declarative JSON + engine; other domains **not** implemented |
| Facts / procedure / skill as institutional truth | **Mostly conceptual** except minimal defer checks |
| Identity / entitlements | **Minimal** — trust flags and string role |
| Fleet / constitutional distribution | **Not in repo** |

---

## Test coverage review

**Present:** 62 tests under `tests/` covering:

- Proposal phase 1–3 (`test_proposal_phase*.py`)
- Effective policy (`test_effective_policy_phase4.py`)
- Phases 5–9 registry/candidate/skill/trust (`test_steward_v2_phases_5_9.py`)
- Approval happy path + resume variants + **AR decision id** (`test_approval_happy_path.py`)
- **`/action/simulate` contract** (`test_action_simulate_contract.py`)
- **Bulk approve_all/clear** (`test_governance_bulk_approval_required.py`)
- Approve matching (`test_approve_matching.py`, `test_governance_context.py`, etc.)
- Candidate evaluate (`test_candidate_evaluate_endpoint.py`)
- Institution expenditure + JSON engine (`test_institution_expenditure.py`, `test_institution_engine.py`)
- SQLite durability (`test_sqlite_storage_durability.py`)
- Governance unknown actions, execute hints, registry policy GET

**Gaps (high value):**

- **Duplicate `/action/authorize` same content** — behavior of multiple GPs / approval resolution when multiple `approval_pending` exist (`find_by_content_proposal_id` picks max `updated_at`).
- **Concurrent requests** stress (optional).

---

## Comparison against `PROGRESS.md` (honest delta)

| Progress claim (summary) | Code reality |
|-------------------------|--------------|
| Full proposal lifecycle states | States exist; `/action/*` creates new GP each time |
| Registry-backed draft-policy | **Seeded GET** + code in `governance.py` |
| Institution expenditure policy | **JSON SoT** + `GET /policies/institution.expenditure.v1` |
| Expenditure engine with senior + junior rules | **Implemented** in `institution_engine.py` + JSON (see §0 `PROGRESS.md`) |
| High-risk bulk never auto-allowed (Phase 1A story) | **Enforced** in `governance.py` for `approve_all` / `clear` |
| Durable audit / governance memory | **Optional SQLite** (`STEWARD_STORAGE_*`); default memory |
| NemoClaw TUI flows | **Cannot verify** without NemoClaw repo; Steward exposes hints and HTTP |

---

## Recovery plan

### Keep (solid foundation)

- `domain.py` model split (decision vs execution, approval request, institutional record).
- `governance.py` + `openshell_client.py` abstraction.
- `main.py` route inventory and `_resolve_governance_proposal_for_approval` ergonomics.
- Test suite structure and `MockOpenShellClient` usage.

### Verify manually (environment / integration)

- gRPC path with real OpenShell + mTLS env vars (`STEWARD_OPENSHELL_*`).
- NemoClaw plugin against this HTTP API (`stewardUrl`, approval complete hints) — **requires** [NemoClaw](https://github.com/Manishsv/NemoClaw) checkout.

### Redo / fix (recommended before next milestone)

1. **Unify draft-policy policy sources** — Registry file or DB drives `build_execution_plan` (today: code + GET metadata).
2. **Postgres / HA** — If SQLite single-writer is insufficient.
3. **Deduplicate GP for `/action/*`** — Optional `find_or_create` by `content_proposal_id`.
4. **Institution** — Rename institutional response field to `institution_decision_record_id` (breaking) or keep + document (see Naming collision).
5. ~~SQLite scaffold, institution JSON, storage protocols~~ — **Done** (see remediation changelog).

---

## Recommended next milestone

**“Registry-driven draft policy + scale-out storage”**

1. Published definitions (versioned) for `StewardActions` / risk / approval requirements consumed by `governance.py`.
2. **Postgres** (or managed DB) behind the same storage protocols; migration from SQLite.
3. Optional: **single GP** per content hash for `/action/*`.
4. NemoClaw E2E smoke test (external repo).

---

## Recommended implementation order

1. Extract draft-policy allowlist + tiers to versioned JSON/YAML; loader in `governance.py`.
2. Add Postgres store implementations (or SQLAlchemy) behind protocols.
3. NemoClaw E2E smoke test (external repo).

---

## Uncertainty

- **Real OpenShell** error shapes and timeouts may differ from `MockOpenShellClient` — production behavior needs integration tests.
- **NemoClaw** command coverage vs Steward routes — not verified here.

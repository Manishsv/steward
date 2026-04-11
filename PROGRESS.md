Agentic AI Governance Platform

Consolidated Progress and Forward Plan

### 0. Code alignment status (this repository)

This document distinguishes **implemented** (in `steward_service/` today), **partial**, and **planned**. Narrative sections below include historical intent; **section 0 and `DEEP_REVIEW.md` are the contract** for what the code actually does. Last aligned update: **declarative EffectivePolicy merge** (`data/effective_policy_merge.json` + `policy_merge_layer.py`), plus technical draft-policy JSON, SQLite, and institutional expenditure JSON.

#### Implemented

- **OpenShell draft-policy actions**: **authoritative definitions** in `steward_service/data/technical_draft_policy_governance.json` (action → capability_id, tool_id, base_risk_tier, approver_role, mutation/bulk flags, `execute.kind` + rationales). Loaded by `technical_governance.py`; **`build_execution_plan`** in `governance.py` uses that registry as the main source of truth for the `openshell.draft_policy.*` family (step wiring maps JSON `execute.kind` → existing `openshell.*` step types). Allow / deny / needs_approval; deny-by-default for unknown actions; gRPC + `MockOpenShellClient`.
- **`/action/authorize`**, **`/action/execute`**: create/link `GovernanceProposalRecord`, persist `DecisionRecord`, audit, optional OpenShell execution; `ExecutionRecord` for runtime outcome.
- **`/action/simulate`**: **ephemeral governance** — computes the same `ExecutionPlan` as authorize **without** creating `GovernanceProposalRecord` or `DecisionRecord`; stores one **audit** row only (`audit_id` in response). See `README.md`.
- **Approval workflow**: `POST /approval-requests`, decision endpoint, resume execute via `steward_resume_proposal_id` + `approval_request_id`; **`ApprovalRequestRecord.decision_record_id` updated** to the post-approval allow `DecisionRecord` after successful approved execute.
- **Phase 1A bulk rule**: `openshell.draft_policy.approve_all` and `.clear` **always** yield `needs_approval` (even for `role=operator`); **`bulk_always_needs_approval: true`** in technical JSON plus loader validation (cannot ship `false` for those actions).
- **Proposal lifecycle** types and `POST /proposals`, `GET /proposals/{id}`; **`/action/*` still creates a new governance proposal per call** (no deduplication by content hash).
- **DecisionRecord vs ExecutionRecord** separation; **GET** `/decision-records/{id}`, `/execution-records/{id}`.
- **EffectivePolicy** merge (`effective_policy.py`) + **`POST /effective-policy/resolve`**, **`GET /effective-policy`**. **Authoritative inputs** for autonomy ceiling merge live in `steward_service/data/effective_policy_merge.json`: constitution (`version`, `autonomy_ceiling`), ordered **`role_ceilings`** (match_roles + priority; `*` fallback), **`local_policy`** (context key / field for `steward_local_policy.autonomy_ceiling`, invalid-tier behavior), and **`merge`** metadata (clamp flags, `effective_operation: min_index`). Loaded by **`policy_merge_layer.py`**; **`resolve_effective_policy`** uses the layer (optional `policy_merge_layer=` override for tests). **`GET /policies/policy.steward.effective_policy_merge.v1`** exposes bundle metadata. **`DEFAULT_CONSTITUTION`** is lazily derived from that JSON (`__getattr__`) so imports stay aligned.
- **Candidate evaluation**: `POST /action/evaluate`, `POST /candidate-sets/evaluate` + `GET /candidate-sets/{id}`; selection heuristics in `main.py`. **`/action/evaluate`** creates a **`GovernanceProposalRecord` + `DecisionRecord` per candidate**, links each **authorize-kind audit** with `governance_proposal_id` / `decision_record_id`, and **`POST /approval-requests`** accepts those proposals when `needs_approval` — same approval target semantics as **`/action/authorize`** (enables NemoClaw `/nemoclaw request` → `/nemoclaw approval complete`).
- **Institutional expenditure slice**: `POST /institution/authorize`, `GET /institution/decision-records/{id}` — **authoritative rules** in `steward_service/data/institution_expenditure_rules.json` (required facts, role rules with priorities, fallback). Evaluated by `institution_engine.py`. **`GET /policies/institution.expenditure.v1`** returns metadata/version from that bundle. **Note:** response field `decision_record_id` is an **institutional** id, not `GET /decision-records/...`.
- **Registry read API**: `GET /roles|policies|capabilities|tools/{id}` — **capabilities/tools/roles** remain seeded in `registry_catalog.py` (metadata; **default risk per capability** still merged with JSON `base_risk_tier` via `merge_action_and_capability_risk`). **Policies registered from JSON at startup:** `institution.expenditure.v1`, **`policy.technical.draft_policy.v1`**, **`policy.steward.effective_policy_merge.v1`**.
- **Technical vs institutional vs policy-layer:** **Institutional** = domain decisions (`institution_engine.py` + expenditure JSON). **Technical** = draft-policy execution planning (technical governance JSON). **Policy merge layer** = cross-cutting autonomy ceiling (constitution / role / local) consumed by **`governance.py`** and **`/effective-policy/resolve`** — same declarative pattern (bundled versioned JSON + registry policy id).
- **Context hooks** in `governance.py`: `steward_skill_profile`, `steward_identity_trusted`, `steward_governance_outcome_hint`, `steward_local_policy`.
- **Storage**: **default in-memory**; optional **SQLite** durability — `STEWARD_STORAGE_BACKEND=sqlite` and `STEWARD_SQLITE_PATH=/path/to/steward.db` (see `README.md`). Protocols: `steward_service/storage/protocols.py`; factory: `storage/factory.py`.

#### Partial

- **Registry “backing”** (draft policy / OpenShell): **draft-policy action definitions** are JSON-driven; **capability/tool rows** in `registry_catalog.py` are still **seeded GET metadata** (not generated from the technical JSON). **`execute_plan`** step dispatch and outcome-hint / skill / trust logic remain **procedural** in `governance.py`. **EffectivePolicy:** merge **algorithm** is still fixed (`min` of tier indices with clamps); **tier tables and wiring** are JSON-driven — not arbitrary expression evaluation or alternate merge strategies without a code change.
- **Proposal lifecycle vs `/action/*`**: full state enum exists; compatibility path **does not** reuse one row per stable content id.
- **Institutional**: expenditure **is** JSON-driven; broader institutional domains / external fact services **not** implemented.
- **ApprovalRequestState**: `under_review` / `revoked` exist in the model but are **unused** in HTTP handlers.
- **NemoClaw / OpenClaw** integration: **plugin code is not in this repo**; Steward only defines HTTP contracts and `operator_hints`. **As of sibling NemoClaw update:** `/nemoclaw institution authorize expenditure …`, `/nemoclaw institution record …`, policy/approval/records/request flows call this service; verify in NemoClaw repo + sandbox E2E.

#### Planned (not implemented here)

- **Postgres / HA** persistence, multi-worker SQLite strategy, backup/restore playbooks.
- **Broader registry-driven governance** beyond the **draft-policy** technical slice (other action families, optional codegen/sync from JSON into `registry_catalog`).
- **Institutional** domains beyond expenditure; authoritative fact resolution; full procedure engine; fleet/constitutional distribution.
- HTTP authentication/authorization for Steward API.

---

1. What we set out to build

The goal was not merely to add guardrails around an AI assistant. The goal was to build a governance plane for agentic systems.

We wanted a system where an agent could:
	•	interpret user requests,
	•	plan actions,
	•	use tools,
	•	access data,
	•	make or recommend decisions,
	•	and still operate inside explicit governance boundaries.

That led to a layered architecture with three main runtime components:
	•	OpenClaw as the user-facing agent interaction layer,
	•	Steward as the governance plane,
	•	OpenShell as the runtime enforcement layer.

A concise description of the intended split became:
	•	OpenClaw decides what to try.
	•	Steward decides whether it may happen.
	•	OpenShell controls how it happens.

Over time, this expanded from technical runtime governance into a broader Agentic AI Governance Framework for public systems and enterprises.

⸻

2. The framework we developed

We built a governance ontology to think about agentic systems in institutional settings.

The final working ontology became:
	•	Identity defines who is acting.
	•	Role defines authority.
	•	Purpose defines why it is being done.
	•	Rules define what is allowed.
	•	Facts define what is true.
	•	Context defines where, when, and under what conditions it is happening.
	•	Procedures define how it must be done.
	•	Capabilities define what is needed.
	•	Tools define how it is done.
	•	Skills define whether it can be done well enough.
	•	Approval defines who else must authorize it.
	•	Outcome defines what effect it produces.
	•	Record defines how it can be explained, reviewed, and challenged later.
	•	Governance decides whether it may proceed.

We then grouped this into a more structured framework:

Authority and legitimacy:
	•	Identity
	•	Role
	•	Purpose
	•	Approval

Reasoning and validity:
	•	Rules
	•	Facts
	•	Context
	•	Procedure

Execution:
	•	Capabilities
	•	Tools
	•	Skills

Effects and accountability:
	•	Outcome
	•	Record

Control:
	•	Governance

This gave us a formal way to think about both technical actions and institutional decisions.

⸻

3. The layered governance architecture

We then framed governance as a layered model.

Constitutional layer

Defines outer bounds for all agents. This includes non-overridable restrictions, mandatory approvals, audit requirements, and system-wide safety boundaries.

Role layer

Defines the governed package for a class of agent: its authority, prompt package, allowed decisions, actions, capabilities, skill expectations, and escalation behavior.

Local operational layer

Defines environment-specific narrowing: which roles are enabled, which tools are available, what websites or systems are reachable, and what is permitted in a given desktop, server, or department context.

Request-time layer

Evaluates a concrete proposal in real time using the applicable rules, facts, context, procedure, capabilities, tools, skills, and approvals.

We also clarified that the effective policy is the result of combining:
	•	constitutional policy,
	•	role policy,
	•	local policy,
	•	and scoped approvals.

⸻

4. The architecture we intended for Steward

Steward was never meant to remain only a small API wrapper around OpenShell. It was meant to evolve into a governance plane composed of several capabilities:
	•	Proposal lifecycle handling
	•	Governance decisioning
	•	Approval workflow
	•	Decision and execution record management
	•	Policy resolution
	•	Runtime integration
	•	Later, registries for roles, capabilities, policies, procedures, and facts

We explicitly decided that Steward should evolve, not be rewritten from scratch. The architecture seam was correct. The scope had simply widened.

⸻

5. What we accomplished technically in Steward

5.1 Explicit governed action flow

We first proved the narrowest useful seam: explicit technical actions could be mediated by Steward before execution.

Steward could:
	•	classify actions,
	•	return allow, deny, or needs_approval,
	•	block execution when approval was missing,
	•	and call OpenShell only when permitted.

This gave us the first real governance boundary.

5.2 Proposal lifecycle

We then introduced a Proposal as the core unit of evaluation rather than treating every call as an untracked action.

A proposal lifecycle was added with states such as:
	•	draft
	•	submitted
	•	evaluated
	•	denied
	•	approval_pending
	•	approved
	•	executing
	•	executed
	•	execution_failed
	•	closed

This made governance stateful instead of purely momentary.

5.3 DecisionRecord and ExecutionRecord separation

A major architectural improvement was separating governance outcome from runtime outcome.

That allowed the system to express cases like:
	•	governance allowed the action,
	•	but runtime failed.

This was proven with concrete tests, such as attempting to approve a non-existent chunk:
	•	governance returned allow,
	•	OpenShell returned chunk not found,
	•	and the response preserved that distinction.

5.4 ApprovalRequest lifecycle

Approval was elevated from a status string into a first-class object with its own lifecycle.

Approval request states were introduced, and execution was made resumable only when a valid approval existed.

This was one of the most important shifts from prototype to governance system.

5.5 Full approval happy path

The full lifecycle was proven:
	•	authorize
	•	needs_approval
	•	create approval request
	•	approve it
	•	resume the same proposal
	•	execute
	•	store decision and execution records

This was a major milestone.

5.6 CandidateActionSet support

We moved from governing only explicit actions to governing candidate actions.

For a request like:
“Please make npm installs work in this sandbox.”

the system could:
	•	generate multiple candidate actions,
	•	evaluate them,
	•	select the best one under governance,
	•	and handle approval if that selected candidate required it.

This was the first meaningful step from action governance to intent-to-action governance.

5.7 EffectivePolicy and registries

**Implemented:** EffectivePolicy merge and risk ceiling integration in `governance.py`. **Partial:** `PolicyDefinition`, `RoleDefinition`, `CapabilityDefinition`, `ToolDefinition` exist as **seeded GET** resources (`registry_catalog.py`); they do **not** yet drive evaluation logic. **Planned:** versioned registry as source of truth for governance.

⸻

6. What we accomplished in NemoClaw and OpenClaw

6.1 Explicit policy flows

NemoClaw became the operator-facing interface for testing and using Steward through OpenClaw TUI.

Commands like:
	•	/nemoclaw policy get manz
	•	/nemoclaw policy approve-all manz

were routed through Steward.

6.2 Approval completion in TUI

We then exposed the approval lifecycle in OpenClaw.

The operator-facing flow became:
	•	/nemoclaw policy approve-all manz
	•	response: Approval required, with an authorize audit id
	•	/nemoclaw approval complete <audit-id>
	•	response: Approval completed and execution finished

This was a huge milestone because approval completion moved from curl-level backend behavior into an operator-visible TUI loop.

6.3 Record inspection in TUI

We added TUI commands to inspect records:
	•	/nemoclaw records audit <id>
	•	/nemoclaw records decision <id>
	•	/nemoclaw records execution <id>

This made governance inspectable from the same surface where actions were initiated.

6.4 Approval-aware candidate-action flow

We extended /nemoclaw request ... so that if the selected candidate required approval, NemoClaw could surface:
	•	the selected candidate,
	•	why approval was needed,
	•	the authorize audit id,
	•	the exact next step:
/nemoclaw approval complete <audit-id>

This brought the approval lifecycle into the request-driven candidate evaluation path as well.

**Integrated contract:** Steward **`POST /action/evaluate`** persists a **governance proposal + decision record** per candidate audit (aligned with **`/action/authorize`**), so **`/nemoclaw approval complete <audit-id>`** can drive **`POST /approval-requests`** and resumed **`POST /action/execute`** for evaluate-originated ids. See `steward_service/main.py` `_evaluate_candidates_impl` and `tests/test_candidate_evaluate_endpoint.py`.

⸻

7. What we accomplished conceptually beyond technical governance

The framework expanded from technical policy mediation into a broader governance model.

7.1 Institutional rules

We clarified that governance must handle not just technical permissions such as:
	•	can this tool run?
	•	can this website be accessed?

but also institutional rules such as:
	•	Junior Engineer may approve expenditure only below Rs 50,000.

This was an important leap. It meant Steward should eventually answer not only:
“Can this action run?”
but also:
“May this decision be taken by this role in this case?”

7.2 Rules and facts

We defined decisions as:
Rules applied to Facts by an authorized Role in a given Context and through a required Procedure.

This shifted the architecture toward institutional decision governance.

7.3 Procedure and skill

We recognized that a decision can be substantively correct but procedurally invalid, and that permission is not enough if the agent lacks competence.

So procedure and skill became first-class concepts in the framework.

7.4 AI-assisted governance authoring

We also recognized that the governance model is too complex for most teams to author by hand without help.

So we discussed AI as a co-author for:
	•	extracting rules,
	•	drafting procedures,
	•	identifying required facts,
	•	defining roles,
	•	detecting gaps and inconsistencies,
	•	and helping convert human policy text into structured publishable governance artifacts.

The principle was:
AI should help author the governance model, but humans should approve and publish it.

⸻

8. What we accomplished on institutional decision governance

We implemented the first institutional decision vertical slice: expenditure authorization.

8.1 Initial slice

A first endpoint was added:
	•	POST /institution/authorize

and a record inspection endpoint:
	•	GET /institution/decision-records/{id}

Initially, a simple rule was applied:
	•	junior_engineer may allow only if amount_rs <= 50,000
	•	above threshold → escalate
	•	missing required fields → defer
	•	other roles → needs_approval

This already proved the shift from tool governance to institutional decision governance.

8.2 TUI exposure

We then exposed this through NemoClaw with commands like:
	•	/nemoclaw institution authorize expenditure junior_engineer 10000
	•	/nemoclaw institution authorize expenditure junior_engineer 75000
	•	/nemoclaw institution authorize expenditure junior_engineer
	•	/nemoclaw institution record <decision_record_id>

This made the institutional slice testable and demonstrable from OpenClaw.

8.3 Minimal reusable engine

**Implemented:** Expenditure behavior is driven by **`steward_service/data/institution_expenditure_rules.json`** (required facts, ordered role rules with `threshold_escalate_above` / `threshold_needs_approval_above`, fallback). Loader: `institution_rules.py`; evaluator: `institution_engine.py`; wired from `main.py`. **`GET /policies/institution.expenditure.v1`** reflects JSON version/metadata.

**Still partial:** facts are only request **parameters** and **context** (no external fact services). “Procedure” is declarative **presence checks** on keys, not a workflow engine.

**Planned:** more domains, external fact resolution, richer procedure modeling.

⸻

9. Where the system stands now

At this point, four meaningful governance loops exist.

9.1 Technical governance loop

The system can govern concrete technical actions such as policy operations against OpenShell-managed sandboxes.

Example (NemoClaw / external client; not in this repo):
	•	policy get flows
	•	bulk **approve_all** / **clear** require **needs_approval** in Steward even for operator — then approval + resume execute (see `governance.py`).

9.2 Approval loop

High-risk actions can be:
	•	blocked,
	•	turned into approval requests,
	•	approved,
	•	resumed,
	•	and executed as the same proposal.

9.3 Candidate-action loop

For user-style requests, the system can:
	•	generate candidate actions,
	•	evaluate them,
	•	choose one,
	•	and route approval if needed.

9.4 Institutional decision loop

The system can apply a domain rule to a fact pattern under a role and return:
	•	allow
	•	escalate
	•	needs_approval
	•	defer

This is the first real public-system style governance slice.

⸻

10. What was still planned next

Although a lot was accomplished, the system was still not finished. The work ahead fell into a few major themes.

10.1 Make the institutional engine more declarative

The expenditure slice had become a minimal reusable engine, but it still had hard-coded boundaries.

The next planned step was:
	•	add rule priority/precedence,
	•	move required fact requirements out of code,
	•	make procedure requirements more declarative,
	•	keep evaluator narrow but more general.

This would turn the expenditure slice into a more reusable institutional decision engine rather than a domain-specific demo.

10.2 Expand registry-backed governance

The next phase was to continue moving definitions out of code and into registry-backed objects:
	•	RoleDefinition
	•	CapabilityDefinition
	•	ToolDefinition
	•	ProcedureDefinition
	•	richer PolicyDefinition

The aim was that governance should increasingly come from published, versioned definitions rather than embedded branches.

10.3 Fact resolution architecture

Facts were still mostly assumed or passed in. The next step was to define:
	•	authoritative fact sources,
	•	fact resolution service interfaces,
	•	freshness/provenance handling,
	•	and explicit required-fact declarations per decision type.

10.4 Procedure engine

Procedure was explicit conceptually, but still minimal in implementation.

The next step was to make procedures:
	•	machine-readable,
	•	sequenced,
	•	tied to role and approval requirements,
	•	and checkable at runtime.

10.5 Institutional domains beyond expenditure

After expenditure, the next natural directions would have been:
	•	eligibility decisions,
	•	procurement decisions,
	•	sanctioning and escalation flows,
	•	or similar domain governance slices.

10.6 Identity and entitlements

Identity hardening had begun conceptually, but the next implementation phase would have strengthened:
	•	acting-for relationships,
	•	entitlement resolution,
	•	less reliance on free-form caller role claims.

10.7 Fleet governance

Still future work:
	•	policy distribution,
	•	central registry publishing,
	•	local runtime bundles,
	•	desktop/server policy sync,
	•	and enterprise/public authority as the constitutional layer.

⸻

11. What to preserve as the central narrative

If someone asks what was built, the best high-level summary is:

We started by governing tool execution.
Then we governed approvals.
Then we governed how a user request becomes a selected action.
Then we began governing real institutional decisions using roles, rules, facts, context, and procedure.

That is the progression.

A concise summary of the **Steward service** state in this repo:
	•	Working governance plane (HTTP API + in-memory stores).
	•	Approval-aware; bulk draft-policy actions require explicit approval.
	•	Candidate-action evaluation with persisted candidate sets.
	•	Institutional expenditure slice (junior + senior engineer rules) in code.
	•	Registry GETs for documentation/interop; **governance logic is still mostly code**, not catalog-driven.
	•	OpenClaw/NemoClaw TUI: **separate repositories** — NemoClaw slash commands + Steward HTTP alignment are implemented in the NemoClaw repo; **sandbox E2E** is not run from this repo.

⸻

12. Recommended immediate next step

**Done:** `DEEP_REVIEW.md` and `RECOVERY_CHECKLIST.md` capture code reality; a remediation pass fixed approval–decision linkage, `/action/simulate` persistence contract, bulk approval enforcement, and senior engineer institutional rules (see `DEEP_REVIEW.md` “Remediation (changelog)”).

**Next:** durable persistence for governance artifacts; optional deduplication of `GovernanceProposalRecord` for repeated `/action/*` with identical content; integrate or replace registry seeds with a real policy source; ongoing NemoClaw ↔ Steward E2E in sandbox (institution + request + policy loops).
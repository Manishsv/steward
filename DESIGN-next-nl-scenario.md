## Next natural-language scenario (recommended)

**Scenario**: “Please make `git clone` work in this sandbox.”

### Why this is a good next step
- **Common**: many real workflows begin with fetching code.
- **Governable**: can be expressed as narrow network policy changes (specific hosts/ports, specific binaries).
- **Demonstrates safety**: we can prefer least-privilege fixes (e.g., allow `github.com:443` for `git`) and fall back to diagnostics.

## Candidate → evaluate → select → execute pattern

### Inputs (from NemoClaw)
- `sandbox_name`
- `user_request` text (string)
- `requested_by`, `channel` (context)
- Candidate list (small, intent-specific)

### Candidate set (minimal v1)
All candidates include `type` to drive selection (`remediation`, `diagnostic`, `administrative`).

- **Remediation**: allow GitHub over HTTPS for `git`
  - action: `openshell.draft_policy.approve_matching`
  - parameters:
    - `match.host = "github.com"`
    - `match.port = 443`
    - `match.binary_path = "/usr/bin/git"` (or the sandbox’s git path)
  - type: `remediation`
  - label: “Allow git to reach GitHub (fix git clone)”

- **Remediation**: allow GitHub “raw” host used by some tooling
  - action: `openshell.draft_policy.approve_matching`
  - parameters:
    - `match.host = "raw.githubusercontent.com"`
    - `match.port = 443`
    - `match.binary_path = "/usr/bin/git"`
  - type: `remediation`
  - label: “Allow git to reach raw.githubusercontent.com (fix fetches)”

- **Diagnostic**: inspect pending network rules
  - action: `openshell.draft_policy.get`
  - type: `diagnostic`
  - label: “Check pending network rules (diagnostic)”

### Selection rule (smallest safe version)
Goal-aware for this scenario, using `user_request`:
- Prefer a **remediation** candidate that matches the likely host (e.g., `github.com`, `raw.githubusercontent.com`) when `git clone` intent is detected.
- Prefer **lowest risk** among relevant remediation candidates.
- Allow **diagnostic** to win only when no remediation is `allow`/`needs_approval`.
- If nothing is `allow`, surface the best `needs_approval` option and explain approval is required.

### Execution + user-facing rendering
- If remediation selected and `allow`: execute and show:
  - Outcome: “Fix applied.”
  - What changed (natural language): “git can now reach github.com:443”
  - Next: “retry `git clone …`”
- If diagnostic selected and `allow`: execute and show:
  - Outcome: “Diagnostics collected.”
  - Summary: number of pending rules, and (if found) the most relevant pending rule id
  - Next action: `/nemoclaw policy approve <sandbox> <id>` (if a relevant pending rule exists)

## Smallest implementation plan
1. **NemoClaw**: add a new intent branch in `/nemoclaw request` for `git clone` detection.
2. **NemoClaw**: build the candidate list above with `type` and readable labels.
3. **Steward**: no new actions required (reuse `openshell.draft_policy.approve_matching` + `get`).
4. **NemoClaw**: add a renderer summary similar to npm scenario (“pending rule”, “recommended next action”).
5. **Tests**: add one request test where remediation wins; one where diagnostic wins and recommends `/nemoclaw policy approve …`.


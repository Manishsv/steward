"""Technical draft-policy governance: bundled JSON drives risk, capability/tool, and approval gates."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from steward_service.domain import ActionType, Proposal, RiskTier
from steward_service.governance import build_execution_plan
from steward_service.openshell_client import MockOpenShellClient
from steward_service.technical_governance import TechnicalDraftPolicyGovernance, load_technical_draft_policy_governance


def _bundle_path() -> Path:
    return Path(__file__).resolve().parent.parent / "steward_service" / "data" / "technical_draft_policy_governance.json"


def _load_gov_with_action_patch(steward_action_suffix: str, **patch: object) -> TechnicalDraftPolicyGovernance:
    raw = json.loads(_bundle_path().read_text(encoding="utf-8"))
    for a in raw["actions"]:
        if str(a["steward_action"]).endswith(steward_action_suffix):
            a.update(patch)
            break
    else:
        raise AssertionError(f"no action ending with {steward_action_suffix!r}")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "gov.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return load_technical_draft_policy_governance(path)


class TestTechnicalGovernanceFromRegistry(unittest.TestCase):
    def test_default_get_low_risk_allow(self) -> None:
        gov = load_technical_draft_policy_governance(_bundle_path())
        os = MockOpenShellClient()
        os.get_draft_policy(sandbox_name="manz")
        p = Proposal(
            proposal_id="p1",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.get",
            purpose="test",
            role="operator",
            context={},
            parameters={"sandbox_name": "manz"},
        )
        plan = build_execution_plan(p, os, technical_gov=gov)
        self.assertEqual(plan.risk_tier, RiskTier.low)
        self.assertEqual(plan.decision.value, "allow")
        self.assertEqual(plan.capability_id, "cap.openshell.draft_policy.read")
        self.assertEqual(plan.tool_id, "tool.openshell.draft_policy.get")

    def test_json_base_risk_tier_merges_into_plan_risk(self) -> None:
        gov = _load_gov_with_action_patch(".get", base_risk_tier="high")
        os = MockOpenShellClient()
        p = Proposal(
            proposal_id="p",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.get",
            purpose="t",
            role="operator",
            context={},
            parameters={"sandbox_name": "sx"},
        )
        plan = build_execution_plan(p, os, technical_gov=gov)
        self.assertEqual(plan.risk_tier, RiskTier.high)
        self.assertEqual(plan.decision.value, "allow")

    def test_json_base_risk_high_on_approve_triggers_ceiling_approval(self) -> None:
        gov = _load_gov_with_action_patch(".approve", base_risk_tier="high")
        os = MockOpenShellClient()
        cid = os.seed_pending_chunk(
            sandbox_name="sapprove",
            rule_name="r",
            proposed_rule={"name": "r", "endpoints": [], "binaries": []},
            rationale="",
        )
        p = Proposal(
            proposal_id="p",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.approve",
            purpose="t",
            role="operator",
            context={},
            parameters={"sandbox_name": "sapprove", "chunk_id": cid},
        )
        plan = build_execution_plan(p, os, technical_gov=gov)
        self.assertEqual(plan.decision.value, "needs_approval")
        self.assertTrue(any("ceiling" in r.reason.lower() for r in plan.requirements))

    def test_loader_enforces_bulk_always_needs_approval_for_approve_all(self) -> None:
        raw = json.loads(_bundle_path().read_text(encoding="utf-8"))
        for a in raw["actions"]:
            if str(a["steward_action"]).endswith("approve_all"):
                a["bulk_always_needs_approval"] = False
                break
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_technical_draft_policy_governance(path)
            self.assertIn("bulk_always_needs_approval", str(ctx.exception))

    def test_approve_all_and_clear_still_require_approval_from_json_flag(self) -> None:
        gov = load_technical_draft_policy_governance(_bundle_path())
        os = MockOpenShellClient()
        for action, purpose in (
            ("openshell.draft_policy.approve_all", "bulk"),
            ("openshell.draft_policy.clear", "clear"),
        ):
            p = Proposal(
                proposal_id="p",
                action_type=ActionType.openshell_draft_policy,
                action=action,
                purpose=purpose,
                role="operator",
                context={},
                parameters={"sandbox_name": "sb"},
            )
            plan = build_execution_plan(p, os, technical_gov=gov)
            self.assertEqual(plan.decision.value, "needs_approval", msg=action)
            aa = gov.actions_by_steward_action[action]
            self.assertTrue(aa.bulk_always_needs_approval)


if __name__ == "__main__":
    unittest.main()

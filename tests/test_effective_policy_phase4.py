"""Phase 4: EffectivePolicy merge and governance integration."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from steward_service.domain import ActionType, Proposal, RiskTier
from steward_service.effective_policy import (
    DEFAULT_CONSTITUTION,
    resolve_effective_policy,
    risk_exceeds_autonomy_ceiling,
)
from steward_service.governance import build_execution_plan
from steward_service.main import app
from steward_service.openshell_client import MockOpenShellClient


class TestEffectivePolicyMerge(unittest.TestCase):
    def test_constitution_caps_local_widen_attempt(self) -> None:
        p = Proposal(
            proposal_id="x",
            action_type=ActionType.generic,
            action="noop",
            purpose="t",
            role="operator",
            context={"steward_local_policy": {"autonomy_ceiling": "high"}},
            parameters={},
        )
        ep = resolve_effective_policy(p)
        self.assertEqual(ep.autonomy_ceiling, DEFAULT_CONSTITUTION.autonomy_ceiling)

    def test_local_narrows_ceiling(self) -> None:
        p = Proposal(
            proposal_id="x",
            action_type=ActionType.generic,
            action="noop",
            purpose="t",
            role="operator",
            context={"steward_local_policy": {"autonomy_ceiling": "low"}},
            parameters={},
        )
        ep = resolve_effective_policy(p)
        self.assertEqual(ep.autonomy_ceiling, RiskTier.low)

    def test_medium_risk_exceeds_low_ceiling_in_plan(self) -> None:
        openshell = MockOpenShellClient()
        cid = openshell.seed_pending_chunk(
            sandbox_name="s4",
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
            context={"steward_local_policy": {"autonomy_ceiling": "low"}},
            parameters={"sandbox_name": "s4", "chunk_id": cid},
        )
        plan = build_execution_plan(p, openshell)
        self.assertEqual(plan.decision.value, "needs_approval")


class TestEffectivePolicyAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_resolve_endpoint(self) -> None:
        res = self.client.post(
            "/effective-policy/resolve",
            json={"role": "agent", "context": {"steward_local_policy": {"autonomy_ceiling": "low"}}},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["autonomy_ceiling"], "low")


if __name__ == "__main__":
    unittest.main()

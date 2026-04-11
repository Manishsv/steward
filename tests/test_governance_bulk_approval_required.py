"""Phase 1A: approve_all and clear always require approval workflow (even for operator)."""

from __future__ import annotations

import unittest

from steward_service.domain import ActionType, Proposal
from steward_service.governance import build_execution_plan
from steward_service.openshell_client import MockOpenShellClient


class TestBulkDraftPolicyRequiresApproval(unittest.TestCase):
    def test_approve_all_operator_still_needs_approval(self) -> None:
        os = MockOpenShellClient()
        p = Proposal(
            proposal_id="p",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.approve_all",
            purpose="bulk",
            role="operator",
            context={},
            parameters={"sandbox_name": "sbulk"},
        )
        plan = build_execution_plan(p, os)
        self.assertEqual(plan.decision.value, "needs_approval")
        self.assertTrue(any("bulk" in r.reason.lower() for r in plan.requirements))

    def test_clear_operator_still_needs_approval(self) -> None:
        os = MockOpenShellClient()
        p = Proposal(
            proposal_id="p2",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.clear",
            purpose="clear all",
            role="operator",
            context={},
            parameters={"sandbox_name": "sclear"},
        )
        plan = build_execution_plan(p, os)
        self.assertEqual(plan.decision.value, "needs_approval")
        self.assertTrue(any("bulk" in r.reason.lower() for r in plan.requirements))


if __name__ == "__main__":
    unittest.main()

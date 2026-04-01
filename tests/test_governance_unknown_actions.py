import unittest

from steward_service.domain import ActionType, Proposal
from steward_service.governance import build_execution_plan
from steward_service.openshell_client import MockOpenShellClient


class TestGovernanceUnknownActions(unittest.TestCase):
    def test_supported_draft_get_is_allowed(self) -> None:
        openshell = MockOpenShellClient()
        # Seed a draft so get has a valid sandbox context.
        openshell.get_draft_policy(sandbox_name="manz")
        p = Proposal(
            proposal_id="p1",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.get",
            purpose="test",
            role="operator",
            context={},
            parameters={"sandbox_name": "manz"},
        )
        plan = build_execution_plan(p, openshell)
        self.assertEqual(plan.decision.value, "allow")

    def test_unknown_action_is_denied(self) -> None:
        openshell = MockOpenShellClient()
        p = Proposal(
            proposal_id="p2",
            action_type=ActionType.generic,
            action="openshell.unknown_action.do_something",
            purpose="test",
            role="operator",
            context={},
            parameters={},
        )
        plan = build_execution_plan(p, openshell)
        self.assertEqual(plan.decision.value, "deny")
        self.assertIn("Unsupported action", plan.rationale)

    def test_malformed_action_is_denied(self) -> None:
        openshell = MockOpenShellClient()
        p = Proposal(
            proposal_id="p3",
            action_type=ActionType.generic,
            action="   ",
            purpose="test",
            role="operator",
            context={},
            parameters={},
        )
        plan = build_execution_plan(p, openshell)
        self.assertEqual(plan.decision.value, "deny")
        self.assertIn("Missing action", plan.rationale)


if __name__ == "__main__":
    unittest.main()


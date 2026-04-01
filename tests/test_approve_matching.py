import unittest

from steward_service.domain import ActionType, Proposal
from steward_service.governance import build_execution_plan, execute_plan
from steward_service.openshell_client import MockOpenShellClient


class TestApproveMatching(unittest.TestCase):
    def test_approve_matching_executes_on_pending_chunk(self) -> None:
        openshell = MockOpenShellClient()
        openshell.seed_pending_chunk(
            sandbox_name="manz",
            rule_name="allow_registry_npmjs_org_443",
            proposed_rule={
                "name": "allow_registry_npmjs_org_443",
                "endpoints": [{"host": "registry.npmjs.org", "port": 443}],
                "binaries": [{"path": "/usr/local/bin/node"}],
            },
            rationale="Allow npm registry",
        )

        p = Proposal(
            proposal_id="p1",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.approve_matching",
            purpose="make npm installs work",
            role="operator",
            context={},
            parameters={
                "sandbox_name": "manz",
                "match": {"host": "registry.npmjs.org", "port": 443, "binary_path": "/usr/local/bin/node"},
            },
        )
        plan = build_execution_plan(p, openshell)
        self.assertEqual(plan.decision.value, "allow")
        ok, result = execute_plan(openshell, plan)
        self.assertTrue(ok)
        self.assertTrue(result.get("ok"))


if __name__ == "__main__":
    unittest.main()


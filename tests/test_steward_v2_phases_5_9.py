"""Phases 5–9: capability metadata, candidate sets, skill/trust hooks, registry reads."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from steward_service.domain import ActionType, Proposal
from steward_service.governance import build_execution_plan
from steward_service.main import app
from steward_service.openshell_client import MockOpenShellClient


class TestPhase5CapabilityMetadata(unittest.TestCase):
    def test_plan_includes_capability_and_tool_ids(self) -> None:
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
        plan = build_execution_plan(p, os)
        self.assertIn("draft_policy.read", plan.capability_id)
        self.assertTrue(plan.tool_id.startswith("tool."))


class TestPhase6CandidateSets(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_evaluate_persists_candidate_set(self) -> None:
        res = self.client.post(
            "/candidate-sets/evaluate",
            json={
                "candidates": [
                    {
                        "id": "c1",
                        "label": "L1",
                        "proposal": {
                            "action": "openshell.draft_policy.get",
                            "purpose": "t",
                            "role": "operator",
                            "parameters": {"sandbox_name": "s1"},
                        },
                    }
                ]
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        sid = body["candidate_set_id"]
        g = self.client.get(f"/candidate-sets/{sid}")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["id"], sid)
        self.assertEqual(g.json()["candidate_ids"], ["c1"])


class TestPhase7SkillAndOutcomes(unittest.TestCase):
    def test_review_required_adds_gate(self) -> None:
        os = MockOpenShellClient()
        cid = os.seed_pending_chunk(
            sandbox_name="sk",
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
            context={"steward_skill_profile": "review_required"},
            parameters={"sandbox_name": "sk", "chunk_id": cid},
        )
        plan = build_execution_plan(p, os)
        self.assertEqual(plan.decision.value, "needs_approval")

    def test_escalate_outcome(self) -> None:
        os = MockOpenShellClient()
        p = Proposal(
            proposal_id="p",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.get",
            purpose="t",
            role="operator",
            context={"steward_governance_outcome_hint": "escalate"},
            parameters={"sandbox_name": "sk"},
        )
        plan = build_execution_plan(p, os)
        self.assertEqual(plan.decision.value, "deny")
        self.assertIn("escalate", plan.rationale.lower())


class TestPhase8IdentityTrust(unittest.TestCase):
    def test_untrusted_identity_denies(self) -> None:
        os = MockOpenShellClient()
        p = Proposal(
            proposal_id="p",
            action_type=ActionType.openshell_draft_policy,
            action="openshell.draft_policy.get",
            purpose="t",
            role="operator",
            context={"steward_identity_trusted": False},
            parameters={"sandbox_name": "sk"},
        )
        plan = build_execution_plan(p, os)
        self.assertEqual(plan.decision.value, "deny")


class TestPhase9Registry(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_role_operator(self) -> None:
        r = self.client.get("/roles/operator")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "operator")

    def test_get_role_senior_engineer(self) -> None:
        r = self.client.get("/roles/senior_engineer")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "senior_engineer")

    def test_get_capability(self) -> None:
        r = self.client.get("/capabilities/cap.openshell.draft_policy.read")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["resource_family"], "openshell.draft_policy")


if __name__ == "__main__":
    unittest.main()

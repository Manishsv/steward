"""Phase 1: Proposal lifecycle, storage, and /proposals APIs."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from steward_service.main import app


class TestProposalPhase1(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_post_proposals_draft(self) -> None:
        res = self.client.post(
            "/proposals",
            json={
                "proposal": {
                    "action": "openshell.draft_policy.get",
                    "purpose": "test",
                    "role": "operator",
                    "parameters": {"sandbox_name": "s1"},
                },
                "submit": False,
                "evaluate": False,
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["state"], "draft")
        self.assertIn("id", body)
        pid = body["id"]

        g = self.client.get(f"/proposals/{pid}")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["id"], pid)

    def test_post_proposals_evaluate_sets_state(self) -> None:
        res = self.client.post(
            "/proposals",
            json={
                "proposal": {
                    "action": "openshell.draft_policy.get",
                    "purpose": "test",
                    "role": "operator",
                    "parameters": {"sandbox_name": "s1"},
                },
                "evaluate": True,
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn(body["state"], ("approved", "denied", "approval_pending"))
        self.assertIsNotNone(body.get("governance_decision"))
        self.assertIsNotNone(body.get("plan"))

    def test_authorize_links_governance_proposal(self) -> None:
        res = self.client.post(
            "/action/authorize",
            json={
                "proposal": {
                    "action": "openshell.draft_policy.get",
                    "purpose": "test",
                    "role": "operator",
                    "parameters": {"sandbox_name": "s1"},
                },
            },
        )
        self.assertEqual(res.status_code, 200)
        audit_id = res.json()["audit_id"]
        a = self.client.get(f"/audit/{audit_id}")
        self.assertEqual(a.status_code, 200)
        gp_id = a.json()["payload"]["audit"].get("governance_proposal_id")
        self.assertIsNotNone(gp_id)
        p = self.client.get(f"/proposals/{gp_id}")
        self.assertEqual(p.status_code, 200)
        self.assertIn(audit_id, p.json()["linked_audit_ids"])

    def test_execute_marks_execution_states_when_allowed(self) -> None:
        res = self.client.post(
            "/action/execute",
            json={
                "proposal": {
                    "action": "openshell.draft_policy.get",
                    "purpose": "test",
                    "role": "operator",
                    "parameters": {"sandbox_name": "s1"},
                },
            },
        )
        self.assertEqual(res.status_code, 200)
        audit_id = res.json()["audit_id"]
        a = self.client.get(f"/audit/{audit_id}")
        gp_id = a.json()["payload"]["audit"]["governance_proposal_id"]
        p = self.client.get(f"/proposals/{gp_id}").json()
        self.assertEqual(p["state"], "executed")


if __name__ == "__main__":
    unittest.main()

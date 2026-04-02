"""Phase 2: DecisionRecord vs ExecutionRecord separation."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from steward_service.main import app


class TestProposalPhase2(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_execute_has_distinct_decision_and_execution_records(self) -> None:
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
        audit = self.client.get(f"/audit/{res.json()['audit_id']}").json()
        dr_id = audit["payload"]["audit"]["decision_record_id"]
        er_id = audit["payload"]["audit"]["execution_record_id"]
        self.assertIsNotNone(dr_id)
        self.assertIsNotNone(er_id)

        dr = self.client.get(f"/decision-records/{dr_id}").json()
        er = self.client.get(f"/execution-records/{er_id}").json()
        self.assertEqual(dr["decision"], "allow")
        self.assertTrue(er["governance_decision_was_allow"])
        self.assertTrue(er["ok"])
        self.assertEqual(er["decision_record_id"], dr_id)

    def test_denied_governance_execution_record_still_exists(self) -> None:
        res = self.client.post(
            "/action/execute",
            json={
                "proposal": {
                    "action": "openshell.unknown.action",
                    "purpose": "test",
                    "role": "operator",
                    "parameters": {},
                },
            },
        )
        self.assertEqual(res.status_code, 403)
        audit_id = res.json()["detail"]["audit_id"]
        audit = self.client.get(f"/audit/{audit_id}").json()
        dr_id = audit["payload"]["audit"]["decision_record_id"]
        er_id = audit["payload"]["audit"]["execution_record_id"]
        dr = self.client.get(f"/decision-records/{dr_id}").json()
        er = self.client.get(f"/execution-records/{er_id}").json()
        self.assertEqual(dr["decision"], "deny")
        self.assertFalse(er["governance_decision_was_allow"])
        self.assertFalse(er["ok"])


if __name__ == "__main__":
    unittest.main()

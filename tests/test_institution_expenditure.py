"""
Institutional decision governance: minimal expenditure approval slice.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from steward_service.main import app


class TestInstitutionExpenditure(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def _req(self, *, role: str, amount_rs=None, procedure: str | None = "expense_v1", procedure_state: str | None = "request_submitted"):
        params = {}
        if amount_rs is not None:
            params["amount_rs"] = amount_rs
        ctx = {}
        if procedure is not None:
            ctx["procedure"] = procedure
        if procedure_state is not None:
            ctx["procedure_state"] = procedure_state
        return {
            "proposal": {
                "action": "expenditure.approve",
                "purpose": "Approve expenditure",
                "role": role,
                "context": ctx,
                "parameters": params,
            }
        }

    def test_below_threshold_allows_for_junior(self) -> None:
        r = self.client.post("/institution/authorize", json=self._req(role="junior_engineer", amount_rs=10_000))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["outcome"], "allow")
        dr = self.client.get(f"/institution/decision-records/{r.json()['decision_record_id']}").json()
        self.assertEqual(dr["outcome"], "allow")
        self.assertIn("junior_engineer authority", dr["rationale"])

    def test_above_threshold_escalates_for_junior(self) -> None:
        r = self.client.post("/institution/authorize", json=self._req(role="junior_engineer", amount_rs=75_000))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["outcome"], "escalate")

    def test_missing_fact_defers(self) -> None:
        r = self.client.post("/institution/authorize", json=self._req(role="junior_engineer", amount_rs=None))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["outcome"], "defer")
        dr = self.client.get(f"/institution/decision-records/{r.json()['decision_record_id']}").json()
        self.assertIn("amount_rs", dr["missing_facts"])

    def test_senior_below_threshold_allows(self) -> None:
        r = self.client.post("/institution/authorize", json=self._req(role="senior_engineer", amount_rs=150_000))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["outcome"], "allow")
        dr = self.client.get(f"/institution/decision-records/{r.json()['decision_record_id']}").json()
        self.assertEqual(dr["outcome"], "allow")
        self.assertIn("senior_engineer", dr["rationale"].lower())

    def test_senior_above_threshold_needs_approval(self) -> None:
        r = self.client.post("/institution/authorize", json=self._req(role="senior_engineer", amount_rs=250_000))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["outcome"], "needs_approval")


if __name__ == "__main__":
    unittest.main()


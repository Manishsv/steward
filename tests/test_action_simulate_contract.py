"""Contract: /action/simulate does not persist proposals or decision records (audit-only)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import steward_service.main as main_mod
from steward_service.main import app


class TestSimulatePersistenceContract(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_simulate_does_not_create_proposal_or_decision_record(self) -> None:
        p_store = main_mod._proposals
        d_store = main_mod._decisions
        before_p = len(p_store._records) if hasattr(p_store, "_records") else None  # noqa: SLF001
        before_d = len(d_store._records) if hasattr(d_store, "_records") else None  # noqa: SLF001

        res = self.client.post(
            "/action/simulate",
            json={
                "proposal": {
                    "action": "openshell.draft_policy.get",
                    "purpose": "simulate contract",
                    "role": "operator",
                    "parameters": {"sandbox_name": "s_sim"},
                },
            },
        )
        self.assertEqual(res.status_code, 200)
        if before_p is not None:
            self.assertEqual(len(p_store._records), before_p)  # noqa: SLF001
            self.assertEqual(len(d_store._records), before_d)  # noqa: SLF001

        audit_id = res.json()["audit_id"]
        a = self.client.get(f"/audit/{audit_id}").json()
        payload_audit = a.get("payload", {}).get("audit", {})
        self.assertIsNone(payload_audit.get("governance_proposal_id"))
        self.assertIsNone(payload_audit.get("decision_record_id"))
        self.assertEqual(a.get("kind"), "simulate")
        self.assertIn("plan", a.get("payload", {}))

    def test_simulate_returns_plan_matching_authorize_decision(self) -> None:
        body = {
            "proposal": {
                "action": "openshell.draft_policy.get",
                "purpose": "same",
                "role": "operator",
                "parameters": {"sandbox_name": "s_sim2"},
            },
        }
        sim = self.client.post("/action/simulate", json=body).json()
        auth = self.client.post("/action/authorize", json=body).json()
        self.assertEqual(sim["simulation"]["decision"], auth["decision"])


if __name__ == "__main__":
    unittest.main()

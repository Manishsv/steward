import unittest

from fastapi.testclient import TestClient

from steward_service.main import app


class TestCandidateEvaluateEndpoint(unittest.TestCase):
    def test_bulk_evaluate_returns_one_result_per_candidate(self) -> None:
        c = TestClient(app)
        res = c.post(
            "/action/evaluate",
            json={
                "candidates": [
                    {
                        "id": "get",
                        "label": "Fetch draft policy",
                        "proposal": {
                            "action": "openshell.draft_policy.get",
                            "purpose": "test",
                            "role": "operator",
                            "context": {"requested_by": "user:test"},
                            "parameters": {"sandbox_name": "manz"},
                        },
                    },
                    {
                        "id": "unknown",
                        "label": "Unknown action",
                        "proposal": {
                            "action": "openshell.unknown_action.do_something",
                            "purpose": "test",
                            "role": "operator",
                            "context": {"requested_by": "user:test"},
                            "parameters": {},
                        },
                    },
                ]
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("evaluations", body)
        self.assertIn("selection", body)
        self.assertEqual(len(body["evaluations"]), 2)
        by_id = {e["id"]: e for e in body["evaluations"]}
        self.assertEqual(by_id["get"]["decision"], "allow")
        self.assertEqual(by_id["unknown"]["decision"], "deny")
        self.assertTrue(by_id["get"]["audit_id"])
        self.assertTrue(by_id["unknown"]["audit_id"])
        self.assertIn("risk_tier", by_id["get"])
        self.assertIn("risk_tier", by_id["unknown"])
        self.assertEqual(body["selection"]["selected_id"], "get")
        self.assertEqual(body["selection"]["decision"], "allow")

    def test_goal_aware_prefers_remediation_when_allowed(self) -> None:
        c = TestClient(app)
        res = c.post(
            "/action/evaluate",
            json={
                "candidates": [
                    {
                        "id": "get-draft",
                        "label": "Fetch draft policy",
                        "type": "diagnostic",
                        "proposal": {
                            "action": "openshell.draft_policy.get",
                            "purpose": "Inspect",
                            "role": "operator",
                            "context": {"user_request": "Please make npm installs work in this sandbox."},
                            "parameters": {"sandbox_name": "manz"},
                        },
                    },
                    {
                        "id": "approve-npm-registry",
                        "label": "Approve npm registry access for Node",
                        "type": "remediation",
                        "proposal": {
                            "action": "openshell.draft_policy.approve_matching",
                            "purpose": "Enable npm installs",
                            "role": "operator",
                            "context": {"user_request": "Please make npm installs work in this sandbox."},
                            "parameters": {
                                "sandbox_name": "manz",
                                "match": {"host": "registry.npmjs.org", "port": 443, "binary_path": "/usr/local/bin/node"},
                            },
                        },
                    },
                ]
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        # Even if risk differs, remediation should win when it is allowed and relevant.
        self.assertEqual(body["selection"]["selected_id"], "approve-npm-registry")
        self.assertEqual(body["selection"]["decision"], "allow")

    def test_evaluate_audit_links_governance_proposal_for_needs_approval(self) -> None:
        """Each evaluate audit must back POST /approval-requests (NemoClaw approval complete)."""
        c = TestClient(app)
        res = c.post(
            "/action/evaluate",
            json={
                "candidates": [
                    {
                        "id": "bulk",
                        "label": "Approve all pending",
                        "proposal": {
                            "action": "openshell.draft_policy.approve_all",
                            "purpose": "bulk approve",
                            "role": "operator",
                            "context": {"requested_by": "user:test"},
                            "parameters": {"sandbox_name": "manz"},
                        },
                    },
                ]
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["evaluations"]), 1)
        ev = body["evaluations"][0]
        self.assertEqual(ev["decision"], "needs_approval")
        audit_id = ev["audit_id"]
        self.assertTrue(audit_id)
        ar = c.get(f"/audit/{audit_id}")
        self.assertEqual(ar.status_code, 200)
        aud = ar.json()
        self.assertTrue(aud.get("governance_proposal_id"))
        gp_id = aud["governance_proposal_id"]
        apr = c.post("/approval-requests", json={"governance_proposal_id": gp_id})
        self.assertEqual(apr.status_code, 200, msg=apr.text)
        self.assertEqual(apr.json()["governance_proposal_id"], gp_id)


if __name__ == "__main__":
    unittest.main()


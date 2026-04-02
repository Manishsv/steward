"""Phase 3: ApprovalRequest objects and execute gating."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import steward_service.main as main_mod
from steward_service.main import app
from steward_service.openshell_client import MockOpenShellClient


def _needs_approval_proposal(*, sandbox: str, chunk_id: str) -> dict:
    """Agent role on draft approve triggers operator approval requirement."""
    return {
        "action": "openshell.draft_policy.approve",
        "purpose": "phase3 test",
        "role": "agent",
        "parameters": {"sandbox_name": sandbox, "chunk_id": chunk_id},
    }


class TestProposalPhase3(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        if isinstance(main_mod._openshell, MockOpenShellClient):
            self._sandbox = f"s_phase3_{id(self)}"
            self._chunk_id = main_mod._openshell.seed_pending_chunk(
                sandbox_name=self._sandbox,
                rule_name="r1",
                proposed_rule={"name": "r1", "endpoints": [], "binaries": []},
                rationale="test",
            )
        else:
            raise unittest.SkipTest("Phase 3 tests require MockOpenShellClient (no STEWARD_OPENSHELL_GRPC_ENDPOINT)")

    def test_execute_blocked_without_approval(self) -> None:
        res = self.client.post(
            "/action/authorize",
            json={"proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["decision"], "needs_approval")
        audit = self.client.get(f"/audit/{res.json()['audit_id']}").json()
        gp_id = audit["payload"]["audit"]["governance_proposal_id"]

        ex = self.client.post(
            "/action/execute",
            json={
                "proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id),
            },
        )
        self.assertEqual(ex.status_code, 403)
        self.assertEqual(ex.json()["detail"]["decision"], "needs_approval")

        p = self.client.get(f"/proposals/{gp_id}").json()
        self.assertEqual(p["state"], "approval_pending")

    def test_approval_crud_and_execute_with_resume(self) -> None:
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        self.assertEqual(auth.status_code, 200)
        gp_id = self.client.get(f"/audit/{auth.json()['audit_id']}").json()["payload"]["audit"][
            "governance_proposal_id"
        ]

        ar = self.client.post("/approval-requests", json={"governance_proposal_id": gp_id})
        self.assertEqual(ar.status_code, 200)
        ar_id = ar.json()["id"]
        self.assertEqual(ar.json()["state"], "requested")

        g = self.client.get(f"/approval-requests/{ar_id}")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["id"], ar_id)

        d = self.client.post(
            f"/approval-requests/{ar_id}/decision",
            json={"decision": "approved", "decided_by": "operator-1"},
        )
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.json()["state"], "approved")

        proposal = _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)
        proposal["context"] = {
            "steward_resume_proposal_id": gp_id,
            "approval_request_id": ar_id,
        }
        ex = self.client.post("/action/execute", json={"proposal": proposal})
        self.assertEqual(ex.status_code, 200, msg=ex.text)
        final = self.client.get(f"/proposals/{gp_id}").json()
        self.assertIn(final["state"], ("executed", "execution_failed"))

    def test_rejected_approval_blocks_execute(self) -> None:
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        gp_id = self.client.get(f"/audit/{auth.json()['audit_id']}").json()["payload"]["audit"][
            "governance_proposal_id"
        ]
        ar_id = self.client.post("/approval-requests", json={"governance_proposal_id": gp_id}).json()["id"]
        self.client.post(f"/approval-requests/{ar_id}/decision", json={"decision": "rejected"})

        proposal = _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)
        proposal["context"] = {"steward_resume_proposal_id": gp_id, "approval_request_id": ar_id}
        ex = self.client.post("/action/execute", json={"proposal": proposal})
        self.assertEqual(ex.status_code, 403)
        self.assertEqual(ex.json()["detail"]["decision"], "needs_approval")
        denied = self.client.get(f"/proposals/{gp_id}").json()
        self.assertEqual(denied["state"], "denied")

    def test_expired_approval_request_blocks_execute(self) -> None:
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        gp_id = self.client.get(f"/audit/{auth.json()['audit_id']}").json()["payload"]["audit"][
            "governance_proposal_id"
        ]
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        ar = self.client.post(
            "/approval-requests",
            json={"governance_proposal_id": gp_id, "expires_at": past.isoformat()},
        )
        self.assertEqual(ar.status_code, 200)
        self.assertEqual(ar.json()["state"], "expired")

        proposal = _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)
        proposal["context"] = {
            "steward_resume_proposal_id": gp_id,
            "approval_request_id": ar.json()["id"],
        }
        ex = self.client.post("/action/execute", json={"proposal": proposal})
        self.assertEqual(ex.status_code, 403)

    def test_audit_top_level_matches_payload_governance_proposal_id(self) -> None:
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        audit = self.client.get(f"/audit/{auth.json()['audit_id']}").json()
        nested = audit["payload"]["audit"]["governance_proposal_id"]
        self.assertEqual(audit.get("governance_proposal_id"), nested)

    def test_create_approval_using_decision_record_id(self) -> None:
        """Some clients paste decision_record_id; resolve via DecisionRecord.governance_proposal_id."""
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        audit = self.client.get(f"/audit/{auth.json()['audit_id']}").json()
        dr_id = audit["decision_record_id"]
        gp_id = audit["governance_proposal_id"]
        self.assertIsNotNone(dr_id)
        ar = self.client.post("/approval-requests", json={"governance_proposal_id": dr_id})
        self.assertEqual(ar.status_code, 200, msg=ar.text)
        self.assertEqual(ar.json()["governance_proposal_id"], gp_id)

    def test_create_approval_using_content_proposal_id(self) -> None:
        """Stable content hash (payload.audit.proposal_id) is not the storage id but must resolve."""
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        audit = self.client.get(f"/audit/{auth.json()['audit_id']}").json()
        content_pid = audit["payload"]["audit"]["proposal_id"]
        gp_id = audit["governance_proposal_id"]
        ar = self.client.post("/approval-requests", json={"governance_proposal_id": content_pid})
        self.assertEqual(ar.status_code, 200, msg=ar.text)
        self.assertEqual(ar.json()["governance_proposal_id"], gp_id)

    def test_post_proposals_evaluate_then_approval_request(self) -> None:
        prop = _needs_approval_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)
        pr = self.client.post(
            "/proposals",
            json={"proposal": prop, "evaluate": True},
        )
        self.assertEqual(pr.status_code, 200, msg=pr.text)
        self.assertEqual(pr.json()["state"], "approval_pending")
        gp_storage_id = pr.json()["id"]
        ar = self.client.post("/approval-requests", json={"governance_proposal_id": gp_storage_id})
        self.assertEqual(ar.status_code, 200, msg=ar.text)
        self.assertEqual(ar.json()["governance_proposal_id"], gp_storage_id)


if __name__ == "__main__":
    unittest.main()

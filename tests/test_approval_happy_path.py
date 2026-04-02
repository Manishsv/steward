"""
End-to-end approval happy path: authorize → approval-request → decision → resumed execute.

Covers compatibility wrappers (/action/*) with persisted GovernanceProposal + ApprovalRequest underneath.
"""

from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

import steward_service.main as main_mod
from steward_service.main import app
from steward_service.openshell_client import MockOpenShellClient


def _agent_approve_proposal(*, sandbox: str, chunk_id: str) -> dict:
    return {
        "action": "openshell.draft_policy.approve",
        "purpose": "happy path test",
        "role": "agent",
        "parameters": {"sandbox_name": sandbox, "chunk_id": chunk_id},
    }


class TestApprovalHappyPath(unittest.TestCase):
    def setUp(self) -> None:
        if os.environ.get("STEWARD_OPENSHELL_GRPC_ENDPOINT", "").strip():
            raise unittest.SkipTest("requires in-process MockOpenShellClient (unset STEWARD_OPENSHELL_GRPC_ENDPOINT)")
        self.client = TestClient(app)
        if not isinstance(main_mod._openshell, MockOpenShellClient):
            raise unittest.SkipTest("MockOpenShellClient required")
        self._sandbox = f"s_happy_{id(self)}"
        self._chunk_id = main_mod._openshell.seed_pending_chunk(
            sandbox_name=self._sandbox,
            rule_name="r1",
            proposed_rule={"name": "r1", "endpoints": [], "binaries": []},
            rationale="test",
        )

    def test_authorize_create_approval_grant_resume_execute_succeeds(self) -> None:
        """Full chain with storage UUIDs; governance allow + runtime success reflected in records."""
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _agent_approve_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        self.assertEqual(auth.status_code, 200)
        self.assertEqual(auth.json()["decision"], "needs_approval")
        audit = self.client.get(f"/audit/{auth.json()['audit_id']}").json()
        gp_id = audit["governance_proposal_id"]
        dr_id_auth = audit["decision_record_id"]
        self.assertIsNotNone(gp_id)
        self.assertIsNotNone(dr_id_auth)
        hints = audit.get("operator_hints") or {}
        self.assertIn("nemoclaw_approval_complete", hints)
        self.assertIn(auth.json()["audit_id"], hints["nemoclaw_approval_complete"])

        ar = self.client.post("/approval-requests", json={"governance_proposal_id": gp_id})
        self.assertEqual(ar.status_code, 200)
        ar_id = ar.json()["id"]

        dec = self.client.post(
            f"/approval-requests/{ar_id}/decision",
            json={"decision": "approved", "decided_by": "operator"},
        )
        self.assertEqual(dec.status_code, 200)

        prop = _agent_approve_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)
        prop["context"] = {
            "steward_resume_proposal_id": gp_id,
            "approval_request_id": ar_id,
        }
        ex = self.client.post("/action/execute", json={"proposal": prop})
        self.assertEqual(ex.status_code, 200, msg=ex.text)
        exec_audit = self.client.get(f"/audit/{ex.json()['audit_id']}").json()
        er_id = exec_audit["execution_record_id"]
        dr_id_exec = exec_audit["decision_record_id"]
        self.assertIsNotNone(er_id)
        self.assertIsNotNone(dr_id_exec)

        dr = self.client.get(f"/decision-records/{dr_id_exec}").json()
        self.assertEqual(dr["decision"], "allow")
        er = self.client.get(f"/execution-records/{er_id}").json()
        self.assertTrue(er["governance_decision_was_allow"])
        self.assertTrue(er["ok"])

        gp_final = self.client.get(f"/proposals/{gp_id}").json()
        self.assertEqual(gp_final["state"], "executed")

    def test_execute_blocked_resume_without_approval_request_id(self) -> None:
        """Resume alone does not bypass needs_approval without a valid approval_request_id."""
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _agent_approve_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        gp_id = self.client.get(f"/audit/{auth.json()['audit_id']}").json()["governance_proposal_id"]
        prop = _agent_approve_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)
        prop["context"] = {"steward_resume_proposal_id": gp_id}
        ex = self.client.post("/action/execute", json={"proposal": prop})
        self.assertEqual(ex.status_code, 403)
        self.assertEqual(ex.json()["detail"]["decision"], "needs_approval")

    def test_resume_execute_accepts_content_hash_steward_resume(self) -> None:
        """steward_resume_proposal_id may use stable content proposal_id (same as approval-requests)."""
        auth = self.client.post(
            "/action/authorize",
            json={"proposal": _agent_approve_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)},
        )
        audit = self.client.get(f"/audit/{auth.json()['audit_id']}").json()
        gp_storage = audit["governance_proposal_id"]
        content_pid = audit["payload"]["audit"]["proposal_id"]

        ar_id = self.client.post("/approval-requests", json={"governance_proposal_id": gp_storage}).json()["id"]
        self.client.post(
            f"/approval-requests/{ar_id}/decision",
            json={"decision": "approved", "decided_by": "op"},
        )

        prop = _agent_approve_proposal(sandbox=self._sandbox, chunk_id=self._chunk_id)
        prop["context"] = {
            "steward_resume_proposal_id": content_pid,
            "approval_request_id": ar_id,
        }
        ex = self.client.post("/action/execute", json={"proposal": prop})
        self.assertEqual(ex.status_code, 200, msg=ex.text)


if __name__ == "__main__":
    unittest.main()

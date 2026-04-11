"""SQLite durability: governance rows survive module reload (process restart simulation)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import steward_service.main as main_mod
from steward_service.openshell_client import MockOpenShellClient
from steward_service.storage.factory import build_storage_bundle_for_tests_sqlite


class TestSqliteStoresRoundtrip(unittest.TestCase):
    def test_put_get_roundtrip(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            b = build_storage_bundle_for_tests_sqlite(path)
            from steward_service.domain import DecisionRecord, Decision as D

            dr = DecisionRecord(
                id="test-dr-1",
                created_at=b.decisions.now(),
                governance_proposal_id="gp1",
                content_proposal_id="cp1",
                decision=D.allow,
                rationale="t",
                plan_snapshot={},
            )
            b.decisions.put(dr)
            got = b.decisions.get("test-dr-1")
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got.governance_proposal_id, "gp1")
        finally:
            os.unlink(path)


class TestSqliteDurabilityAcrossReload(unittest.TestCase):
    def setUp(self) -> None:
        if os.environ.get("STEWARD_OPENSHELL_GRPC_ENDPOINT", "").strip():
            raise unittest.SkipTest("reload test needs MockOpenShellClient")

    def test_approval_and_proposal_survive_reload(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            os.environ["STEWARD_STORAGE_BACKEND"] = "sqlite"
            os.environ["STEWARD_SQLITE_PATH"] = path
            importlib.reload(main_mod)
            if not isinstance(main_mod._openshell, MockOpenShellClient):
                raise unittest.SkipTest("MockOpenShellClient required")

            client = TestClient(main_mod.app)
            sandbox = f"s_dur_{id(self)}"
            chunk_id = main_mod._openshell.seed_pending_chunk(
                sandbox_name=sandbox,
                rule_name="r1",
                proposed_rule={"name": "r1", "endpoints": [], "binaries": []},
                rationale="t",
            )
            auth = client.post(
                "/action/authorize",
                json={
                    "proposal": {
                        "action": "openshell.draft_policy.approve",
                        "purpose": "durability",
                        "role": "agent",
                        "parameters": {"sandbox_name": sandbox, "chunk_id": chunk_id},
                    },
                },
            )
            self.assertEqual(auth.status_code, 200)
            self.assertEqual(auth.json()["decision"], "needs_approval")
            audit = client.get(f"/audit/{auth.json()['audit_id']}").json()
            gp_id = audit["governance_proposal_id"]
            dr_id = audit["decision_record_id"]
            self.assertIsNotNone(gp_id)
            self.assertIsNotNone(dr_id)

            ar = client.post("/approval-requests", json={"governance_proposal_id": gp_id})
            self.assertEqual(ar.status_code, 200)
            ar_id = ar.json()["id"]
            self.assertEqual(ar.json()["decision_record_id"], dr_id)

            importlib.reload(main_mod)
            self.assertEqual(main_mod._stores.sqlite_path, path)

            client2 = TestClient(main_mod.app)
            g = client2.get(f"/proposals/{gp_id}")
            self.assertEqual(g.status_code, 200, g.text)
            self.assertEqual(g.json()["state"], "approval_pending")

            d = client2.get(f"/decision-records/{dr_id}")
            self.assertEqual(d.status_code, 200)
            self.assertEqual(d.json()["governance_proposal_id"], gp_id)

            a = client2.get(f"/approval-requests/{ar_id}")
            self.assertEqual(a.status_code, 200)
            self.assertEqual(a.json()["governance_proposal_id"], gp_id)
            self.assertEqual(a.json()["decision_record_id"], dr_id)
        finally:
            os.environ.pop("STEWARD_STORAGE_BACKEND", None)
            os.environ.pop("STEWARD_SQLITE_PATH", None)
            importlib.reload(main_mod)
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

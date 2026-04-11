"""Registry catalog: PolicyDefinition and RoleDefinition GET APIs (seeded; future persistent store)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from steward_service.main import app


class TestPolicyDefinitionRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_seed_policy(self) -> None:
        r = self.client.get("/policies/policy.steward.draft_policy_v1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "policy.steward.draft_policy_v1")
        self.assertIn("version", r.json())

    def test_unknown_policy_404(self) -> None:
        r = self.client.get("/policies/policy.does.not.exist")
        self.assertEqual(r.status_code, 404)

    def test_institution_expenditure_policy_metadata(self) -> None:
        r = self.client.get("/policies/institution.expenditure.v1")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], "institution.expenditure.v1")
        self.assertEqual(body["version"], "2")
        self.assertIn("JSON", body["description"])

    def test_technical_draft_policy_policy_metadata(self) -> None:
        r = self.client.get("/policies/policy.technical.draft_policy.v1")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], "policy.technical.draft_policy.v1")
        self.assertEqual(body["version"], "1")
        self.assertIn("JSON", body["description"])

    def test_effective_policy_merge_metadata(self) -> None:
        r = self.client.get("/policies/policy.steward.effective_policy_merge.v1")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], "policy.steward.effective_policy_merge.v1")
        self.assertEqual(body["version"], "1")
        self.assertIn("JSON", body["description"])


class TestRoleDefinitionRegistryCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_operator_from_registry_catalog(self) -> None:
        r = self.client.get("/roles/operator")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "operator")
        self.assertIn("display_name", r.json())
        self.assertIn("version", r.json())


class TestCapabilityDefinitionRegistryCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_seed_capability_from_registry_catalog(self) -> None:
        r = self.client.get("/capabilities/cap.openshell.draft_policy.read")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "cap.openshell.draft_policy.read")
        self.assertIn("resource_family", r.json())
        self.assertIn("version", r.json())

    def test_unknown_capability_404(self) -> None:
        r = self.client.get("/capabilities/cap.does.not.exist")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()

"""Declarative expenditure rules (JSON) + engine."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from steward_service.institution_engine import evaluate_expenditure
from steward_service.institution_rules import load_expenditure_ruleset


class _P(BaseModel):
    parameters: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    role: Optional[str] = None


class TestInstitutionEngine(unittest.TestCase):
    def test_bundled_json_junior_allow(self) -> None:
        rs = load_expenditure_ruleset()
        o, r, rid, m = evaluate_expenditure(
            _P(
                role="junior_engineer",
                parameters={"amount_rs": 10000},
                context={"procedure": "expense_v1", "procedure_state": "request_submitted"},
            ),
            rs,
        )
        self.assertEqual(o, "allow")
        self.assertIn("junior", r.lower())
        self.assertEqual(rid, "rule.expenditure.junior_threshold_v1")

    def test_custom_json_overrides_threshold(self) -> None:
        raw = {
            "domain": "institution.expenditure.v1",
            "version": "99",
            "policy_id": "institution.expenditure.v1",
            "display_name": "Test",
            "description": "t",
            "required_facts": [
                {
                    "id": "amount_rs",
                    "source": "parameters",
                    "key": "amount_rs",
                    "types": ["number"],
                    "defer_code": "amount_rs",
                },
                {
                    "id": "procedure",
                    "source": "context",
                    "key": "procedure",
                    "types": ["string"],
                    "defer_code": "procedure",
                },
                {
                    "id": "procedure_state",
                    "source": "context",
                    "key": "procedure_state",
                    "types": ["string"],
                    "defer_code": "procedure_state",
                },
            ],
            "defer_rule_id": "rule.x",
            "defer_rationale_template": "Missing: {missing_list}",
            "role_rules": [
                {
                    "match_roles": ["junior_engineer"],
                    "priority": 30,
                    "kind": "threshold_escalate_above",
                    "max_direct_amount_rs": 999,
                    "rule_id": "rule.custom",
                    "allow_rationale": "ok",
                    "above_rationale": "too high",
                }
            ],
            "fallback": {
                "outcome": "needs_approval",
                "rule_id": "fb",
                "rationale_template": "role {role}",
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
            p = Path(f.name)
        try:
            rs = load_expenditure_ruleset(p)
            o, _, rid, _ = evaluate_expenditure(
                _P(
                    role="junior_engineer",
                    parameters={"amount_rs": 500},
                    context={"procedure": "x", "procedure_state": "y"},
                ),
                rs,
            )
            self.assertEqual(o, "allow")
            self.assertEqual(rid, "rule.custom")
        finally:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

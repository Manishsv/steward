"""Load declarative institutional expenditure rules (JSON source of truth)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from .domain import PolicyDefinition
from .registry_catalog import POLICIES


@dataclass(frozen=True)
class RequiredFactSpec:
    id: str
    source: Literal["parameters", "context"]
    key: str
    types: List[str]
    defer_code: str


@dataclass(frozen=True)
class RoleRuleSpec:
    match_roles: List[str]
    priority: int
    kind: Literal["threshold_escalate_above", "threshold_needs_approval_above"]
    max_direct_amount_rs: float
    rule_id: str
    allow_rationale: str
    above_rationale: str


@dataclass(frozen=True)
class FallbackSpec:
    outcome: Literal["needs_approval"]
    rule_id: str
    rationale_template: str


@dataclass(frozen=True)
class ExpenditureRuleset:
    domain: str
    version: str
    policy_id: str
    display_name: str
    description: str
    required_facts: List[RequiredFactSpec]
    defer_rule_id: str
    defer_rationale_template: str
    role_rules: List[RoleRuleSpec]
    fallback: FallbackSpec


def _load_raw(path: Optional[Path] = None) -> Dict[str, Any]:
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    default = Path(__file__).resolve().parent / "data" / "institution_expenditure_rules.json"
    return json.loads(default.read_text(encoding="utf-8"))


def load_expenditure_ruleset(path: Optional[Path] = None) -> ExpenditureRuleset:
    raw = _load_raw(path)
    facts = [
        RequiredFactSpec(
            id=f["id"],
            source=f["source"],
            key=f["key"],
            types=list(f["types"]),
            defer_code=f["defer_code"],
        )
        for f in raw["required_facts"]
    ]
    rules = [
        RoleRuleSpec(
            match_roles=list(r["match_roles"]),
            priority=int(r["priority"]),
            kind=r["kind"],
            max_direct_amount_rs=float(r["max_direct_amount_rs"]),
            rule_id=r["rule_id"],
            allow_rationale=r["allow_rationale"],
            above_rationale=r["above_rationale"],
        )
        for r in raw["role_rules"]
    ]
    fb = raw["fallback"]
    return ExpenditureRuleset(
        domain=raw["domain"],
        version=str(raw["version"]),
        policy_id=raw["policy_id"],
        display_name=raw["display_name"],
        description=raw["description"],
        required_facts=facts,
        defer_rule_id=raw["defer_rule_id"],
        defer_rationale_template=raw["defer_rationale_template"],
        role_rules=sorted(rules, key=lambda x: -x.priority),
        fallback=FallbackSpec(
            outcome=fb["outcome"],
            rule_id=fb["rule_id"],
            rationale_template=fb["rationale_template"],
        ),
    )


def register_expenditure_policy_metadata(ruleset: ExpenditureRuleset) -> None:
    """Expose policy metadata via GET /policies/{id} (authoritative version from JSON)."""
    POLICIES[ruleset.policy_id] = PolicyDefinition(
        id=ruleset.policy_id,
        display_name=ruleset.display_name,
        description=f"{ruleset.description} (rules v{ruleset.version}; bundled JSON)",
        version=ruleset.version,
    )

"""Evaluate institutional expenditure proposals using declarative ruleset."""

from __future__ import annotations

from typing import Any, List, Tuple

from pydantic import BaseModel

from .institution_rules import ExpenditureRuleset


def _fact_value(
    spec_source: str, key: str, parameters: dict, context: dict
) -> Any:
    if spec_source == "parameters":
        return parameters.get(key)
    return context.get(key)


def _is_present(spec_types: List[str], value: Any) -> bool:
    if value is None:
        return False
    for t in spec_types:
        if t == "number":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
        elif t == "string":
            if isinstance(value, str) and value.strip():
                return True
    return False


def evaluate_expenditure(
    req: BaseModel,
    ruleset: ExpenditureRuleset,
) -> Tuple[str, str, str, List[str]]:
    """
    req: ActionProposal-like with .parameters, .context, .role
    Returns: (outcome, rationale, rule_id, missing_fact_codes).
    outcome is allow | needs_approval | escalate | defer.
    """
    params = dict(req.parameters)
    ctx = dict(req.context)
    missing: List[str] = []
    for spec in ruleset.required_facts:
        val = _fact_value(spec.source, spec.key, params, ctx)
        if not _is_present(spec.types, val):
            missing.append(spec.defer_code)
    if missing:
        return (
            "defer",
            ruleset.defer_rationale_template.format(missing_list=", ".join(missing)),
            ruleset.defer_rule_id,
            missing,
        )

    amount = params.get("amount_rs")
    assert isinstance(amount, (int, float))
    amt = float(amount)
    role = (req.role or "").strip().lower()

    for rule in ruleset.role_rules:
        if role not in {r.lower() for r in rule.match_roles}:
            continue
        if rule.kind == "threshold_escalate_above":
            if amt <= rule.max_direct_amount_rs:
                return (
                    "allow",
                    rule.allow_rationale,
                    rule.rule_id,
                    [],
                )
            return (
                "escalate",
                rule.above_rationale,
                rule.rule_id,
                [],
            )
        if rule.kind == "threshold_needs_approval_above":
            if amt <= rule.max_direct_amount_rs:
                return (
                    "allow",
                    rule.allow_rationale,
                    rule.rule_id,
                    [],
                )
            return (
                "needs_approval",
                rule.above_rationale,
                rule.rule_id,
                [],
            )

    fb = ruleset.fallback
    return (
        "needs_approval",
        fb.rationale_template.format(role=role or "unknown"),
        fb.rule_id,
        [],
    )

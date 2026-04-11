"""
Authoritative policy-layer definitions for EffectivePolicy merge (autonomy ceiling).

Bundled JSON: steward_service/data/effective_policy_merge.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .domain import PolicyDefinition, RiskTier
from .registry_catalog import POLICIES


@dataclass(frozen=True)
class RoleCeilingRule:
    match_roles: Tuple[str, ...]
    autonomy_ceiling: RiskTier
    priority: int


@dataclass(frozen=True)
class PolicyMergeLayer:
    version: str
    policy_id: str
    display_name: str
    description: str
    constitution_version: str
    constitution_ceiling: RiskTier
    role_ceilings: Tuple[RoleCeilingRule, ...]
    local_context_key: str
    local_autonomy_ceiling_field: str
    local_ignore_invalid_tier: bool
    merge_clamp_role_to_constitution: bool
    merge_clamp_local_to_constitution: bool
    effective_operation: str


def _risk(s: str) -> RiskTier:
    return RiskTier(s.strip().lower())


def _bundle_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "effective_policy_merge.json"


def load_policy_merge_layer(path: Optional[Path] = None) -> PolicyMergeLayer:
    p = path or _bundle_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    const = raw["constitution"]
    local = raw["local_policy"]
    merge = raw["merge"]
    if merge.get("effective_operation") != "min_index":
        raise ValueError("merge.effective_operation must be 'min_index' for this Steward release")
    if not merge.get("clamp_role_to_constitution", False):
        raise ValueError("merge.clamp_role_to_constitution must be true")
    if not merge.get("clamp_local_to_constitution", False):
        raise ValueError("merge.clamp_local_to_constitution must be true")
    if not merge.get("missing_local_uses_constitution_index", False):
        raise ValueError("merge.missing_local_uses_constitution_index must be true (local absent => constitution index term)")

    rules_raw = list(raw["role_ceilings"])
    has_wildcard = any(
        any(m.strip().lower() == "*" for m in rr.get("match_roles", [])) for rr in rules_raw
    )
    if not has_wildcard:
        raise ValueError("role_ceilings must include a rule with match_roles containing '*'")

    rules = tuple(
        RoleCeilingRule(
            match_roles=tuple(str(x) for x in rr["match_roles"]),
            autonomy_ceiling=_risk(rr["autonomy_ceiling"]),
            priority=int(rr.get("priority", 0)),
        )
        for rr in rules_raw
    )

    return PolicyMergeLayer(
        version=str(raw["version"]),
        policy_id=str(raw["policy_id"]),
        display_name=str(raw["display_name"]),
        description=str(raw["description"]),
        constitution_version=str(const["version"]),
        constitution_ceiling=_risk(const["autonomy_ceiling"]),
        role_ceilings=rules,
        local_context_key=str(local["context_key"]),
        local_autonomy_ceiling_field=str(local["autonomy_ceiling_field"]),
        local_ignore_invalid_tier=bool(local.get("ignore_invalid_tier", True)),
        merge_clamp_role_to_constitution=bool(merge["clamp_role_to_constitution"]),
        merge_clamp_local_to_constitution=bool(merge["clamp_local_to_constitution"]),
        effective_operation=str(merge["effective_operation"]),
    )


def register_effective_policy_merge_metadata(layer: PolicyMergeLayer) -> None:
    POLICIES[layer.policy_id] = PolicyDefinition(
        id=layer.policy_id,
        display_name=layer.display_name,
        description=f"{layer.description} (definitions v{layer.version}; bundled JSON)",
        version=layer.version,
    )


def role_autonomy_ceiling_for_layer(
    role: Optional[str], layer: PolicyMergeLayer
) -> Tuple[RiskTier, str]:
    """Return (raw role ceiling tier, normalized role name for diagnostics)."""
    r = (role or "").strip().lower() or "anonymous"
    specific = [
        rule
        for rule in layer.role_ceilings
        if any(m.strip().lower() != "*" for m in rule.match_roles)
        and r in {m.strip().lower() for m in rule.match_roles if m.strip().lower() != "*"}
    ]
    if specific:
        best = max(specific, key=lambda x: x.priority)
        return best.autonomy_ceiling, r
    wild = [rule for rule in layer.role_ceilings if any(m.strip().lower() == "*" for m in rule.match_roles)]
    if not wild:
        return RiskTier.medium, r
    best = max(wild, key=lambda x: x.priority)
    return best.autonomy_ceiling, r


_MERGE_LAYER_SINGLETON: Optional[PolicyMergeLayer] = None


def get_policy_merge_layer() -> PolicyMergeLayer:
    global _MERGE_LAYER_SINGLETON
    if _MERGE_LAYER_SINGLETON is None:
        _MERGE_LAYER_SINGLETON = load_policy_merge_layer()
        register_effective_policy_merge_metadata(_MERGE_LAYER_SINGLETON)
    return _MERGE_LAYER_SINGLETON


def reset_policy_merge_layer_for_tests() -> None:
    global _MERGE_LAYER_SINGLETON
    _MERGE_LAYER_SINGLETON = None

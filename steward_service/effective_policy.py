from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .domain import Proposal, RiskTier
from .policy_merge_layer import PolicyMergeLayer, get_policy_merge_layer, role_autonomy_ceiling_for_layer


def _tier_index(tier: RiskTier) -> int:
    return {RiskTier.low: 0, RiskTier.medium: 1, RiskTier.high: 2}[tier]


def _tier_from_index(idx: int) -> RiskTier:
    for t, i in {RiskTier.low: 0, RiskTier.medium: 1, RiskTier.high: 2}.items():
        if i == idx:
            return t
    return RiskTier.low


@dataclass(frozen=True)
class ConstitutionPolicy:
    """Immutable upper bound on autonomy; cannot be widened by local or role."""

    version: str
    autonomy_ceiling: RiskTier


@dataclass(frozen=True)
class RolePolicy:
    """Authority hints from role; cannot exceed constitution."""

    role_name: str
    autonomy_ceiling: RiskTier


@dataclass(frozen=True)
class LocalPolicy:
    """Caller-supplied narrowing only (e.g. from workspace or channel)."""

    autonomy_ceiling: Optional[RiskTier] = None


@dataclass(frozen=True)
class EffectivePolicy:
    """Merged policy used for governance decisioning."""

    autonomy_ceiling: RiskTier
    constitution_version: str
    sources: Dict[str, str]


def default_constitution() -> ConstitutionPolicy:
    """Constitution slice from bundled policy merge definitions."""
    ml = get_policy_merge_layer()
    return ConstitutionPolicy(version=ml.constitution_version, autonomy_ceiling=ml.constitution_ceiling)


def __getattr__(name: str) -> Any:
    """Lazy `DEFAULT_CONSTITUTION` from bundled JSON (avoids stale import binding)."""
    if name == "DEFAULT_CONSTITUTION":
        return default_constitution()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def ensure_effective_policy_merge_warmed() -> None:
    """Load merge layer and register policy metadata (call at app startup)."""
    get_policy_merge_layer()


def _local_from_context(context: Dict[str, Any], layer: PolicyMergeLayer) -> LocalPolicy:
    raw = context.get(layer.local_context_key)
    if not isinstance(raw, dict):
        return LocalPolicy()
    ac = raw.get(layer.local_autonomy_ceiling_field)
    if not isinstance(ac, str) or not ac.strip():
        return LocalPolicy()
    try:
        return LocalPolicy(autonomy_ceiling=RiskTier(ac.strip().lower()))
    except ValueError:
        return LocalPolicy() if layer.local_ignore_invalid_tier else LocalPolicy()


def _role_policy(role: Optional[str], layer: PolicyMergeLayer) -> RolePolicy:
    tier, name = role_autonomy_ceiling_for_layer(role, layer)
    return RolePolicy(role_name=name, autonomy_ceiling=tier)


def resolve_effective_policy(
    proposal: Proposal, *, policy_merge_layer: Optional[PolicyMergeLayer] = None
) -> EffectivePolicy:
    """
    Precedence (from bundled policy merge layer; see data/effective_policy_merge.json):
    - Constitution caps maximum permissiveness (autonomy ceiling cannot be raised above it).
    - Role cannot exceed constitution (clamp role ceiling to constitution).
    - Local may only narrow (stricter = lower autonomy ceiling rank).
    - Effective ceiling = min(constitution_index, clamped_role_index, clamped_local_contribution).
    """
    layer = policy_merge_layer or get_policy_merge_layer()

    const = ConstitutionPolicy(version=layer.constitution_version, autonomy_ceiling=layer.constitution_ceiling)
    c_idx = _tier_index(const.autonomy_ceiling)

    role = _role_policy(proposal.role, layer)
    role_idx = _tier_index(role.autonomy_ceiling)
    if layer.merge_clamp_role_to_constitution:
        role_idx = min(role_idx, c_idx)

    local = _local_from_context(dict(proposal.context), layer)
    if local.autonomy_ceiling is None:
        local_idx = c_idx
    else:
        local_idx = _tier_index(local.autonomy_ceiling)
        if layer.merge_clamp_local_to_constitution:
            local_idx = min(local_idx, c_idx)

    if layer.effective_operation != "min_index":
        raise RuntimeError("unsupported effective_operation")

    eff_idx = min(c_idx, role_idx, local_idx)
    return EffectivePolicy(
        autonomy_ceiling=_tier_from_index(eff_idx),
        constitution_version=const.version,
        sources={
            "constitution": const.version,
            "role": role.role_name,
            "local_autonomy_ceiling": (
                local.autonomy_ceiling.value if local.autonomy_ceiling is not None else ""
            ),
            "policy_merge_layer_version": layer.version,
        },
    )


def risk_exceeds_autonomy_ceiling(tier: RiskTier, ceiling: RiskTier) -> bool:
    return _tier_index(tier) > _tier_index(ceiling)

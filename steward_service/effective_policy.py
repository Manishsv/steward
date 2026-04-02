from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .domain import Proposal, RiskTier


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


DEFAULT_CONSTITUTION = ConstitutionPolicy(version="v0", autonomy_ceiling=RiskTier.medium)


def _local_from_context(context: Dict[str, Any]) -> LocalPolicy:
    raw = context.get("steward_local_policy")
    if not isinstance(raw, dict):
        return LocalPolicy()
    ac = raw.get("autonomy_ceiling")
    if not isinstance(ac, str) or not ac.strip():
        return LocalPolicy()
    try:
        return LocalPolicy(autonomy_ceiling=RiskTier(ac.strip().lower()))
    except ValueError:
        return LocalPolicy()


def _role_policy(role: Optional[str]) -> RolePolicy:
    r = (role or "").strip().lower()
    if r == "operator":
        return RolePolicy(role_name=r or "anonymous", autonomy_ceiling=RiskTier.high)
    return RolePolicy(role_name=r or "anonymous", autonomy_ceiling=RiskTier.medium)


def resolve_effective_policy(proposal: Proposal) -> EffectivePolicy:
    """
    Precedence:
    - Constitution caps maximum permissiveness (autonomy ceiling cannot be raised above it).
    - Role cannot exceed constitution (clamp role ceiling to constitution).
    - Local may only narrow (stricter = lower autonomy ceiling rank).
    """
    const = DEFAULT_CONSTITUTION
    c_idx = _tier_index(const.autonomy_ceiling)

    role = _role_policy(proposal.role)
    role_idx = min(_tier_index(role.autonomy_ceiling), c_idx)

    local = _local_from_context(dict(proposal.context))
    if local.autonomy_ceiling is None:
        local_idx = c_idx
    else:
        local_idx = min(_tier_index(local.autonomy_ceiling), c_idx)

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
        },
    )


def risk_exceeds_autonomy_ceiling(tier: RiskTier, ceiling: RiskTier) -> bool:
    return _tier_index(tier) > _tier_index(ceiling)

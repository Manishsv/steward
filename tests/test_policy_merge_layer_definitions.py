"""Policy merge layer: bundled JSON drives constitution, role ceilings, and merge outcome."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from steward_service.domain import ActionType, Proposal, RiskTier
from steward_service.effective_policy import resolve_effective_policy
from steward_service.policy_merge_layer import PolicyMergeLayer, load_policy_merge_layer


def _bundle_path() -> Path:
    return Path(__file__).resolve().parent.parent / "steward_service" / "data" / "effective_policy_merge.json"


def _layer_from_overrides(
    *,
    constitution: Optional[Dict[str, Any]] = None,
    role_ceilings: Optional[List[Dict[str, Any]]] = None,
) -> PolicyMergeLayer:
    base = json.loads(_bundle_path().read_text(encoding="utf-8"))
    if constitution is not None:
        base["constitution"] = {**base["constitution"], **constitution}
    if role_ceilings is not None:
        base["role_ceilings"] = role_ceilings
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "merge.json"
        path.write_text(json.dumps(base), encoding="utf-8")
        return load_policy_merge_layer(path)


class TestPolicyMergeLayerDeclarative(unittest.TestCase):
    def test_constitution_from_json_caps_everyone_low(self) -> None:
        layer = _layer_from_overrides(constitution={"autonomy_ceiling": "low"})
        p_op = Proposal(
            proposal_id="a",
            action_type=ActionType.generic,
            action="noop",
            purpose="t",
            role="operator",
            context={},
            parameters={},
        )
        ep = resolve_effective_policy(p_op, policy_merge_layer=layer)
        self.assertEqual(ep.autonomy_ceiling, RiskTier.low)

    def test_operator_vs_non_operator_ceilings_from_json(self) -> None:
        layer = _layer_from_overrides(
            constitution={"autonomy_ceiling": "high"},
            role_ceilings=[
                {"match_roles": ["operator"], "autonomy_ceiling": "high", "priority": 100},
                {"match_roles": ["*"], "autonomy_ceiling": "medium", "priority": 0},
            ],
        )
        op = resolve_effective_policy(
            Proposal(
                proposal_id="o",
                action_type=ActionType.generic,
                action="noop",
                purpose="t",
                role="operator",
                context={},
                parameters={},
            ),
            policy_merge_layer=layer,
        )
        ag = resolve_effective_policy(
            Proposal(
                proposal_id="g",
                action_type=ActionType.generic,
                action="noop",
                purpose="t",
                role="agent",
                context={},
                parameters={},
            ),
            policy_merge_layer=layer,
        )
        self.assertEqual(op.autonomy_ceiling, RiskTier.high)
        self.assertEqual(ag.autonomy_ceiling, RiskTier.medium)

    def test_local_narrow_still_works_with_layer_override(self) -> None:
        layer = _layer_from_overrides()
        ep = resolve_effective_policy(
            Proposal(
                proposal_id="x",
                action_type=ActionType.generic,
                action="noop",
                purpose="t",
                role="operator",
                context={"steward_local_policy": {"autonomy_ceiling": "low"}},
                parameters={},
            ),
            policy_merge_layer=layer,
        )
        self.assertEqual(ep.autonomy_ceiling, RiskTier.low)

    def test_local_cannot_broaden_past_constitution_from_definitions(self) -> None:
        layer = _layer_from_overrides()
        ep = resolve_effective_policy(
            Proposal(
                proposal_id="x",
                action_type=ActionType.generic,
                action="noop",
                purpose="t",
                role="operator",
                context={"steward_local_policy": {"autonomy_ceiling": "high"}},
                parameters={},
            ),
            policy_merge_layer=layer,
        )
        self.assertEqual(ep.autonomy_ceiling, layer.constitution_ceiling)


if __name__ == "__main__":
    unittest.main()

import unittest

from steward_service.governance_context import GovernanceContext
from steward_service.identity import Identity


class TestGovernanceContext(unittest.TestCase):
    def test_empty_context(self) -> None:
        g = GovernanceContext.from_proposal_context({})
        self.assertIsNone(g.requested_by)
        self.assertIsNone(g.approved_by)
        self.assertIsNone(g.channel)
        self.assertEqual(g.external_refs, [])

    def test_requested_by_string(self) -> None:
        g = GovernanceContext.from_proposal_context({"requested_by": "user:alice", "channel": "tui"})
        self.assertIsNotNone(g.requested_by)
        assert g.requested_by is not None
        self.assertEqual(g.requested_by.kind, "user")
        self.assertEqual(g.requested_by.value, "alice")
        self.assertEqual(g.channel, "tui")

    def test_requested_by_dict(self) -> None:
        g = GovernanceContext.from_proposal_context(
            {"requested_by": {"kind": "service", "value": "openclaw"}}
        )
        self.assertEqual(g.requested_by, Identity(kind="service", value="openclaw"))

    def test_external_refs_list(self) -> None:
        g = GovernanceContext.from_proposal_context({"external_refs": [{"k": 1}]})
        self.assertEqual(g.external_refs, [{"k": 1}])


if __name__ == "__main__":
    unittest.main()

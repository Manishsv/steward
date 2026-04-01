import unittest

from steward_service.main import _execute_user_hint


class TestExecuteUserHint(unittest.TestCase):
    def test_needs_approval_hint(self) -> None:
        hint = _execute_user_hint(
            decision="needs_approval",
            rationale="Approval requirements not satisfied.",
            result={"error": "not_allowed"},
        )
        self.assertIn("Approval is required", hint)

    def test_unsupported_denied_hint(self) -> None:
        hint = _execute_user_hint(
            decision="deny",
            rationale="Unsupported action: no governance policy exists for this action. (family=openshell)",
            result={},
        )
        self.assertIn("unsupported", hint.lower())
        self.assertIn("no governance policy", hint.lower())

    def test_runtime_failure_hint(self) -> None:
        hint = _execute_user_hint(
            decision="allow",
            rationale="Approved by operator.",
            result={"error": "external_call_failed", "message": "socket closed"},
        )
        self.assertIn("OpenShell", hint)
        self.assertIn("execution failed", hint)


if __name__ == "__main__":
    unittest.main()


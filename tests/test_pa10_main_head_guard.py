"""PA-10 revalidation unit tests: no network, providers, or credentials."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.pa10_main_head_guard import (
    API_ROOT, MainHeadChanged, inspect_current_main, require_current_main,
)

SHA = "a" * 40


def protected_main():
    return {"name": "main", "protected": True, "commit": {"sha": SHA}}


class CurrentMainTests(unittest.TestCase):
    def test_exact_protected_main_passes(self):
        self.assertIsNone(require_current_main(protected_main(), SHA))

    def test_unprotected_or_advanced_main_fail_closed(self):
        variations = (
            {"name": "main", "protected": False, "commit": {"sha": SHA}},
            {"name": "main", "protected": None, "commit": {"sha": SHA}},
            {"name": "main", "protected": True, "commit": {"sha": "b" * 40}},
            {"name": "develop", "protected": True, "commit": {"sha": SHA}},
            {"name": "main", "protected": True, "commit": None},
            {"name": "main", "protected": True},
            {},
            [],
            None,
        )
        for branch in variations:
            with self.subTest(branch=branch), self.assertRaises(MainHeadChanged):
                require_current_main(branch, SHA)

    def test_fetch_is_pinned_to_exact_repository_and_branch(self):
        with patch("scripts.pa10_main_head_guard._get_json", return_value=protected_main()) as request:
            self.assertIsNone(inspect_current_main("rumman52/Shuddho", SHA, "token"))
            request.assert_called_once_with(API_ROOT + "/branches/main", "token")

    def test_invalid_identity_or_token_rejected_without_network(self):
        cases = (
            ("other/Shuddho", SHA, "token"),
            ("rumman52/Shuddho", "b", "token"),
            ("rumman52/Shuddho", "../malicious", "token"),
            ("rumman52/Shuddho", SHA, ""),
            ("rumman52/Shuddho", SHA, None),
        )
        with patch("scripts.pa10_main_head_guard._get_json") as request:
            for repo, sha, token in cases:
                with self.subTest(repo=repo, sha=sha, token=token):
                    with self.assertRaises(MainHeadChanged):
                        inspect_current_main(repo, sha, token)
            request.assert_not_called()

    def test_network_errors_do_not_grant_admission(self):
        from scripts.main_protection_audit import GovernanceAuditError
        with patch("scripts.pa10_main_head_guard._get_json", side_effect=GovernanceAuditError("unavailable")):
            with self.assertRaises(GovernanceAuditError):
                inspect_current_main("rumman52/Shuddho", SHA, "token")


if __name__ == "__main__":
    unittest.main()

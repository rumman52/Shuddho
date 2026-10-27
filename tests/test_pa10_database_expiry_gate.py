"""Database lifecycle admission regressions; no Render calls or credentials."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from scripts.pa10_database_expiry_gate import (
    DatabaseExpiryGateError,
    check_database_lifecycle,
)

NOW = datetime(2026, 10, 27, 11, 16, tzinfo=timezone.utc)


class DatabaseExpiryGateTests(unittest.TestCase):
    def test_free_database_with_safe_lifetime_passes(self):
        result = check_database_lifecycle(
            "free", "2026-11-10T11:16:00Z", now=NOW, minimum_remaining_days=7
        )
        self.assertEqual(result["status"], "clear")
        self.assertEqual(result["plan"], "free")
        self.assertEqual(result["remaining_seconds"], 14 * 24 * 60 * 60)

    def test_free_database_inside_safety_window_fails(self):
        for days in (7, 4, 1):
            with self.subTest(days=days), self.assertRaises(DatabaseExpiryGateError):
                check_database_lifecycle(
                    "free",
                    (NOW + timedelta(days=days)).isoformat(),
                    now=NOW,
                    minimum_remaining_days=7,
                )

    def test_expired_database_fails(self):
        with self.assertRaisesRegex(DatabaseExpiryGateError, "already expired"):
            check_database_lifecycle(
                "free", "2026-10-27T11:15:59Z", now=NOW
            )

    def test_free_database_without_expiry_fails_closed(self):
        for value in (None, "", "   "):
            with self.subTest(value=value), self.assertRaisesRegex(
                DatabaseExpiryGateError, "expiry is unavailable"
            ):
                check_database_lifecycle("free", value, now=NOW)

    def test_paid_database_without_expiry_is_allowed(self):
        result = check_database_lifecycle("starter", None, now=NOW)
        self.assertEqual(result["status"], "no_expiry")
        self.assertIsNone(result["expires_at"])

    def test_present_expiry_is_checked_regardless_of_plan_name(self):
        with self.assertRaisesRegex(DatabaseExpiryGateError, "safety window"):
            check_database_lifecycle(
                "starter", "2026-10-30T11:16:00Z", now=NOW
            )

    def test_unknown_or_custom_plan_fails_closed(self):
        for plan, expiry in (
            ("future-free-alias", None),
            ("custom", None),
            ("future-plan", "2026-11-10T11:16:00Z"),
        ):
            with self.subTest(plan=plan, expiry=expiry), self.assertRaisesRegex(
                DatabaseExpiryGateError, "plan"
            ):
                check_database_lifecycle(plan, expiry, now=NOW)

    def test_malformed_or_timezone_naive_expiry_fails_closed(self):
        for value in ("not-a-date", "2026-10-30T11:16:00", "2026-02-30T00:00:00Z"):
            with self.subTest(value=value), self.assertRaises(DatabaseExpiryGateError):
                check_database_lifecycle("free", value, now=NOW)

    def test_missing_plan_and_invalid_safety_window_fail_closed(self):
        with self.assertRaisesRegex(DatabaseExpiryGateError, "plan is missing"):
            check_database_lifecycle("", "2026-11-10T11:16:00Z", now=NOW)
        for days in (0, -1, 366, True, 7.0):
            with self.subTest(days=days), self.assertRaises(DatabaseExpiryGateError):
                check_database_lifecycle(
                    "starter", None, now=NOW, minimum_remaining_days=days
                )

    def test_naive_current_time_fails_closed(self):
        with self.assertRaisesRegex(DatabaseExpiryGateError, "current time"):
            check_database_lifecycle(
                "free", "2026-11-10T11:16:00Z",
                now=datetime(2026, 10, 27, 11, 16),
            )


if __name__ == "__main__":
    unittest.main()

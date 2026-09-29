from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from services.coworker.notification_digests import digest_views


def notice(index: int, **overrides) -> dict:
    at = datetime(2026, 9, 29, 12, tzinfo=timezone.utc) + timedelta(seconds=index)
    return {
        "id": f"{index:08x}-0000-4000-8000-000000000000", "workspace_id": "workspace-a",
        "kind": "personal_suggestion", "title": "Goal review", "message": "পরিকল্পনা পর্যালোচনা করুন।",
        "state": "delivered", "created_at": at.isoformat(), "visible_at": at.isoformat(),
        "read_at": None, "automation_id": None, "occurrence_id": None, **overrides,
    }


class DigestViewsTest(unittest.TestCase):
    def test_group_is_stable_owner_bound_and_preserves_every_notice(self):
        items = [notice(1), notice(2, state="read")]
        grouped = digest_views("alice", items)
        self.assertEqual(grouped, digest_views("alice", list(reversed(items))))
        self.assertEqual(grouped[0]["count"], 2)
        self.assertEqual(grouped[0]["unread_count"], 1)
        self.assertEqual({row["id"] for row in grouped[0]["notifications"]}, {row["id"] for row in items})
        self.assertEqual(grouped[0]["notifications"][0]["message"], items[0]["message"])
        self.assertNotIn("workspace_id", grouped[0]["notifications"][0])
        self.assertNotEqual(grouped[0]["id"], digest_views("bob", items)[0]["id"])
        self.assertNotEqual(grouped[0]["id"], digest_views("alice", items[:1])[0]["id"])
        self.assertEqual(grouped[0]["id"], digest_views("alice", [dict(item, state="read") for item in items])[0]["id"])

    def test_workspaces_kinds_windows_and_automation_updates_are_separate(self):
        items = [notice(1), notice(2, workspace_id="workspace-b"),
                 notice(3, kind="personal_suggestion_event"),
                 notice(4, visible_at="2026-09-29T18:00:00+00:00"),
                 notice(5, kind="automation_started"), notice(6, kind="automation_started")]
        grouped = digest_views("alice", items)
        self.assertEqual(len(grouped), 6)
        self.assertTrue(all(item["count"] == 1 for item in grouped))
        self.assertEqual(sum(item["count"] for item in grouped), len(items))

    def test_bounded_chunks_do_not_drop_or_duplicate_members(self):
        grouped = digest_views("alice", [notice(index) for index in range(1, 106)])
        self.assertEqual(len(grouped), 10)
        self.assertTrue(all(item["count"] == 10 for item in grouped))
        ids = [row["id"] for item in grouped for row in item["notifications"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {notice(index)["id"] for index in range(6, 106)})

    def test_timezones_representing_the_same_instant_share_a_group(self):
        grouped = digest_views("alice", [notice(1, visible_at="2026-09-29T12:00:00+00:00"),
                                        notice(2, visible_at="2026-09-29T18:00:00+06:00")])
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()

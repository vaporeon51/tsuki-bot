import unittest
from unittest.mock import MagicMock, patch

from src.db import utils
from src.discord_ui.content_reports import ContentReportView
from src.rate_limit import RecentPairRateLimiter


class ContentReportQueryTests(unittest.TestCase):
    @patch("src.db.utils.POOL")
    def test_broken_link_report_increments_every_matching_url(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 2

        updated = utils.add_content_report("role-1", "https://i.imgur.com/example.gif", "broken_link")

        self.assertEqual(updated, 2)
        query, params = cursor.execute.call_args.args
        self.assertIn("SET num_reports = num_reports + 1", query)
        self.assertIn("WHERE url = %s", query)
        self.assertEqual(params, ("https://i.imgur.com/example.gif",))

    @patch("src.db.utils.POOL")
    def test_wrong_idol_report_increments_only_the_delivered_pair(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1

        updated = utils.add_content_report("role-1", "https://i.imgur.com/example.gif", "wrong_idol")

        self.assertEqual(updated, 1)
        query, params = cursor.execute.call_args.args
        self.assertIn("WHERE role_id = %s", query)
        self.assertIn("AND url = %s", query)
        self.assertEqual(params, ("role-1", "https://i.imgur.com/example.gif"))

    def test_content_report_rejects_unknown_reason(self) -> None:
        with self.assertRaises(ValueError):
            utils.add_content_report("role-1", "https://i.imgur.com/example.gif", "something_else")

    def test_recent_pair_limiter_cools_down_only_the_same_user_and_idol(self) -> None:
        limiter = RecentPairRateLimiter(cooldown_seconds=300, capacity=20)

        self.assertTrue(limiter.allow(1, "role-1", now=0))
        self.assertFalse(limiter.allow(1, "role-1", now=299))
        self.assertTrue(limiter.allow(2, "role-1", now=299))
        self.assertTrue(limiter.allow(1, "role-2", now=299))
        self.assertTrue(limiter.allow(1, "role-1", now=300))

    def test_recent_pair_limiter_evicts_the_oldest_entry(self) -> None:
        limiter = RecentPairRateLimiter(cooldown_seconds=300, capacity=2)

        self.assertTrue(limiter.allow(1, "role-1", now=0))
        self.assertTrue(limiter.allow(1, "role-2", now=0))
        self.assertTrue(limiter.allow(1, "role-3", now=0))
        self.assertTrue(limiter.allow(1, "role-1", now=1))


class ContentReportViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_button_encodes_the_idol_and_uses_the_custom_emoji(self) -> None:
        view = ContentReportView("123", "https://i.imgur.com/GWCSS1f.mp4")
        button = view.children[0].item

        self.assertEqual(button.custom_id, "content_report:123")
        self.assertEqual(button.label, "Report issue")
        self.assertEqual(button.emoji.name, "important")
        self.assertEqual(button.emoji.id, 1538368125127360652)

if __name__ == "__main__":
    unittest.main()

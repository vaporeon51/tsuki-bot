import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.db import utils
from src.discord_ui.content_reports import ContentFeedbackView, ContentVoteButton
from src.rate_limit import RecentPairRateLimiter


class ContentReportQueryTests(unittest.TestCase):
    @patch("src.db.utils.POOL")
    def test_report_increments_only_the_delivered_pair(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1

        updated = utils.add_content_report("role-1", "https://i.imgur.com/example.gif")

        self.assertEqual(updated, 1)
        query, params = cursor.execute.call_args.args
        self.assertIn("SET num_reports = num_reports + 1", query)
        self.assertIn("WHERE role_id = %s", query)
        self.assertIn("AND url = %s", query)
        self.assertEqual(params, ("role-1", "https://i.imgur.com/example.gif"))

    @patch("src.db.utils.POOL")
    def test_load_vote_score_uses_existing_content_link_columns(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (8, 3)

        score = utils.get_content_vote_score("role-1", "https://i.imgur.com/example.gif")

        self.assertEqual(score, utils.ContentVoteScore(upvotes=8, downvotes=3))
        query, params = cursor.execute.call_args.args
        self.assertIn("MAX(num_upvotes)", query)
        self.assertIn("MAX(num_downvotes)", query)
        self.assertEqual(params, ("role-1", "https://i.imgur.com/example.gif"))

    @patch("src.db.utils.POOL")
    def test_upvote_updates_existing_content_link_columns(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (9, 3)

        score = utils.add_content_vote("role-1", "https://i.imgur.com/example.gif", "up")

        self.assertEqual(score.value, 6)
        query, params = cursor.execute.call_args.args
        self.assertIn("SET num_upvotes = num_upvotes + 1", query)
        self.assertNotIn("num_downvotes = num_downvotes + 1", query)
        self.assertEqual(params, ("role-1", "https://i.imgur.com/example.gif"))

    def test_content_vote_rejects_unknown_direction(self) -> None:
        with self.assertRaises(ValueError):
            utils.add_content_vote("role-1", "https://i.imgur.com/example.gif", "sideways")

    @patch("src.db.utils.POOL")
    def test_random_sampling_uses_net_community_votes(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []

        self.assertIsNone(utils.get_random_link_for_each_role(["role-1"], "18 year"))

        query = cursor.execute.call_args.args[0]
        self.assertIn("num_upvotes - num_downvotes", query)

    @patch("src.db.utils.POOL")
    def test_top_content_uses_original_reactions_and_bot_votes(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []

        self.assertIsNone(utils.get_latest_links_for_roles(3, 1, "18 year", ["role-1"], order="top"))

        query, params = cursor.execute.call_args.args
        self.assertIn("initial_reaction_count", query)
        self.assertIn("num_upvotes - cl.num_downvotes", query)
        self.assertIn("ORDER BY", query)
        self.assertEqual(params, [["role-1"], utils.REPORT_THRESHOLD, "18 year", 3, 1])

    @patch("src.db.utils.POOL")
    def test_oldest_content_is_ordered_ascending(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []

        self.assertIsNone(utils.get_latest_links_for_roles(2, 4, "18 year", order="oldest"))

        query, params = cursor.execute.call_args.args
        self.assertIn("ORDER BY cl.uploaded_date ASC", query)
        self.assertEqual(params, [utils.REPORT_THRESHOLD, "18 year", 2, 4])

    def test_content_order_rejects_unknown_values(self) -> None:
        with self.assertRaises(ValueError):
            utils.get_latest_links_for_roles(1, 0, "18 year", order="sideways")

    def test_recent_pair_limiter_cools_down_only_the_same_user_and_link(self) -> None:
        limiter = RecentPairRateLimiter(cooldown_seconds=300, capacity=20)

        self.assertTrue(limiter.allow(1, "https://example.com/one.gif", now=0))
        self.assertFalse(limiter.allow(1, "https://example.com/one.gif", now=299))
        self.assertTrue(limiter.allow(2, "https://example.com/one.gif", now=299))
        self.assertTrue(limiter.allow(1, "https://example.com/two.gif", now=299))
        self.assertTrue(limiter.allow(1, "https://example.com/one.gif", now=300))

    def test_recent_pair_limiter_evicts_the_oldest_entry(self) -> None:
        limiter = RecentPairRateLimiter(cooldown_seconds=300, capacity=2)

        self.assertTrue(limiter.allow(1, "https://example.com/one.gif", now=0))
        self.assertTrue(limiter.allow(1, "https://example.com/two.gif", now=0))
        self.assertTrue(limiter.allow(1, "https://example.com/three.gif", now=0))
        self.assertTrue(limiter.allow(1, "https://example.com/one.gif", now=1))


class ContentReportViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_feedback_view_shows_score_and_uses_the_custom_report_emoji(self) -> None:
        view = ContentFeedbackView(
            "123",
            "https://i.imgur.com/GWCSS1f.mp4",
            utils.ContentVoteScore(upvotes=4, downvotes=1),
        )
        upvote = view.children[0].item
        score = view.children[1]
        downvote = view.children[2].item
        report = view.children[3].item

        self.assertEqual(upvote.custom_id, "content_vote:up:123")
        self.assertEqual(upvote.emoji.name, "small_green_triangle_up31")
        self.assertEqual(upvote.emoji.id, 1538379192104914994)
        self.assertEqual(score.label, "+3")
        self.assertEqual(downvote.custom_id, "content_vote:down:123")
        self.assertEqual(downvote.emoji.name, "small_red_triangle_down31")
        self.assertEqual(downvote.emoji.id, 1538379272383758436)
        self.assertEqual(report.custom_id, "content_report:123")
        self.assertEqual(report.emoji.name, "important")
        self.assertEqual(report.emoji.id, 1538368125127360652)

    async def test_accepted_upvote_also_updates_personal_activity(self) -> None:
        interaction = MagicMock()
        interaction.user.id = 456
        interaction.response.edit_message = AsyncMock()
        button = ContentVoteButton("role-1", "https://example.com/one.gif", "up")

        with (
            patch("src.discord_ui.content_reports._vote_rate_limiter.allow", return_value=True),
            patch(
                "src.discord_ui.content_reports.add_content_vote",
                return_value=utils.ContentVoteScore(upvotes=2, downvotes=0),
            ),
            patch("src.discord_ui.content_reports.add_personal_activity", return_value=1) as add_activity,
        ):
            await button.callback(interaction)

        add_activity.assert_called_once_with(456, ["role-1"], 2)
        interaction.response.edit_message.assert_awaited_once()

    async def test_accepted_downvote_has_a_weaker_negative_activity_signal(self) -> None:
        interaction = MagicMock()
        interaction.user.id = 456
        interaction.response.edit_message = AsyncMock()
        button = ContentVoteButton("role-1", "https://example.com/one.gif", "down")

        with (
            patch("src.discord_ui.content_reports._vote_rate_limiter.allow", return_value=True),
            patch(
                "src.discord_ui.content_reports.add_content_vote",
                return_value=utils.ContentVoteScore(upvotes=0, downvotes=1),
            ),
            patch("src.discord_ui.content_reports.add_personal_activity", return_value=1) as add_activity,
        ):
            await button.callback(interaction)

        add_activity.assert_called_once_with(456, ["role-1"], -1)

if __name__ == "__main__":
    unittest.main()

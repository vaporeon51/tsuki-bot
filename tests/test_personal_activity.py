import unittest
from unittest.mock import MagicMock, patch

from src.db import bias_rater
from src.discord_ui.bias_rater import build_leaderboard_embeds
from src.rate_limit import RecentPairRateLimiter


class PersonalActivityDatabaseTests(unittest.TestCase):
    def test_activity_adjustment_is_unbounded_but_sublinear(self) -> None:
        small = bias_rater.calculate_activity_adjustment(4, 0)
        medium = bias_rater.calculate_activity_adjustment(40, 0)
        large = bias_rater.calculate_activity_adjustment(400, 0)

        self.assertGreater(medium, small)
        self.assertGreater(large, medium)
        self.assertLess(large - medium, 10 * (medium - small))
        self.assertEqual(
            bias_rater.calculate_activity_adjustment(-40, 0),
            -medium,
        )

    def test_explicit_matches_fade_activity_for_that_idol(self) -> None:
        no_matches = bias_rater.calculate_activity_adjustment(40, 0)
        ten_matches = bias_rater.calculate_activity_adjustment(40, 10)

        self.assertEqual(ten_matches, round(no_matches / 2))

    @patch("src.db.bias_rater.POOL")
    def test_activity_upserts_unique_user_idol_rows(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 2

        updated = bias_rater.add_personal_activity(123, ["idol-a", "idol-a", "idol-b"], 2)

        self.assertEqual(updated, 2)
        query, params = cursor.execute.call_args.args
        self.assertIn("INSERT INTO user_elo", query)
        self.assertIn("activity_score = user_elo.activity_score + EXCLUDED.activity_score", query)
        self.assertEqual(params, (123, 2, ["idol-a", "idol-b"]))

    @patch("src.db.bias_rater.POOL")
    def test_feed_only_user_gets_a_personal_leaderboard(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (0, True)
        cursor.fetchall.return_value = [
            ("idol-a", "Minji", "NewJeans", 1230, "https://example.com/a.gif", None, None)
        ]

        leaderboard = bias_rater.get_personal_leaderboard(123)

        self.assertEqual([entry.role_id for entry in leaderboard.entries], ["idol-a"])
        self.assertEqual(leaderboard.vote_count, 0)
        self.assertTrue(leaderboard.has_activity)
        ranking_query = cursor.execute.call_args_list[1].args[0]
        self.assertIn("activity_score", ranking_query)
        self.assertIn("AS effective_elo", ranking_query)


class PersonalActivityPresentationTests(unittest.TestCase):
    def test_feed_only_board_footer_explains_its_basis(self) -> None:
        leaderboard = bias_rater.Leaderboard(
            entries=[
                bias_rater.LeaderboardEntry(
                    role_id="idol-a",
                    member_name="Minji",
                    group_name="NewJeans",
                    elo=1230,
                    image_url="https://example.com/a.gif",
                )
            ],
            vote_count=0,
            has_activity=True,
        )

        embeds = build_leaderboard_embeds("Personal Bias Leaderboard", leaderboard)

        self.assertEqual(embeds[0].footer.text, "Based on feed activity")


class FeedActivityRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_user_idol_pair_only_scores_once_per_window(self) -> None:
        import src.personal_activity as personal_activity

        limiter = RecentPairRateLimiter(cooldown_seconds=300, capacity=20)
        with (
            patch.object(personal_activity, "_feed_activity_rate_limiter", limiter),
            patch.object(personal_activity, "add_personal_activity", return_value=1) as add_activity,
        ):
            first = await personal_activity.record_feed_activity(123, ["idol-a"], 1)
            second = await personal_activity.record_feed_activity(123, ["idol-a"], 1)

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        add_activity.assert_called_once_with(123, ["idol-a"], 1)


if __name__ == "__main__":
    unittest.main()

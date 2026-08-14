import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from dotenv import load_dotenv

load_dotenv()

from src.db import utils
from src.reaction.gather import gather_dead_link


class DeadLinkGatherTests(unittest.IsolatedAsyncioTestCase):
    @patch("src.reaction.gather.mark_url_dead")
    async def test_pending_embed_does_not_mark_link_dead(self, mark_url_dead: MagicMock) -> None:
        message = MagicMock()
        message.id = 123
        checked_message = MagicMock()
        checked_message.embeds = []
        message.channel.fetch_message = AsyncMock(return_value=checked_message)

        marked_count = await gather_dead_link(
            message,
            "https://i.imgur.com/dead.mp4",
            wait_seconds=0,
        )

        self.assertEqual(marked_count, 0)
        message.channel.fetch_message.assert_awaited_once_with(123)
        mark_url_dead.assert_not_called()

    @patch("src.reaction.gather.mark_url_dead")
    async def test_wrong_embed_marks_all_matching_rows(self, mark_url_dead: MagicMock) -> None:
        message = MagicMock()
        message.id = 123
        checked_message = MagicMock()
        checked_message.embeds = [MagicMock(type="article")]
        message.channel.fetch_message = AsyncMock(return_value=checked_message)
        mark_url_dead.return_value = 2

        marked_count = await gather_dead_link(
            message,
            "https://i.imgur.com/dead.mp4",
            wait_seconds=0,
        )

        self.assertEqual(marked_count, 2)
        message.channel.fetch_message.assert_awaited_once_with(123)
        mark_url_dead.assert_called_once_with("https://i.imgur.com/dead.mp4")

    @patch("src.reaction.gather.mark_url_dead")
    async def test_live_probe_is_not_marked_dead(self, mark_url_dead: MagicMock) -> None:
        message = MagicMock()
        message.id = 456
        checked_message = MagicMock()
        checked_message.embeds = [MagicMock(type="video")]
        message.channel.fetch_message = AsyncMock(return_value=checked_message)

        marked_count = await gather_dead_link(message, "https://i.imgur.com/live.mp4", wait_seconds=0)

        self.assertEqual(marked_count, 0)
        mark_url_dead.assert_not_called()


class DeadLinkQueryTests(unittest.TestCase):
    @patch("src.db.utils.POOL")
    def test_get_live_urls_uses_a_distinct_stable_cursor(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            ("https://i.imgur.com/a.mp4", ["Mina (TWICE)"]),
            ("https://i.imgur.com/b.mp4", ["Tsuki (Billlie)", "Suhyeon (Billlie)"]),
        ]

        candidates = utils.get_live_urls_for_dead_link_check("https://i.imgur.com/0.mp4", 100)

        self.assertEqual(candidates[0].url, "https://i.imgur.com/a.mp4")
        self.assertEqual(candidates[0].role_labels, ("Mina (TWICE)",))
        self.assertEqual(candidates[1].role_labels, ("Tsuki (Billlie)", "Suhyeon (Billlie)"))
        query, params = cursor.execute.call_args.args
        self.assertIn("array_agg(DISTINCT role_label", query)
        self.assertIn("ORDER BY url ASC", query)
        self.assertEqual(params, (5, "https://i.imgur.com/0.mp4", "https://i.imgur.com/0.mp4", 100))

    @patch("src.db.utils.POOL")
    def test_dead_link_cursor_is_loaded_and_saved(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("https://i.imgur.com/last.mp4",)

        self.assertEqual(utils.get_dead_link_check_cursor(), "https://i.imgur.com/last.mp4")
        utils.set_dead_link_check_cursor("https://i.imgur.com/next.mp4")

        load_query = cursor.execute.call_args_list[0].args[0]
        save_query, save_params = cursor.execute.call_args_list[1].args
        self.assertIn("SELECT last_url", load_query)
        self.assertIn("ON CONFLICT (state_id)", save_query)
        self.assertEqual(save_params, ("https://i.imgur.com/next.mp4",))


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from src import content_update  # noqa: E402


def message(
    message_id: str,
    timestamp: str,
    *,
    roles: list[str] | None = None,
    urls: list[str] | None = None,
) -> dict:
    return {
        "id": message_id,
        "timestamp": timestamp,
        "author": {"id": "author-1", "username": "poster"},
        "content": "\n".join(urls or []),
        "mention_roles": roles or [],
        "embeds": [{"type": "gifv", "url": url} for url in urls or []],
    }


class ContentUpdateTests(unittest.IsolatedAsyncioTestCase):
    @patch("src.content_update.content_update_db.persist_content_update")
    @patch("src.content_update.content_discord.get_messages_around")
    @patch("src.content_update.content_discord.get_messages_after")
    @patch("src.content_update.content_update_db.get_latest_message_id", return_value="100")
    async def test_no_new_messages_skips_context_and_database_write(
        self,
        get_latest_message_id: Mock,
        get_messages_after: Mock,
        get_messages_around: Mock,
        persist_content_update: Mock,
    ) -> None:
        get_messages_after.return_value = []

        await content_update.run_content_links_update()

        get_latest_message_id.assert_called_once()
        get_messages_after.assert_called_once_with("100")
        get_messages_around.assert_not_called()
        persist_content_update.assert_not_called()

    @patch("src.content_update.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.content_update.content_update_db.persist_content_update", side_effect=[1, 1])
    @patch("src.content_update.content_discord.get_messages_around", return_value=[])
    @patch("src.content_update.content_discord.get_messages_after")
    @patch("src.content_update.content_update_db.get_latest_message_id", return_value="100")
    async def test_each_page_is_committed_with_its_own_cursor(
        self,
        get_latest_message_id: Mock,
        get_messages_after: Mock,
        get_messages_around: Mock,
        persist_content_update: Mock,
        sleep: AsyncMock,
    ) -> None:
        first = message(
            "101",
            "2026-08-10T18:07:47.064000+00:00",
            roles=["role-1"],
            urls=["https://imgur.com/first"],
        )
        second = message(
            "102",
            "2026-08-10T18:08:47.064000+00:00",
            urls=["https://imgur.com/second"],
        )
        get_messages_after.side_effect = [[first], [second], []]

        await content_update.run_content_links_update()

        get_messages_after.assert_has_calls([call("100"), call("101"), call("102")])
        self.assertEqual(persist_content_update.call_count, 2)
        first_write = persist_content_update.call_args_list[0].args
        second_write = persist_content_update.call_args_list[1].args
        self.assertEqual(first_write[1], "101")
        self.assertEqual(second_write[1], "102")
        self.assertEqual([link.url for link in first_write[2]], ["https://imgur.com/first"])
        self.assertEqual([link.url for link in second_write[2]], ["https://imgur.com/second"])
        self.assertEqual(sleep.await_count, 2)


if __name__ == "__main__":
    unittest.main()

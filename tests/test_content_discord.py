import unittest
from unittest.mock import Mock, patch

import requests

from src import content_discord


def response(status_code: int, payload: object) -> Mock:
    result = Mock()
    result.status_code = status_code
    result.headers = {}
    result.json.return_value = payload
    if status_code >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(response=result)
    return result


class ContentDiscordTests(unittest.TestCase):
    @patch.dict("os.environ", {"USER_AUTH": "test-auth"})
    @patch("src.content_discord.time.sleep")
    @patch("src.content_discord.requests.get")
    def test_rate_limit_waits_and_retries(self, get: Mock, sleep: Mock) -> None:
        limited = response(429, {"retry_after": 2.5})
        successful = response(200, [{"id": "101"}])
        get.side_effect = [limited, successful]

        messages = content_discord.get_messages_after("100")

        self.assertEqual(messages, [{"id": "101"}])
        sleep.assert_called_once_with(2.5)
        self.assertEqual(get.call_count, 2)
        limited.close.assert_called_once()
        successful.close.assert_called_once()

    @patch.dict("os.environ", {"USER_AUTH": "test-auth"})
    @patch("src.content_discord.time.sleep")
    @patch("src.content_discord.requests.get")
    def test_non_transient_http_error_is_not_retried(self, get: Mock, sleep: Mock) -> None:
        rejected = response(401, {"message": "401: Unauthorized"})
        get.return_value = rejected

        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            content_discord.get_messages_after("100")

        get.assert_called_once()
        sleep.assert_not_called()
        rejected.close.assert_called_once()

    @patch.dict("os.environ", {"USER_AUTH": "test-auth"})
    @patch("src.content_discord.time.sleep")
    @patch("src.content_discord.requests.get")
    def test_server_error_retries_with_backoff(self, get: Mock, sleep: Mock) -> None:
        unavailable = response(503, {"message": "temporarily unavailable"})
        successful = response(200, [])
        get.side_effect = [unavailable, successful]

        self.assertEqual(content_discord.get_messages_after("100"), [])

        sleep.assert_called_once_with(1)
        self.assertEqual(get.call_count, 2)
        unavailable.close.assert_called_once()
        successful.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

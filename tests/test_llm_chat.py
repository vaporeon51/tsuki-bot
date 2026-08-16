import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from src.llm_chat import (
    ChatMsg,
    ContentAttachment,
    ContentRequest,
    MAX_CONTENT_ATTACHMENTS,
    _content_fallback_text,
    _content_request_from_args,
    _resolve_content,
    generate_chat_response,
    SYSTEM_PROMPT,
)


class ContentRequestTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_treats_bare_idol_and_group_names_as_content_requests(self) -> None:
        self.assertIn("Bare idol and group names are content requests", SYSTEM_PROMPT)
        self.assertIn('"kiikii haum"', SYSTEM_PROMPT)

    def test_request_is_bounded_and_normalized(self) -> None:
        request = _content_request_from_args(
            {"query": " minji ", "mode": "latest", "count": 9, "offset": -4}
        )

        self.assertEqual(request.query, "minji")
        self.assertEqual(request.mode, "latest")
        self.assertEqual(request.count, MAX_CONTENT_ATTACHMENTS)
        self.assertEqual(request.requested_count, 9)
        self.assertEqual(request.offset, 0)

    @patch("src.llm_chat.get_random_link_for_each_role", return_value=[("minji", "one"), ("minji", "two")])
    @patch("src.llm_chat.get_closest_roles", return_value=["minji"])
    async def test_random_idol_request_repeats_one_match_for_multiple_links(self, closest_roles, random_links) -> None:
        attachments = await _resolve_content(ContentRequest("minji", "random", 2, 0, 2), "18 year")

        self.assertEqual(attachments, [ContentAttachment("minji", "one"), ContentAttachment("minji", "two")])
        closest_roles.assert_called_once_with("minji", "18 year", 2)
        random_links.assert_called_once_with(["minji", "minji"], "18 year")

    @patch("src.llm_chat.get_latest_links_for_roles", return_value=[("minji", "newest")])
    @patch("src.llm_chat.get_closest_roles", return_value=["minji"])
    async def test_latest_request_passes_count_and_offset_to_db(self, closest_roles, latest_links) -> None:
        attachments = await _resolve_content(ContentRequest("minji", "latest", 2, 4, 2), "18 year")

        self.assertEqual(attachments, [ContentAttachment("minji", "newest")])
        closest_roles.assert_called_once_with("minji", "18 year", 2)
        latest_links.assert_called_once_with(
            num_links=2,
            skip=4,
            min_age="18 year",
            role_ids=["minji"],
            order="latest",
        )

    @patch("src.llm_chat.get_latest_links_for_roles", return_value=[("minji", "top")])
    async def test_top_request_uses_the_highest_rated_query(self, ordered_links) -> None:
        attachments = await _resolve_content(ContentRequest("all", "top", 1, 2, 1), "18 year")

        self.assertEqual(attachments, [ContentAttachment("minji", "top")])
        ordered_links.assert_called_once_with(num_links=1, skip=2, min_age="18 year", order="top")

    @patch("src.llm_chat.get_latest_links_for_roles", return_value=[("minji", "oldest")])
    async def test_oldest_request_uses_the_earliest_upload_query(self, ordered_links) -> None:
        attachments = await _resolve_content(ContentRequest("all", "oldest", 1, 3, 1), "18 year")

        self.assertEqual(attachments, [ContentAttachment("minji", "oldest")])
        ordered_links.assert_called_once_with(num_links=1, skip=3, min_age="18 year", order="oldest")

    async def test_tool_only_response_uses_a_local_reply_without_second_model_call(self) -> None:
        tool_response = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "share_content",
                    "args": {"query": "minji", "count": 2},
                    "id": "call-1",
                }
            ],
        )
        with (
            patch("src.llm_chat._ainvoke", new=AsyncMock(return_value=tool_response)) as invoke,
            patch(
                "src.llm_chat._resolve_content",
                new=AsyncMock(return_value=[ContentAttachment("minji", "one"), ContentAttachment("minji", "two")]),
            ),
        ):
            result = await generate_chat_response([ChatMsg("user", 1, False, "show minji")], "18 year")

        self.assertEqual(invoke.await_count, 1)
        self.assertEqual(result.text, "gotchu, some minji for you !!")
        self.assertEqual(len(result.attachments), 2)

    def test_canned_message_explains_the_attachment_limit(self) -> None:
        message = _content_fallback_text([ContentRequest("random", "random", 3, 0, 8)], 3)

        self.assertEqual(message, "i can only send 3 at once so here's 3 !!")


if __name__ == "__main__":
    unittest.main()

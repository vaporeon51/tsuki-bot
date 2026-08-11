import unittest

from src import content_ingestion


def message(
    message_id: str,
    timestamp: str,
    author_id: str,
    content: str,
    *,
    roles: list[str] | None = None,
    urls: list[str] | None = None,
    parent_id: str | None = None,
    referenced_message: dict | None = None,
) -> dict:
    result = {
        "id": message_id,
        "timestamp": timestamp,
        "author": {"id": author_id, "username": "poster"},
        "content": content,
        "mention_roles": roles or [],
        "embeds": [{"type": "gifv", "url": url} for url in urls or []],
    }
    if parent_id:
        result["message_reference"] = {"message_id": parent_id}
    if referenced_message is not None:
        result["referenced_message"] = referenced_message
    return result


class ContentMessageClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = content_ingestion.ContentMessageClassifier()
        self.root = message(
            "100",
            "2026-08-10T18:07:47.064000+00:00",
            "author-1",
            "<@&role-1>\nhttps://imgur.com/root",
            roles=["role-1"],
            urls=["https://imgur.com/root"],
        )

    def test_root_and_url_only_unthreaded_continuation(self) -> None:
        root_links = self.classifier.consume(self.root)
        continuation = message(
            "101",
            "2026-08-10T18:08:47.064000+00:00",
            "author-1",
            "https://imgur.com/part-2",
            urls=["https://imgur.com/part-2"],
        )
        continuation_links = self.classifier.consume(continuation)

        self.assertEqual([link.source_kind for link in root_links], [content_ingestion.ROOT])
        self.assertEqual([link.source_kind for link in continuation_links], [content_ingestion.UNTHREADED_CONTINUATION])
        self.assertEqual(continuation_links[0].root_message_id, "100")
        self.assertEqual(continuation_links[0].role_id, "role-1")

    def test_reply_continuation_can_use_inline_parent(self) -> None:
        reply = message(
            "101",
            "2026-08-10T18:07:53.960000+00:00",
            "author-1",
            "https://imgur.com/part-2",
            urls=["https://imgur.com/part-2"],
            parent_id="100",
            referenced_message=self.root,
        )

        links = self.classifier.consume(reply)

        self.assertEqual([link.source_kind for link in links], [content_ingestion.REPLY_CONTINUATION])
        self.assertEqual(links[0].root_message_id, "100")

    def test_reply_to_known_continuation_keeps_the_original_root(self) -> None:
        self.classifier.consume(self.root)
        first_reply = message(
            "101",
            "2026-08-10T18:07:53.960000+00:00",
            "author-1",
            "https://imgur.com/part-2",
            urls=["https://imgur.com/part-2"],
            parent_id="100",
        )
        self.classifier.consume(first_reply)
        second_reply = message(
            "102",
            "2026-08-10T18:08:00.000000+00:00",
            "author-1",
            "https://imgur.com/part-3",
            urls=["https://imgur.com/part-3"],
            parent_id="101",
        )

        links = self.classifier.consume(second_reply)

        self.assertEqual([link.source_kind for link in links], [content_ingestion.REPLY_CONTINUATION])
        self.assertEqual(links[0].root_message_id, "100")

    def test_unthreaded_window_is_measured_from_previous_continuation(self) -> None:
        self.classifier.consume(self.root)
        first = message(
            "101",
            "2026-08-10T18:09:47.064000+00:00",
            "author-1",
            "https://imgur.com/part-2",
            urls=["https://imgur.com/part-2"],
        )
        second = message(
            "102",
            "2026-08-10T18:11:47.064000+00:00",
            "author-1",
            "https://imgur.com/part-3",
            urls=["https://imgur.com/part-3"],
        )

        self.assertEqual(len(self.classifier.consume(first)), 1)
        self.assertEqual(len(self.classifier.consume(second)), 1)

    def test_rejects_unthreaded_media_outside_the_window(self) -> None:
        self.classifier.consume(self.root)
        late = message(
            "101",
            "2026-08-10T18:09:47.065000+00:00",
            "author-1",
            "https://imgur.com/late",
            urls=["https://imgur.com/late"],
        )

        self.assertEqual(self.classifier.consume(late), [])

    def test_duplicate_role_mentions_and_embed_urls_do_not_duplicate_links(self) -> None:
        duplicate_root = message(
            "100",
            "2026-08-10T18:07:47.064000+00:00",
            "author-1",
            "<@&role-1>\nhttps://imgur.com/root",
            roles=["role-1", "role-1"],
            urls=["https://imgur.com/root", "https://imgur.com/root"],
        )

        links = self.classifier.consume(duplicate_root)

        self.assertEqual(len(links), 1)

    def test_animated_image_embed_is_ingested(self) -> None:
        animated_image_root = self.root | {
            "content": "<@&role-1>\nhttps://cdn.example.com/content.webp",
            "embeds": [
                {
                    "type": "image",
                    "url": "https://cdn.example.com/content.webp",
                    "thumbnail": {"flags": content_ingestion.ANIMATED_MEDIA_FLAG},
                }
            ],
        }

        links = self.classifier.consume(animated_image_root)

        self.assertEqual([link.url for link in links], ["https://cdn.example.com/content.webp"])
        self.assertEqual([link.source_kind for link in links], [content_ingestion.ROOT])

    def test_still_image_embed_is_not_ingested(self) -> None:
        still_image_root = self.root | {
            "content": "<@&role-1>\nhttps://cdn.example.com/content.webp",
            "embeds": [
                {
                    "type": "image",
                    "url": "https://cdn.example.com/content.webp",
                    "thumbnail": {"flags": 0},
                }
            ],
        }

        self.assertEqual(self.classifier.consume(still_image_root), [])

    def test_reply_context_cache_is_bounded(self) -> None:
        classifier = content_ingestion.ContentMessageClassifier(context_cache_size=1)
        classifier.consume(self.root)
        other_root = message(
            "200",
            "2026-08-10T18:08:00.000000+00:00",
            "author-2",
            "<@&role-2>\nhttps://imgur.com/other",
            roles=["role-2"],
            urls=["https://imgur.com/other"],
        )
        classifier.consume(other_root)
        old_reply_without_inline_parent = message(
            "201",
            "2026-08-10T18:08:10.000000+00:00",
            "author-1",
            "https://imgur.com/part-2",
            urls=["https://imgur.com/part-2"],
            parent_id="100",
        )

        self.assertEqual(classifier.consume(old_reply_without_inline_parent), [])

    def test_rejects_other_author_reply_and_textual_unthreaded_message(self) -> None:
        self.classifier.consume(self.root)
        other_author_reply = message(
            "101",
            "2026-08-10T18:07:53.960000+00:00",
            "author-2",
            "https://imgur.com/not-content",
            urls=["https://imgur.com/not-content"],
            parent_id="100",
        )
        merged = message(
            "102",
            "2026-08-10T18:08:47.064000+00:00",
            "author-1",
            "Merged\nhttps://imgur.com/not-content",
            urls=["https://imgur.com/not-content"],
        )

        self.assertEqual(self.classifier.consume(other_author_reply), [])
        self.assertEqual(self.classifier.consume(merged), [])

    def test_same_author_non_media_message_ends_unthreaded_chain(self) -> None:
        self.classifier.consume(self.root)
        comment = message(
            "101",
            "2026-08-10T18:08:00.000000+00:00",
            "author-1",
            "unrelated comment",
        )
        media = message(
            "102",
            "2026-08-10T18:08:10.000000+00:00",
            "author-1",
            "https://imgur.com/not-a-continuation",
            urls=["https://imgur.com/not-a-continuation"],
        )

        self.classifier.consume(comment)

        self.assertEqual(self.classifier.consume(media), [])


if __name__ == "__main__":
    unittest.main()

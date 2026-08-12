import tempfile
import unittest
from pathlib import Path
from concurrent.futures import Future
from unittest.mock import MagicMock, Mock, patch

from src import content_recovery


class ContentRecoveryTests(unittest.TestCase):
    @staticmethod
    def candidate() -> content_recovery.Candidate:
        return content_recovery.Candidate(
            content_link_id=42,
            role_id="1",
            url="https://imgur.com/original",
            original_url=None,
            recovery_generation=0,
            num_reports=7,
            initial_reaction_count=0,
            author=None,
            uploaded_date=None,
        )

    def test_frames_to_drop_accounts_for_the_source_generation(self) -> None:
        self.assertEqual(content_recovery.frames_to_drop(1, 0), 1)
        self.assertEqual(content_recovery.frames_to_drop(2, 0), 3)
        self.assertEqual(content_recovery.frames_to_drop(3, 0), 5)
        self.assertEqual(content_recovery.frames_to_drop(3, 2), 2)
        with self.assertRaises(ValueError):
            content_recovery.frames_to_drop(2, 2)
        with self.assertRaises(ValueError):
            content_recovery.frames_to_drop(4, 0)

    @patch("src.content_recovery.time.sleep")
    def test_verify_uploaded_link_uses_the_test_message_embed(self, sleep: Mock) -> None:
        discord_client = Mock()
        discord_client.create_message.return_value = {"id": "123"}
        discord_client.get_message.return_value = {"embeds": [{"type": "video"}]}

        verified = content_recovery.verify_uploaded_link(
            discord_client, content_recovery.RECOVERY_TEST_CHANNEL_ID, "https://i.imgur.com/recovered.mp4"
        )

        self.assertTrue(verified)
        discord_client.create_message.assert_called_once_with(
            content_recovery.RECOVERY_TEST_CHANNEL_ID, "https://i.imgur.com/recovered.mp4"
        )
        discord_client.get_message.assert_called_once_with(content_recovery.RECOVERY_TEST_CHANNEL_ID, "123")
        sleep.assert_not_called()

    @patch("src.content_recovery.time.sleep")
    def test_verify_uploaded_link_rejects_a_broken_embed(self, _sleep: Mock) -> None:
        discord_client = Mock()
        discord_client.create_message.return_value = {"id": "123"}
        discord_client.get_message.return_value = {"embeds": [{"type": "article"}]}

        self.assertFalse(
            content_recovery.verify_uploaded_link(
                discord_client, content_recovery.RECOVERY_TEST_CHANNEL_ID, "https://i.imgur.com/recovered.mp4"
            )
        )
        _sleep.assert_not_called()

    @patch("src.content_recovery.time.sleep")
    def test_verify_uploaded_link_waits_only_while_the_embed_is_pending(self, sleep: Mock) -> None:
        discord_client = Mock()
        discord_client.create_message.return_value = {"id": "123"}
        discord_client.get_message.side_effect = [
            {"embeds": []},
            {"embeds": [{"type": "video"}]},
        ]

        self.assertTrue(
            content_recovery.verify_uploaded_link(
                discord_client, content_recovery.RECOVERY_TEST_CHANNEL_ID, "https://i.imgur.com/recovered.mp4"
            )
        )

        sleep.assert_called_once_with(content_recovery.RECOVERY_VERIFICATION_POLL_INTERVAL_SECONDS)

    def test_record_dead_replacement_keeps_the_content_link_dead(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (7,)
        cursor.rowcount = 1

        content_recovery.record_dead_replacement(
            connection,
            self.candidate(),
            "https://i.imgur.com/dead.mp4",
            "batch",
            "direct_imgur",
            10,
            9,
            "a" * 64,
            "dead",
            1,
        )

        content_link_update = cursor.execute.call_args_list[0].args[0]
        self.assertIn("is_dead = TRUE", content_link_update)
        self.assertNotIn("url = %s,", content_link_update.split("WHERE", 1)[0])
        self.assertNotIn("content_link_id", content_link_update.split("WHERE", 1)[1])

    def test_apply_success_updates_every_dead_row_with_the_source_url(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (7,)
        cursor.rowcount = 1

        content_recovery.apply_success(
            connection,
            self.candidate(),
            "https://i.imgur.com/recovered.mp4",
            "batch",
            "direct_imgur",
            10,
            9,
            "a" * 64,
            "recovered",
            1,
        )

        content_link_update = cursor.execute.call_args_list[0].args[0]
        self.assertIn("WHERE url = %s", content_link_update)
        self.assertIn("AND is_dead = TRUE", content_link_update)
        self.assertNotIn("content_link_id", content_link_update.split("WHERE", 1)[1])

    def test_fetch_candidates_deduplicates_shared_urls(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []

        self.assertEqual(content_recovery.fetch_candidates(connection, None, 10), [])

        query = cursor.execute.call_args.args[0]
        self.assertIn("SELECT DISTINCT ON (url)", query)
        self.assertIn("FROM one_candidate_per_url", query)

    @patch("src.content_recovery.finalize_pending_verification")
    def test_completed_verifications_are_committed_before_the_batch_ends(self, finalize: Mock) -> None:
        completed = Future()
        completed.set_result(True)
        waiting = Future()
        completed_item = MagicMock()
        waiting_item = MagicMock()

        remaining = content_recovery.finalize_completed_verifications(
            MagicMock(), [(completed, completed_item), (waiting, waiting_item)]
        )

        finalize.assert_called_once()
        self.assertEqual(remaining, [(waiting, waiting_item)])

    @patch("src.content_recovery.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.content_recovery.subprocess.run")
    def test_trim_leading_frames_configures_ffmpeg_for_the_requested_generation(self, run: Mock, _which: Mock) -> None:
        def create_ffmpeg_output(command: list[str], **_kwargs: object) -> None:
            Path(command[-1]).touch()

        run.side_effect = create_ffmpeg_output
        with tempfile.TemporaryDirectory() as temporary_dir:
            input_path = Path(temporary_dir) / "input.mp4"
            input_path.touch()

            output_path = content_recovery.trim_leading_frames(input_path, 2, True)

        command = run.call_args.args[0]
        self.assertIn("select='gte(n,2)',setpts=N/FRAME_RATE/TB", command)
        self.assertTrue(output_path.name.endswith("_trimmed.mp4"))


if __name__ == "__main__":
    unittest.main()

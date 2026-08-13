import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from src.db import utils  # noqa: E402


class LinkExportTests(unittest.TestCase):
    @patch("src.db.utils.POOL")
    def test_role_autocomplete_returns_name_and_group_labels(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            ("123", "Mina", "TWICE"),
            ("456", "", "Billlie"),
        ]

        matches = utils.role_autocomplete_matches("mi")

        self.assertEqual(matches, [("Mina (TWICE)", "123"), ("Billlie", "456")])
        query = cursor.execute.call_args.args[0]
        self.assertIn("cl.is_dead = FALSE", query)
        self.assertIn("cl.num_reports < %s", query)

    @patch("src.db.utils.POOL")
    def test_export_contains_only_the_supported_columns_and_writes_csv(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.__iter__.return_value = [
            (
                "Mina (TWICE)",
                "123",
                "2026-08-13 12:00:00",
                "poster",
                "https://i.imgur.com/live.mp4",
                "https://imgur.com/original",
            )
        ]

        with tempfile.TemporaryDirectory() as temporary_dir:
            export = utils.export_live_links_csv("123", Path(temporary_dir))
            self.assertEqual(export.row_count, 1)
            with export.paths[0].open(newline="") as file:
                rows = list(csv.reader(file))

        self.assertEqual(rows[0], list(utils.LINK_EXPORT_COLUMNS))
        self.assertEqual(rows[1][0], "Mina (TWICE)")
        self.assertEqual(rows[1][4], "https://i.imgur.com/live.mp4")
        query = cursor.execute.call_args.args[0]
        self.assertIn("cl.is_dead = FALSE", query)
        self.assertIn("cl.num_reports < %s", query)

import unittest
from unittest.mock import MagicMock, patch

from src.db import utils
from src.discord_ui.disambiguate import DisambiguationView


class DisambiguationQueryTests(unittest.TestCase):
    @patch("src.db.utils.POOL")
    def test_candidate_is_live_unresolved_and_has_selectable_roles(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("https://i.imgur.com/example.gif",)
        cursor.fetchall.return_value = [
            ("role-1", "Mina (TWICE)"),
            ("role-2", "Sana (TWICE)"),
        ]

        candidate = utils.get_disambiguation_candidate()

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.url, "https://i.imgur.com/example.gif")
        self.assertEqual([role.role_id for role in candidate.roles], ["role-1", "role-2"])
        self.assertEqual([role.label for role in candidate.roles], ["Mina (TWICE)", "Sana (TWICE)"])

        candidate_query = cursor.execute.call_args_list[0].args[0]
        self.assertIn("is_dead = FALSE", candidate_query)
        self.assertIn("disambiguated = FALSE", candidate_query)
        self.assertIn("BETWEEN 2 AND 25", candidate_query)

    @patch("src.db.utils.POOL")
    def test_no_candidate_returns_none(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        self.assertIsNone(utils.get_disambiguation_candidate())
        self.assertEqual(cursor.execute.call_count, 1)

    @patch("src.db.utils.POOL")
    def test_apply_keeps_selected_roles_and_suppresses_others(self, pool: MagicMock) -> None:
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 3

        updated = utils.apply_disambiguation("https://i.imgur.com/example.gif", ("role-1", "role-3"))

        self.assertEqual(updated, 3)
        query, params = cursor.execute.call_args.args
        self.assertIn("disambiguated = TRUE", query)
        self.assertIn("role_id = ANY", query)
        self.assertIn("GREATEST(num_reports", query)
        self.assertEqual(params, (["role-1", "role-3"], 5, "https://i.imgur.com/example.gif"))


class DisambiguationViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_uses_one_multi_select_for_all_candidate_roles(self) -> None:
        candidate = utils.DisambiguationCandidate(
            url="https://i.imgur.com/example.gif",
            roles=(
                utils.DisambiguationRole("role-1", "Mina (TWICE)"),
                utils.DisambiguationRole("role-2", "Sana (TWICE)"),
            ),
        )

        view = DisambiguationView(user_id=123, candidate=candidate)

        self.assertEqual(view.role_select.min_values, 0)
        self.assertEqual(view.role_select.max_values, 2)
        self.assertEqual([option.value for option in view.role_select.options], ["role-1", "role-2"])
        self.assertEqual(len(view.children), 3)


if __name__ == "__main__":
    unittest.main()

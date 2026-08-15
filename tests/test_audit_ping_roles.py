import unittest

from scripts.audit_ping_roles import RoleInfo, audit_ping_roles, role_ids_in_message, role_ids_in_ping_role_listing


class AuditPingRolesTests(unittest.TestCase):
    def test_extracts_structured_and_textual_role_mentions(self) -> None:
        message = {
            "mention_roles": [123, "456", "not-a-role"],
            "content": "also <@&789> and a duplicate <@&456>",
            "embeds": [{"description": "and <@&999> in an embed"}],
        }

        self.assertEqual(role_ids_in_message(message), {"123", "456", "789", "999"})

    def test_extracts_plain_text_role_list_entries(self) -> None:
        message = {"content": "Hanni [NewJeans] 1000863360776147054\nNot a role ID: 1234"}

        self.assertEqual(role_ids_in_ping_role_listing(message), {"1000863360776147054"})

    def test_marks_roles_missing_from_each_source(self) -> None:
        audit = audit_ping_roles(
            {"1": ("100",), "2": ("101",)},
            [
                RoleInfo("2", "Present", "Present", "Group"),
                RoleInfo("3", "Table only", "Table only", "Group"),
            ],
            scanned_message_count=2,
            scanned_page_count=1,
        )

        self.assertEqual(audit.new_role_ids, frozenset({"1"}))
        self.assertEqual(audit.missing_role_ids, frozenset({"3"}))
        self.assertEqual(audit.message_ids_by_role_id["1"], ("100",))


if __name__ == "__main__":
    unittest.main()

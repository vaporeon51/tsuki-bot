import unittest

from src.birthday_feed import BIRTHDAY_CHEER, BIRTHDAY_HEADER_END, BIRTHDAY_HEADER_START, build_birthday_message


class BirthdayCardTests(unittest.TestCase):
    def test_birthday_message_uses_the_birthday_emojis(self) -> None:
        message = build_birthday_message("Minji", "NewJeans")

        self.assertTrue(message.startswith(f"# {BIRTHDAY_HEADER_START} Happy Birthday, Minji! {BIRTHDAY_HEADER_END}"))
        self.assertIn("NewJeans", message)
        self.assertIn(BIRTHDAY_CHEER, message)

    def test_birthday_message_handles_a_soloist_without_a_group(self) -> None:
        message = build_birthday_message("IU", "")

        self.assertIn("everyone give IU lots of love", message)
        self.assertNotIn("give 's", message)


if __name__ == "__main__":
    unittest.main()

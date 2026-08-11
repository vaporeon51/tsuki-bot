import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src import content_recovery


class ContentRecoveryTests(unittest.TestCase):
    def test_frames_to_drop_accounts_for_the_source_generation(self) -> None:
        self.assertEqual(content_recovery.frames_to_drop(1, 0), 1)
        self.assertEqual(content_recovery.frames_to_drop(2, 0), 3)
        self.assertEqual(content_recovery.frames_to_drop(3, 0), 5)
        self.assertEqual(content_recovery.frames_to_drop(4, 0), 7)
        self.assertEqual(content_recovery.frames_to_drop(3, 2), 2)
        with self.assertRaises(ValueError):
            content_recovery.frames_to_drop(2, 2)
        with self.assertRaises(ValueError):
            content_recovery.frames_to_drop(5, 0)

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

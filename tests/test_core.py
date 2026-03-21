import unittest
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from wukong_invite.core import extract_image_asset_id, extract_invite_code, parse_js_payload
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ops import cmd_fill_app
from wukong_invite.ocr import VisionOCR, TesseractOCR, create_ocr


class ParseJsPayloadTests(unittest.TestCase):
    def test_parse_jsonp_payload(self) -> None:
        payload = (
            'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/'
            'O1CN01No3bjS1tzEQxQUg4t_!!6000000005972-2-tps-1974-540.png"})'
        )
        self.assertEqual(
            parse_js_payload(payload),
            "https://gw.alicdn.com/imgextra/i2/O1CN01No3bjS1tzEQxQUg4t_!!6000000005972-2-tps-1974-540.png",
        )

    def test_parse_plain_text_fallback(self) -> None:
        payload = "see image https://example.com/code.png now"
        self.assertEqual(parse_js_payload(payload), "https://example.com/code.png")

    def test_extract_image_asset_id_from_img_url(self) -> None:
        image_url = (
            "https://gw.alicdn.com/imgextra/i2/"
            "O1CN01No3bjS1tzEQxQUg4t_!!6000000005972-2-tps-1773-540.png"
        )
        self.assertEqual(extract_image_asset_id(image_url), "6000000005972")

    def test_extract_image_asset_id_rejects_unknown_pattern(self) -> None:
        with self.assertRaises(ValueError):
            extract_image_asset_id("https://example.com/invite.png")


class ExtractInviteCodeTests(unittest.TestCase):
    def test_extract_after_current_invite_label(self) -> None:
        text = "活动开始\n当前邀请码：WUKONG2026\n请尽快使用"
        self.assertEqual(extract_invite_code(text), "WUKONG2026")

    def test_extract_with_plain_invite_label(self) -> None:
        text = "邀请码 ABCD1234"
        self.assertEqual(extract_invite_code(text), "ABCD1234")

    def test_extract_standalone_mixed_code_token(self) -> None:
        text = "活动开始\nWUKONG2026\n立即使用"
        self.assertEqual(extract_invite_code(text), "WUKONG2026")

    def test_ignores_plain_count_numbers(self) -> None:
        with self.assertRaises(ValueError):
            extract_invite_code("限量10000个\n已领完")

    def test_rejects_multiple_garbled_tokens(self) -> None:
        with self.assertRaises(ValueError):
            extract_invite_code("2SL8SS FLS2SUL")

    def test_extract_standalone_five_chinese_chars(self) -> None:
        text = "活动开始\n春江花月夜\n立即使用"
        self.assertEqual(extract_invite_code(text), "春江花月夜")

    def test_rejects_known_chinese_ui_text(self) -> None:
        with self.assertRaises(ValueError):
            extract_invite_code("欢迎回来\n立即体验\n已领完")


class VisionOCRTests(unittest.TestCase):
    def test_recognize_text_tries_alpha_candidates(self) -> None:
        ocr = VisionOCR(Path("/tmp/project"))
        alpha_paths = [Path("/tmp/a1.png"), Path("/tmp/a2.png")]
        with (
            patch("wukong_invite.ocr._preprocess_alpha", return_value=alpha_paths),
            patch.object(ocr, "_recognize", side_effect=["", "当前邀请码：金蝉脱凡壳"]),
        ):
            self.assertEqual(ocr.recognize_text(Path("/tmp/original.png")), "当前邀请码：金蝉脱凡壳")


class CreateOCRFactoryTests(unittest.TestCase):
    @patch("wukong_invite.ocr.platform.system", return_value="Darwin")
    def test_darwin_returns_vision_ocr(self, _mock) -> None:
        ocr = create_ocr(Path("/tmp/project"))
        self.assertIsInstance(ocr, VisionOCR)

    @patch("wukong_invite.ocr.platform.system", return_value="Windows")
    def test_windows_returns_tesseract_ocr(self, _mock) -> None:
        ocr = create_ocr(Path("/tmp/project"))
        self.assertIsInstance(ocr, TesseractOCR)

    @patch("wukong_invite.ocr.platform.system", return_value="Linux")
    def test_linux_returns_tesseract_ocr(self, _mock) -> None:
        ocr = create_ocr(Path("/tmp/project"))
        self.assertIsInstance(ocr, TesseractOCR)


class NotifyTests(unittest.TestCase):
    @patch("wukong_invite.notify.platform.system", return_value="Darwin")
    @patch("wukong_invite.notify.subprocess.run")
    @patch("wukong_invite.notify.shutil.which", return_value="/usr/bin/pbcopy")
    def test_copy_to_clipboard_uses_pbcopy(self, _which, run_mock, _platform) -> None:
        copy_to_clipboard("WUKONG2026")
        run_mock.assert_called_once_with(
            ["/usr/bin/pbcopy"],
            input="WUKONG2026",
            text=True,
            check=True,
        )

    @patch("wukong_invite.notify.platform.system", return_value="Darwin")
    @patch("wukong_invite.notify.subprocess.run")
    @patch("wukong_invite.notify.shutil.which", return_value="/usr/bin/afplay")
    def test_play_alert_uses_mac_sound(self, _which, run_mock, _platform) -> None:
        play_alert()
        run_mock.assert_called_once_with(
            ["/usr/bin/afplay", "/System/Library/Sounds/Glass.aiff"],
            check=True,
            stdout=-3,
            stderr=-3,
        )


class OpsTests(unittest.TestCase):
    @patch("wukong_invite.ops.platform.system", return_value="Darwin")
    @patch("wukong_invite.ops.subprocess.run")
    def test_fill_app_runs_osascript_with_submit_enabled(self, run_mock, _platform_mock) -> None:
        self.assertEqual(cmd_fill_app("春江花月夜", no_submit=False), 0)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], "osascript")
        self.assertIn("立即体验", command[2])
        self.assertEqual(command[3], "春江花月夜")

    @patch("wukong_invite.ops.platform.system", return_value="Darwin")
    @patch("wukong_invite.ops.subprocess.run")
    def test_fill_app_runs_osascript_without_submit_when_disabled(self, run_mock, _platform_mock) -> None:
        self.assertEqual(cmd_fill_app("春江花月夜", no_submit=True), 0)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], "osascript")
        self.assertNotIn("立即体验", command[2])
        self.assertEqual(command[3], "春江花月夜")


class SnatchInviteScriptTests(unittest.TestCase):
    def test_snatch_invite_logs_progress_during_polling(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()

            self._write_executable(
                fake_bin / "curl",
                """#!/usr/bin/env bash
exit 1
""",
            )
            self._write_executable(
                fake_bin / "sleep",
                """#!/usr/bin/env bash
exit 0
""",
            )
            self._write_executable(
                fake_bin / "date",
                """#!/usr/bin/env bash
state_file="${TMPDIR:-/tmp}/wukong_test_fake_date_state"
count=0
if [ -f "$state_file" ]; then
  count="$(cat "$state_file")"
fi
count=$((count + 1))
printf '%s' "$count" > "$state_file"
if [ "$1" = "+%s" ]; then
  if [ "$count" -eq 1 ]; then
    printf '100\\n'
  elif [ "$count" -eq 2 ]; then
    printf '100\\n'
  else
    printf '101\\n'
  fi
  exit 0
fi
printf 'unsupported fake date args: %s\\n' "$*" >&2
exit 1
""",
            )

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["INTERVAL"] = "0"
            env["TIMEOUT_SECONDS"] = "1"
            env["TMPDIR"] = temp_dir

            result = subprocess.run(
                ["bash", "scripts/snatch_invite.sh"],
                cwd=project_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("starting watcher", result.stderr)
        self.assertIn("poll attempt #1", result.stderr)
        self.assertIn("timeout without invite code", result.stderr)

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()

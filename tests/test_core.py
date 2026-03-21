import unittest
from pathlib import Path
from unittest.mock import patch

from wukong_invite.core import extract_invite_code, parse_js_payload
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ocr import VisionOCR


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
            patch.object(ocr, "_preprocess_alpha", return_value=alpha_paths),
            patch.object(ocr, "_recognize_vision", side_effect=["", "当前邀请码：金蝉脱凡壳"]),
        ):
            self.assertEqual(ocr.recognize_text(Path("/tmp/original.png")), "当前邀请码：金蝉脱凡壳")


class NotifyTests(unittest.TestCase):
    @patch("wukong_invite.notify.subprocess.run")
    @patch("wukong_invite.notify.shutil.which", return_value="/usr/bin/pbcopy")
    def test_copy_to_clipboard_uses_pbcopy(self, _which, run_mock) -> None:
        copy_to_clipboard("WUKONG2026")
        run_mock.assert_called_once_with(
            ["/usr/bin/pbcopy"],
            input="WUKONG2026",
            text=True,
            check=True,
        )

    @patch("wukong_invite.notify.subprocess.run")
    @patch("wukong_invite.notify.shutil.which", return_value="/usr/bin/afplay")
    def test_play_alert_uses_mac_sound(self, _which, run_mock) -> None:
        play_alert()
        run_mock.assert_called_once_with(
            ["/usr/bin/afplay", "/System/Library/Sounds/Glass.aiff"],
            check=True,
            stdout=-3,
            stderr=-3,
        )


if __name__ == "__main__":
    unittest.main()

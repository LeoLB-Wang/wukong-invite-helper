import unittest
import os
import stat
import subprocess
import tempfile
import io
import json
import threading
import time
import importlib
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from wukong_invite.core import (
    extract_image_asset_id,
    extract_invite_code,
    parse_invite_api_payload,
    parse_js_payload,
)
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ops import cmd_fill_app
from wukong_invite.ocr import VisionOCR, TesseractOCR, _preprocess_alpha, create_ocr
from wukong_invite import cli


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


class ParseInviteApiPayloadTests(unittest.TestCase):
    def test_parse_ready_code_from_json_payload(self) -> None:
        payload = '{"code":"春江花月夜"}'

        result = parse_invite_api_payload(payload)

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.code, "春江花月夜")
        self.assertIsNone(result.next_release_at)

    def test_parse_waiting_status_when_code_is_not_five_chinese_chars(self) -> None:
        payload = (
            '{"code":"__WUKONG_INVITE_CODE_EXHAUSTED__",'
            '"nextReleaseAt":"2026-04-02T02:00:00.000Z"}'
        )

        result = parse_invite_api_payload(payload)

        self.assertEqual(result.status, "waiting")
        self.assertIsNone(result.code)
        self.assertEqual(result.raw_code, "__WUKONG_INVITE_CODE_EXHAUSTED__")
        self.assertEqual(result.next_release_at, "2026-04-02T02:00:00.000Z")


class CliHttpTests(unittest.TestCase):
    def test_fetch_text_uses_python_http_client(self) -> None:
        response = unittest.mock.MagicMock()
        response.read.return_value = "img_url({})".encode("utf-8")
        response.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value = response
        response.__exit__.return_value = None

        with patch("wukong_invite.cli.urlopen", return_value=response) as urlopen_mock:
            text = cli.fetch_text("https://example.com/invite.js")

        self.assertEqual(text, "img_url({})")
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.com/invite.js")
        self.assertEqual(request.headers["User-agent"], cli.USER_AGENT)
        self.assertEqual(request.headers["Cache-control"], "no-cache")

    def test_download_file_uses_python_http_client(self) -> None:
        response = unittest.mock.MagicMock()
        response.read.return_value = b"fake-image"
        response.headers.get_content_charset.return_value = None
        response.__enter__.return_value = response
        response.__exit__.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "invite.png"
            with patch(
                "wukong_invite.cli.urlopen", return_value=response
            ) as urlopen_mock:
                cli.download_file("https://example.com/invite.png", target)

            self.assertEqual(target.read_bytes(), b"fake-image")
            request = urlopen_mock.call_args.args[0]
            self.assertEqual(request.full_url, "https://example.com/invite.png")
            self.assertEqual(request.headers["User-agent"], cli.USER_AGENT)
            self.assertEqual(request.headers["Cache-control"], "no-cache")


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

    def test_extract_labelled_five_chinese_chars_with_windows_style_spaces(
        self,
    ) -> None:
        text = "当 前 邀 请 码 ： 春 江 花 月 夜"
        self.assertEqual(extract_invite_code(text), "春江花月夜")

    def test_extract_standalone_five_chinese_chars_with_windows_style_spaces(
        self,
    ) -> None:
        text = "活动开始\n春 江 花 月 夜\n立即使用"
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
            self.assertEqual(
                ocr.recognize_text(Path("/tmp/original.png")), "当前邀请码：金蝉脱凡壳"
            )

    def test_preprocess_alpha_emits_mac_style_upper_crop_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.png"
            Image.new("RGBA", (100, 100), (255, 255, 255, 0)).save(image_path)

            candidates = _preprocess_alpha(image_path, Path(temp_dir))
            names = {path.name for path in candidates}

            self.assertIn("upper_gray_default_4x.png", names)
            self.assertIn("upper_gray_soft_4x.png", names)
            self.assertIn("upper_gray_contrast_4x.png", names)
            self.assertIn("upper_gray_threshold_240_6x.png", names)
            self.assertIn("upper_gray_threshold_245_6x.png", names)
            self.assertIn("upper_gray_threshold_250_6x.png", names)

            default_candidate = next(path for path in candidates if path.name == "upper_gray_default_4x.png")
            threshold_candidate = next(
                path for path in candidates if path.name == "upper_gray_threshold_240_6x.png"
            )
            with Image.open(default_candidate) as default_image:
                self.assertEqual(default_image.size, (216, 80))
            with Image.open(threshold_candidate) as threshold_image:
                self.assertEqual(threshold_image.size, (324, 120))

    def test_preprocess_alpha_gray_background_candidate_avoids_black_background(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.png"
            image = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
            image.putpixel((25, 5), (255, 255, 255, 160))
            image.save(image_path)

            candidates = _preprocess_alpha(image_path, Path(temp_dir))
            default_candidate = next(path for path in candidates if path.name == "upper_gray_default_4x.png")
            processed = Image.open(default_candidate).convert("L")

            self.assertGreater(processed.getpixel((0, 0)), 0)


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
    def test_ops_module_import_does_not_require_ocr_dependency(self) -> None:
        import builtins
        import sys

        real_import = builtins.__import__
        sys.modules.pop("wukong_invite.ops", None)

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "wukong_invite.ocr":
                raise ModuleNotFoundError("mock missing ocr dependency")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=guarded_import):
            ops_module = importlib.import_module("wukong_invite.ops")

        self.assertTrue(hasattr(ops_module, "cmd_fill_app"))

    @patch("wukong_invite.autofill.fill_and_submit")
    def test_fill_app_delegates_to_autofill_with_submit(self, fill_mock) -> None:
        self.assertEqual(cmd_fill_app("春江花月夜", no_submit=False), 0)
        fill_mock.assert_called_once_with("春江花月夜", submit=True)

    @patch("wukong_invite.autofill.fill_and_submit")
    def test_fill_app_delegates_to_autofill_without_submit(self, fill_mock) -> None:
        self.assertEqual(cmd_fill_app("春江花月夜", no_submit=True), 0)
        fill_mock.assert_called_once_with("春江花月夜", submit=False)

    def test_fill_app_returns_1_when_autofill_missing(self) -> None:
        with patch.dict("sys.modules", {"wukong_invite.autofill": None}):
            result = cmd_fill_app("CODE123", no_submit=False)
        self.assertEqual(result, 1)

    @patch(
        "wukong_invite.autofill.fill_and_submit",
        side_effect=RuntimeError("mock autofill failure"),
    )
    def test_fill_app_returns_1_when_autofill_fails(self, _fill_mock) -> None:
        with patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = cmd_fill_app("春江花月夜", no_submit=False)
        self.assertEqual(result, 1)
        self.assertIn("mock autofill failure", stderr.getvalue())


class AutofillTests(unittest.TestCase):
    @patch("wukong_invite.autofill.subprocess.run")
    @patch("wukong_invite.autofill.copy_to_clipboard")
    @patch("wukong_invite.autofill.platform.system", return_value="Darwin")
    def test_fill_macos_sends_osascript_with_submit(
        self, _sys, clip_mock, run_mock
    ) -> None:
        from wukong_invite.autofill import fill_and_submit

        run_mock.return_value.returncode = 0
        run_mock.return_value.stderr = ""
        fill_and_submit("WUKONG2026", submit=True)
        clip_mock.assert_called_once_with("WUKONG2026")
        run_mock.assert_called_once()
        script = run_mock.call_args.args[0][2]
        self.assertIn('keystroke "v" using command down', script)
        self.assertIn("keystroke return", script)

    @patch("wukong_invite.autofill.subprocess.run")
    @patch("wukong_invite.autofill.copy_to_clipboard")
    @patch("wukong_invite.autofill.platform.system", return_value="Darwin")
    def test_fill_macos_sends_osascript_without_submit(
        self, _sys, clip_mock, run_mock
    ) -> None:
        from wukong_invite.autofill import fill_and_submit

        run_mock.return_value.returncode = 0
        run_mock.return_value.stderr = ""
        fill_and_submit("WUKONG2026", submit=False)
        clip_mock.assert_called_once_with("WUKONG2026")
        run_mock.assert_called_once()
        script = run_mock.call_args.args[0][2]
        self.assertIn('keystroke "v" using command down', script)
        self.assertNotIn("keystroke return", script)

    @patch("wukong_invite.autofill.subprocess.run")
    @patch("wukong_invite.autofill.copy_to_clipboard")
    @patch("wukong_invite.autofill.platform.system", return_value="Darwin")
    def test_fill_macos_raises_after_restoring_clipboard_on_failure(
        self, _sys, clip_mock, run_mock
    ) -> None:
        from wukong_invite.autofill import fill_and_submit

        run_mock.return_value.returncode = 1
        run_mock.return_value.stderr = "mock osascript denied"
        with self.assertRaisesRegex(RuntimeError, "mock osascript denied"):
            fill_and_submit("WUKONG2026", submit=True)
        self.assertEqual(clip_mock.call_count, 2)

    @patch("wukong_invite.autofill.time.sleep")
    @patch("wukong_invite.autofill.activate_wukong_window")
    @patch("wukong_invite.autofill.copy_to_clipboard")
    @patch("wukong_invite.autofill.platform.system", return_value="Windows")
    def test_fill_pyautogui_hotkey_sequence_windows(
        self, _sys, clip_mock, activate_mock, sleep_mock
    ) -> None:
        pyautogui = unittest.mock.Mock()
        with patch.dict("sys.modules", {"pyautogui": pyautogui}):
            from wukong_invite.autofill import fill_and_submit

            fill_and_submit("WUKONG2026", submit=True)
        clip_mock.assert_called_once_with("WUKONG2026")
        activate_mock.assert_called_once()
        pyautogui.hotkey.assert_any_call("ctrl", "a")
        pyautogui.hotkey.assert_any_call("ctrl", "v")
        pyautogui.press.assert_called_once_with("enter")


class WatchTests(unittest.TestCase):
    def test_watch_returns_direct_code_when_json_payload_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            with (
                patch(
                    "wukong_invite.cli.fetch_text",
                    return_value='{"code":"春江花月夜"}',
                ),
                patch("wukong_invite.cli.copy_to_clipboard") as copy_mock,
                patch("wukong_invite.cli.play_alert") as alert_mock,
                patch("wukong_invite.cli.cmd_fill_app", return_value=0) as fill_mock,
                patch("wukong_invite.cli.time.time", side_effect=[100.0, 100.1]),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = cli.watch(
                    js_url="https://example.com/invite-code",
                    interval=0,
                    timeout_seconds=1,
                    project_root=project_root,
                    seen_ids_file=seen_ids_file,
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "春江花月夜\n")
        copy_mock.assert_called_once_with("春江花月夜")
        alert_mock.assert_called_once_with("Glass")
        fill_mock.assert_called_once_with("春江花月夜", no_submit=False)
        self.assertIn("invite code ready [春江花月夜]", stderr.getvalue())

    def test_watch_retries_until_next_release_window_opens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            with (
                patch(
                    "wukong_invite.cli.fetch_text",
                    side_effect=[
                        '{"code":"__WUKONG_INVITE_CODE_EXHAUSTED__",'
                        '"nextReleaseAt":"2026-04-02T02:00:00.000Z"}',
                        '{"code":"春江花月夜"}',
                    ],
                ),
                patch("wukong_invite.cli.time.sleep") as sleep_mock,
                patch("wukong_invite.cli.copy_to_clipboard"),
                patch("wukong_invite.cli.play_alert"),
                patch("wukong_invite.cli.cmd_fill_app", return_value=0),
                patch(
                    "wukong_invite.cli.time.time",
                    side_effect=[100.0, 100.1, 100.2],
                ),
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = cli.watch(
                    js_url="https://example.com/invite-code",
                    interval=0,
                    timeout_seconds=1,
                    project_root=project_root,
                    seen_ids_file=seen_ids_file,
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "春江花月夜\n")
        sleep_mock.assert_called_once_with(0)

    def test_watch_logs_autofill_error_when_fill_app_returns_non_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            with (
                patch(
                    "wukong_invite.cli.fetch_text",
                    return_value='{"code":"春江花月夜"}',
                ),
                patch("wukong_invite.cli.copy_to_clipboard"),
                patch("wukong_invite.cli.play_alert"),
                patch("wukong_invite.cli.cmd_fill_app", return_value=1),
                patch("wukong_invite.cli.time.time", side_effect=[100.0, 100.1]),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                exit_code = cli.watch(
                    js_url="https://example.com/invite-code",
                    interval=0,
                    timeout_seconds=1,
                    project_root=project_root,
                    seen_ids_file=seen_ids_file,
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("autofill error", stderr.getvalue())

    def test_watch_times_out_while_waiting_for_next_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            with (
                patch(
                    "wukong_invite.cli.fetch_text",
                    side_effect=[
                        '{"code":"__WUKONG_INVITE_CODE_EXHAUSTED__",'
                        '"nextReleaseAt":"2026-04-02T02:00:00.000Z"}',
                        '{"code":"__WUKONG_INVITE_CODE_EXHAUSTED__",'
                        '"nextReleaseAt":"2026-04-02T02:00:00.000Z"}',
                    ],
                ),
                patch("wukong_invite.cli.time.sleep"),
                patch(
                    "wukong_invite.cli.time.time",
                    side_effect=[100.0, 100.1, 101.2],
                ),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = cli.watch(
                    js_url="https://example.com/invite-code",
                    interval=0,
                    timeout_seconds=1,
                    project_root=project_root,
                    seen_ids_file=seen_ids_file,
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("2026-04-02T02:00:00.000Z", stderr.getvalue())


class WebWatchServiceTests(unittest.TestCase):
    def test_manual_retry_returns_direct_code_from_json_payload(self) -> None:
        from wukong_invite.webui import InviteWatchService

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                fetch_text_func=lambda _url: '{"code":"春江花月夜"}',
                notify_func=lambda _code: None,
            )

            result = service.retry_now()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["code"], "春江花月夜")
        self.assertEqual(service.snapshot()["latest_code"], "春江花月夜")
        self.assertEqual(service.snapshot()["last_result"], "ok")

    def test_manual_retry_reports_waiting_until_next_release(self) -> None:
        from wukong_invite.webui import InviteWatchService

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                fetch_text_func=lambda _url: (
                    '{"code":"__WUKONG_INVITE_CODE_EXHAUSTED__",'
                    '"nextReleaseAt":"2026-04-02T02:00:00.000Z"}'
                ),
                notify_func=lambda _code: None,
            )

            result = service.retry_now()

        self.assertEqual(result["status"], "waiting")
        self.assertEqual(result["next_release_at"], "2026-04-02T02:00:00.000Z")
        self.assertEqual(service.snapshot()["last_result"], "waiting")

    def test_start_and_stop_toggle_running_state(self) -> None:
        from wukong_invite.webui import InviteWatchService

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                interval=0.01,
                fetch_text_func=lambda _url: (
                    '{"code":"__WUKONG_INVITE_CODE_EXHAUSTED__",'
                    '"nextReleaseAt":"2026-04-02T02:00:00.000Z"}'
                ),
                notify_func=lambda _code: None,
            )

            self.assertTrue(service.start())
            self.assertTrue(service.snapshot()["running"])
            self.assertTrue(service.stop())
            self.assertFalse(service.snapshot()["running"])


class WebAPITests(unittest.TestCase):
    def test_http_api_supports_state_start_stop_and_retry(self) -> None:
        from wukong_invite.webui import InviteWatchService, create_http_server

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                interval=0.01,
                fetch_text_func=lambda _url: '{"code":"春江花月夜"}',
                notify_func=lambda _code: None,
            )

            server = create_http_server("127.0.0.1", 0, service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address

            try:
                state = self._request_json(host, port, "GET", "/api/state")
                self.assertFalse(state["running"])

                start = self._request_json(host, port, "POST", "/api/start")
                self.assertEqual(start["status"], "ok")

                stop = self._request_json(host, port, "POST", "/api/stop")
                self.assertEqual(stop["status"], "ok")

                retry_result = self._request_json(host, port, "POST", "/api/retry")
                self.assertEqual(retry_result["status"], "ok")
                self.assertEqual(retry_result["code"], "春江花月夜")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

    def test_root_page_includes_copy_button_and_success_banner(self) -> None:
        from wukong_invite.webui import InviteWatchService, create_http_server

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"
            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                fetch_text_func=lambda _url: "",
                notify_func=lambda _code: None,
            )
            server = create_http_server("127.0.0.1", 0, service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address

            try:
                conn = HTTPConnection(host, port, timeout=2)
                conn.request("GET", "/")
                response = conn.getresponse()
                body = response.read().decode("utf-8")
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

        self.assertEqual(response.status, 200)
        self.assertIn("复制邀请码", body)
        self.assertIn("successBanner", body)
        self.assertIn("countdownValue", body)
        self.assertIn("lastSuccessAt", body)
        self.assertIn("toast", body)
        self.assertIn('class="card wide"', body)
        self.assertIn("logs.scrollTop = logs.scrollHeight", body)
        self.assertIn("setButtonLoading", body)
        self.assertIn("renderLogs", body)
        self.assertLess(body.index("停止监听"), body.index("手动重试"))
        self.assertIn("console-panel", body)
        self.assertIn("console-actions", body)
        self.assertIn("开始监听后会按设定间隔持续轮询邀请码接口", body)
        self.assertIn("停止监听后会结束后台轮询", body)
        self.assertIn("手动重试会立即重新请求当前邀请码接口", body)
        self.assertIn("status-pill", body)
        self.assertIn("status-running", body)
        self.assertIn("status-stopped", body)

    def _request_json(
        self, host: str, port: int, method: str, path: str, payload: dict | None = None
    ) -> dict:
        conn = HTTPConnection(host, port, timeout=2)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()
        self.assertEqual(response.status, 200, msg=data)
        return json.loads(data)


class SnatchInviteScriptTests(unittest.TestCase):
    def test_snatch_invite_logs_progress_during_polling(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()

            self._write_executable(
                fake_bin / "curl",
                """#!/usr/bin/env bash
printf '%s' '{"code":"__WUKONG_INVITE_CODE_EXHAUSTED__","nextReleaseAt":"2026-04-02T02:00:00.000Z"}'
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
        self.assertIn("next release at 2026-04-02T02:00:00.000Z", result.stderr)
        self.assertIn("timeout without invite code", result.stderr)

    def test_snatch_invite_returns_direct_code_after_json_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            scripts_dir = project_root / "scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            source_script = (
                Path(__file__).resolve().parents[1] / "scripts" / "snatch_invite.sh"
            )
            script_content = source_script.read_text().replace(
                'PYTHON_BIN="$(command -v python)"\n'
                'if [[ "$PYTHON_BIN" != "$ROOT_DIR/.venv/"* ]]; then\n'
                '  echo "python is not using project .venv: $PYTHON_BIN" >&2\n'
                "  exit 1\n"
                "fi\n",
                'PYTHON_BIN="$(command -v python)"\n',
            )
            (scripts_dir / "snatch_invite.sh").write_text(script_content)
            (scripts_dir / "snatch_invite.sh").chmod(
                stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            )

            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True, exist_ok=True)
            (project_root / ".venv" / "bin" / "activate").write_text(
                f'export PATH="{venv_bin}:$PATH"\n'
            )
            self._write_executable(
                venv_bin / "python",
                """#!/usr/bin/env bash
if [ "$1" = "-m" ] && [ "$2" = "wukong_invite.ops" ]; then
  shift 2
  case "$1" in
    parse-api)
      if [ "$2" = "--field" ] && [ "$3" = "code" ]; then
        printf '%s\n' '春江花月夜'
        exit 0
      fi
      if [ "$2" = "--field" ] && [ "$3" = "next-release" ]; then
        exit 0
      fi
      if [ "$2" = "--field" ] && [ "$3" = "raw-code" ]; then
        exit 0
      fi
      exit 1
      ;;
    notify|fill-app)
      exit 0
      ;;
  esac
fi
exit 1
""",
            )

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()

            self._write_executable(
                fake_bin / "curl",
                """#!/usr/bin/env bash
printf '%s' '{"code":"春江花月夜"}'
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
if [ "$1" = "+%s" ]; then
  state_file="${TMPDIR:-/tmp}/wukong_test_fake_date_success_state"
  count=0
  if [ -f "$state_file" ]; then
    count="$(cat "$state_file")"
  fi
  count=$((count + 1))
  printf '%s' "$count" > "$state_file"
  printf '100\\n'
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
            env["ENABLE_CLIPBOARD"] = "0"
            env["ENABLE_SOUND"] = "0"
            env["AUTO_FILL_APP"] = "0"

            result = subprocess.run(
                ["bash", "scripts/snatch_invite.sh"],
                cwd=project_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("春江花月夜", result.stdout)
        self.assertIn("invite code ready [春江花月夜]", result.stderr)

    def test_start_bat_is_ascii_only_for_cmd_compatibility(self) -> None:
        launcher = Path(__file__).resolve().parents[1] / "start.bat"
        try:
            launcher.read_bytes().decode("ascii")
        except UnicodeDecodeError as exc:
            self.fail(
                f"start.bat must stay ASCII-only for cmd.exe compatibility: {exc}"
            )

    def test_start_bat_uses_crlf_line_endings(self) -> None:
        launcher = Path(__file__).resolve().parents[1] / "start.bat"
        raw = launcher.read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_start_bat_avoids_fragile_batch_constructs(self) -> None:
        launcher = Path(__file__).resolve().parents[1] / "start.bat"
        text = launcher.read_bytes().decode("ascii")
        self.assertNotIn("::", text)
        self.assertNotIn("enabledelayedexpansion", text.lower())

    def test_start_bat_launches_module_instead_of_console_script(self) -> None:
        launcher = Path(__file__).resolve().parents[1] / "start.bat"
        text = launcher.read_bytes().decode("ascii")
        self.assertIn('set "UV_CACHE_DIR=%CD%\\.uv-cache"', text)
        self.assertIn('set "UV_LINK_MODE=copy"', text)
        self.assertIn(
            'uv sync --link-mode copy --cache-dir "%UV_CACHE_DIR%" --no-editable --no-install-project',
            text,
        )
        self.assertNotIn("--extra rapidocr", text)
        self.assertIn('set "PYTHONPATH=%CD%\\src"', text)
        self.assertIn(
            "echo [warn] First dependency sync failed. Retrying once...", text
        )
        self.assertIn('".venv\\Scripts\\python.exe" -m wukong_invite.webui', text)
        self.assertNotIn("uv run wukong-invite-webui", text)
        self.assertNotIn("uv run python -m wukong_invite.webui", text)

    def test_start_command_launches_module_instead_of_console_script(self) -> None:
        launcher = (Path(__file__).resolve().parents[1] / "start.command").read_text(
            encoding="utf-8"
        )
        self.assertIn('UV_CACHE_DIR="$PWD/.uv-cache"', launcher)
        self.assertIn('UV_LINK_MODE="${UV_LINK_MODE:-copy}"', launcher)
        self.assertIn(
            'uv sync --link-mode copy --cache-dir "$UV_CACHE_DIR" --no-editable --no-install-project',
            launcher,
        )
        self.assertIn(
            'export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"', launcher
        )
        self.assertIn("First dependency sync failed. Retrying once", launcher)
        self.assertIn(".venv/bin/python -m wukong_invite.webui", launcher)
        self.assertNotIn("uv run wukong-invite-webui", launcher)
        self.assertNotIn("uv run python -m wukong_invite.webui", launcher)

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()

import unittest
import os
import stat
import subprocess
import tempfile
import io
import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from wukong_invite.core import extract_image_asset_id, extract_invite_code, parse_js_payload
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ops import cmd_fill_app
from wukong_invite.ocr import VisionOCR, TesseractOCR, create_ocr
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


class AutofillTests(unittest.TestCase):
    @patch("wukong_invite.autofill.subprocess.run")
    @patch("wukong_invite.autofill.copy_to_clipboard")
    @patch("wukong_invite.autofill.platform.system", return_value="Darwin")
    def test_fill_macos_sends_osascript_with_submit(self, _sys, clip_mock, run_mock) -> None:
        from wukong_invite.autofill import fill_and_submit
        fill_and_submit("WUKONG2026", submit=True)
        clip_mock.assert_called_once_with("WUKONG2026")
        run_mock.assert_called_once()
        script = run_mock.call_args.args[0][2]
        self.assertIn('keystroke "v" using command down', script)
        self.assertIn("keystroke return", script)

    @patch("wukong_invite.autofill.subprocess.run")
    @patch("wukong_invite.autofill.copy_to_clipboard")
    @patch("wukong_invite.autofill.platform.system", return_value="Darwin")
    def test_fill_macos_sends_osascript_without_submit(self, _sys, clip_mock, run_mock) -> None:
        from wukong_invite.autofill import fill_and_submit
        fill_and_submit("WUKONG2026", submit=False)
        clip_mock.assert_called_once_with("WUKONG2026")
        run_mock.assert_called_once()
        script = run_mock.call_args.args[0][2]
        self.assertIn('keystroke "v" using command down', script)
        self.assertNotIn("keystroke return", script)

    @patch("wukong_invite.autofill.time.sleep")
    @patch("wukong_invite.autofill.activate_wukong_window")
    @patch("wukong_invite.autofill.copy_to_clipboard")
    @patch("wukong_invite.autofill.platform.system", return_value="Windows")
    def test_fill_pyautogui_hotkey_sequence_windows(self, _sys, clip_mock, activate_mock, sleep_mock) -> None:
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
    def test_watch_processes_current_asset_if_not_in_seen_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"
            seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
            seen_ids_file.write_text("6000000001111\n")

            ocr = unittest.mock.Mock()
            ocr.recognize_text.return_value = "当前邀请码：春江花月夜"

            with (
                patch("wukong_invite.cli.create_ocr", return_value=ocr),
                patch(
                    "wukong_invite.cli.fetch_text",
                    return_value='img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01Latest_!!6000000009999-2-tps-1773-540.png"})',
                ),
                patch("wukong_invite.cli.download_file"),
                patch("wukong_invite.cli.copy_to_clipboard") as copy_mock,
                patch("wukong_invite.cli.play_alert") as alert_mock,
                patch("wukong_invite.cli.cmd_fill_app", return_value=0) as fill_mock,
                patch("wukong_invite.cli.time.time", side_effect=[100.0, 100.1, 100.2, 101.1]),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = cli.watch(
                    js_url="https://example.com/invite.js",
                    interval=0,
                    timeout_seconds=1,
                    project_root=project_root,
                    seen_ids_file=seen_ids_file,
                )
                seen_ids_content = seen_ids_file.read_text()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "春江花月夜\n")
        copy_mock.assert_called_once_with("春江花月夜")
        alert_mock.assert_called_once_with("Glass")
        fill_mock.assert_called_once_with("春江花月夜", no_submit=False)
        self.assertEqual(seen_ids_content, "6000000001111\n6000000009999\n")
        self.assertIn("saved seen asset id [6000000009999]", stderr.getvalue())

    def test_watch_retries_same_new_asset_when_ocr_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"
            seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
            seen_ids_file.write_text("6000000001111\n")

            ocr = unittest.mock.Mock()
            ocr.recognize_text.side_effect = RuntimeError("ocr failed")

            with (
                patch("wukong_invite.cli.create_ocr", return_value=ocr),
                patch(
                    "wukong_invite.cli.fetch_text",
                    side_effect=[
                        'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01NewAsset_!!6000000009999-2-tps-1773-540.png"})',
                        'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01NewAsset_!!6000000009999-2-tps-1773-540.png"})',
                    ],
                ),
                patch("wukong_invite.cli.download_file"),
                patch("wukong_invite.cli.time.sleep"),
                patch("wukong_invite.cli.time.time", side_effect=[100.0, 100.1, 100.2, 101.1]),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = cli.watch(
                    js_url="https://example.com/invite.js",
                    interval=0,
                    timeout_seconds=1,
                    project_root=project_root,
                    seen_ids_file=seen_ids_file,
                )
                seen_ids_content = seen_ids_file.read_text()

        self.assertEqual(exit_code, 1)
        self.assertEqual(seen_ids_content, "6000000001111\n")
        self.assertEqual(ocr.recognize_text.call_count, 2)
        self.assertIn("timeout without invite code", stderr.getvalue())

    def test_watch_prints_and_triggers_notify_and_fill_on_new_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"
            seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
            seen_ids_file.write_text("6000000001111\n")

            ocr = unittest.mock.Mock()
            ocr.recognize_text.return_value = "当前邀请码：春江花月夜"

            with (
                patch("wukong_invite.cli.create_ocr", return_value=ocr),
                patch(
                    "wukong_invite.cli.fetch_text",
                    side_effect=[
                        'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01NewAsset_!!6000000009999-2-tps-1773-540.png"})',
                    ],
                ),
                patch("wukong_invite.cli.download_file"),
                patch("wukong_invite.cli.copy_to_clipboard", create=True) as copy_mock,
                patch("wukong_invite.cli.play_alert", create=True) as alert_mock,
                patch("wukong_invite.cli.cmd_fill_app", return_value=0, create=True) as fill_mock,
                patch("wukong_invite.cli.time.time", side_effect=[100.0, 100.1]),
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = cli.watch(
                    js_url="https://example.com/invite.js",
                    interval=0,
                    timeout_seconds=1,
                    project_root=project_root,
                    seen_ids_file=seen_ids_file,
                )
                seen_ids_content = seen_ids_file.read_text()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "春江花月夜\n")
        copy_mock.assert_called_once_with("春江花月夜")
        alert_mock.assert_called_once_with("Glass")
        fill_mock.assert_called_once_with("春江花月夜", no_submit=False)
        self.assertEqual(seen_ids_content, "6000000001111\n6000000009999\n")


class WebWatchServiceTests(unittest.TestCase):
    def test_manual_retry_processes_current_seen_asset_after_clear(self) -> None:
        from wukong_invite.webui import InviteWatchService

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"
            seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
            seen_ids_file.write_text("6000000009999\n")

            ocr = unittest.mock.Mock()
            ocr.recognize_text.return_value = "当前邀请码：春江花月夜"

            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                fetch_text_func=lambda _url: 'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01Latest_!!6000000009999-2-tps-1773-540.png"})',
                download_file_func=lambda _url, _path: None,
                create_ocr_func=lambda _root: ocr,
                notify_func=lambda _code: None,
            )

            self.assertTrue(service.clear_seen_id("6000000009999"))
            result = service.retry_now()
            seen_ids_content = seen_ids_file.read_text()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["code"], "春江花月夜")
        self.assertEqual(seen_ids_content, "6000000009999\n")
        self.assertEqual(service.snapshot()["latest_code"], "春江花月夜")

    def test_start_and_stop_toggle_running_state(self) -> None:
        from wukong_invite.webui import InviteWatchService

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"

            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                interval=0.01,
                fetch_text_func=lambda _url: 'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01Seen_!!6000000001111-2-tps-1773-540.png"})',
                download_file_func=lambda _url, _path: None,
                create_ocr_func=lambda _root: unittest.mock.Mock(),
                notify_func=lambda _code: None,
            )

            self.assertTrue(service.start())
            self.assertTrue(service.snapshot()["running"])
            self.assertTrue(service.stop())
            self.assertFalse(service.snapshot()["running"])


class WebAPITests(unittest.TestCase):
    def test_http_api_supports_state_start_stop_retry_and_clear(self) -> None:
        from wukong_invite.webui import InviteWatchService, create_http_server

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            seen_ids_file = project_root / "data" / "seen_ids.txt"
            seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
            seen_ids_file.write_text("6000000009999\n")

            ocr = unittest.mock.Mock()
            ocr.recognize_text.return_value = "当前邀请码：春江花月夜"

            service = InviteWatchService(
                project_root=project_root,
                seen_ids_file=seen_ids_file,
                interval=0.01,
                fetch_text_func=lambda _url: 'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01Latest_!!6000000009999-2-tps-1773-540.png"})',
                download_file_func=lambda _url, _path: None,
                create_ocr_func=lambda _root: ocr,
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

                cleared = self._request_json(
                    host,
                    port,
                    "POST",
                    "/api/clear-seen-id",
                    {"asset_id": "6000000009999"},
                )
                self.assertEqual(cleared["status"], "ok")

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
                download_file_func=lambda _url, _path: None,
                create_ocr_func=lambda _root: unittest.mock.Mock(),
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
        self.assertLess(body.index("已处理 seen_id"), body.index("最近日志"))
        self.assertIn("logs.scrollTop = logs.scrollHeight", body)
        self.assertIn("setButtonLoading", body)
        self.assertIn("renderLogs", body)
        self.assertIn("showToast('已清空 seen_id", body)
        self.assertLess(body.index("停止监听"), body.index("手动重试"))
        self.assertIn("console-panel", body)
        self.assertIn("console-actions", body)
        self.assertIn("开始监听后会按设定间隔持续轮询最新图片", body)
        self.assertIn("停止监听后会结束后台轮询", body)
        self.assertIn("手动重试会立即对当前最新图片再执行一次 OCR 和提取流程", body)
        self.assertIn("清空指定 seen_id 后，当前 asset_id 会重新变成可处理状态", body)
        self.assertIn("status-pill", body)
        self.assertIn("status-running", body)
        self.assertIn("status-stopped", body)

    def _request_json(self, host: str, port: int, method: str, path: str, payload: dict | None = None) -> dict:
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

    def test_snatch_invite_does_not_persist_seen_id_when_extract_fails(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()

            self._write_executable(
                fake_bin / "curl",
                """#!/usr/bin/env bash
state_file="${TMPDIR:-/tmp}/wukong_test_fake_curl_state"
count=0
if [ -f "$state_file" ]; then
  count="$(cat "$state_file")"
fi
count=$((count + 1))
printf '%s' "$count" > "$state_file"
if [ "$1" = "-fsSL" ] && [ "$4" = "-o" ]; then
  printf 'fake image' > "$5"
  exit 0
fi
if [ "$count" -eq 1 ]; then
  printf '%s' 'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01SeedAsset_!!6000000001111-2-tps-1773-540.png"})'
else
  printf '%s' 'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01TestAsset_!!6000000009999-2-tps-1773-540.png"})'
fi
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
  if [ "$count" -le 3 ]; then
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

            seen_ids_file = Path(temp_dir) / "seen_ids.txt"

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["INTERVAL"] = "0"
            env["TIMEOUT_SECONDS"] = "1"
            env["TMPDIR"] = temp_dir
            env["SEEN_IDS_FILE"] = str(seen_ids_file)

            with patch("wukong_invite.ops.cmd_extract_code", side_effect=ValueError("ocr failed")):
                result = subprocess.run(
                    ["bash", "scripts/snatch_invite.sh"],
                    cwd=project_root,
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            seen_ids_content = seen_ids_file.read_text() if seen_ids_file.exists() else ""

        self.assertEqual(result.returncode, 1)
        self.assertNotIn("6000000001111", seen_ids_content)
        self.assertNotIn("6000000009999", seen_ids_content)

    def test_snatch_invite_persists_seen_id_and_logs_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            scripts_dir = project_root / "scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            source_script = Path(__file__).resolve().parents[1] / "scripts" / "snatch_invite.sh"
            script_content = source_script.read_text().replace(
                'PYTHON_BIN="$(command -v python)"\n'
                'if [[ "$PYTHON_BIN" != "$ROOT_DIR/.venv/"* ]]; then\n'
                '  echo "python is not using project .venv: $PYTHON_BIN" >&2\n'
                '  exit 1\n'
                'fi\n',
                'PYTHON_BIN="$(command -v python)"\n',
            )
            (scripts_dir / "snatch_invite.sh").write_text(script_content)
            (scripts_dir / "snatch_invite.sh").chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

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
    parse-js)
      printf '%s\n' 'https://gw.alicdn.com/imgextra/i2/O1CN01SuccessAsset_!!6000000009999-2-tps-1773-540.png'
      exit 0
      ;;
    image-key)
      printf '%s\n' '6000000009999'
      exit 0
      ;;
    extract-code)
      printf '%s\n' '春江花月夜'
      exit 0
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
if [ "$1" = "-fsSL" ] && [ "$4" = "-o" ]; then
  printf 'fake image' > "$5"
  exit 0
fi
printf '%s' 'img_url({"img_url":"https://gw.alicdn.com/imgextra/i2/O1CN01SuccessAsset_!!6000000009999-2-tps-1773-540.png"})'
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

            seen_ids_file = Path(temp_dir) / "seen_ids.txt"

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["INTERVAL"] = "0"
            env["TIMEOUT_SECONDS"] = "1"
            env["TMPDIR"] = temp_dir
            env["SEEN_IDS_FILE"] = str(seen_ids_file)
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
            seen_ids_content = seen_ids_file.read_text() if seen_ids_file.exists() else ""

        self.assertEqual(result.returncode, 0)
        self.assertIn("春江花月夜", result.stdout)
        self.assertIn("6000000009999", seen_ids_content)
        self.assertIn("saved seen asset id [6000000009999]", result.stderr)

    def test_start_bat_is_ascii_only_for_cmd_compatibility(self) -> None:
        launcher = Path(__file__).resolve().parents[1] / "start.bat"
        try:
            launcher.read_bytes().decode("ascii")
        except UnicodeDecodeError as exc:
            self.fail(f"start.bat must stay ASCII-only for cmd.exe compatibility: {exc}")

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
        self.assertIn("uv sync --no-editable --extra tesseract", text)
        self.assertIn('".venv\\Scripts\\python.exe" -m wukong_invite.webui', text)
        self.assertNotIn("uv run wukong-invite-webui", text)
        self.assertNotIn("uv run python -m wukong_invite.webui", text)

    def test_start_command_launches_module_instead_of_console_script(self) -> None:
        launcher = (Path(__file__).resolve().parents[1] / "start.command").read_text()
        self.assertIn("uv sync --no-editable", launcher)
        self.assertIn('.venv/bin/python -m wukong_invite.webui', launcher)
        self.assertNotIn("uv run wukong-invite-webui", launcher)
        self.assertNotIn("uv run python -m wukong_invite.webui", launcher)

    def test_start_bat_bootstraps_windows_tesseract(self) -> None:
        launcher = Path(__file__).resolve().parents[1] / "start.bat"
        text = launcher.read_bytes().decode("ascii")
        self.assertIn("winget install -e --id UB-Mannheim.TesseractOCR", text)
        self.assertIn("chi_sim.traineddata", text)
        self.assertIn('set "TESSDATA_DIR=%LOCALAPPDATA%\\wukong-invite-helper\\tessdata"', text)
        self.assertIn('set "TESSDATA_PREFIX=%TESSDATA_DIR%"', text)

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()

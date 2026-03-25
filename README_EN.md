# wukong-invite-helper

[中文](./README.md) | English

A lightweight watcher for Wukong invite images. It polls the official endpoint, OCRs unseen invite images, alerts on success, copies the invite code to the clipboard, and autofills `Wukong App` across platforms.

> [!IMPORTANT]
> Before using, download the [Wukong App](https://wukong.com), log in via DingTalk QR scan, and stay on the invite code input page.  **Click inside the invite-code input field so the cursor is active** — the autofill script sends keystrokes to whatever is focused and cannot click the field for you.

## One-Click Launch (Recommended)

No need to manually install Python or any dependencies — just double-click.

The script automatically handles: install uv → install Python → create venv → install deps → launch Web UI → open browser.

**macOS**

Double-click `start.command` (first run: right-click → Open → click "Open" to confirm)

**Windows**

Double-click `start.bat`

> First launch downloads dependencies (~1-2 min); subsequent launches are instant.

### macOS Accessibility Permission

To enable the "autofill Wukong App" feature, grant Accessibility permission to your terminal app:

`System Settings → Privacy & Security → Accessibility` → check your terminal app

### Windows Extra Dependencies

On Windows, double-clicking `start.bat` will try to install Tesseract OCR automatically and place the `chi_sim` language data in a user-writable directory.

If `winget` / App Installer is unavailable, the script will stop with a clear error so you can install Tesseract manually.

## Command Line Launch

For users who prefer the terminal. Scripts also auto-install `uv` and configure the environment.

### Web UI Mode

```bash
bash start.command
```

### CLI Watcher Mode

```bash
bash scripts/snatch_invite.sh
```

Custom parameters:

```bash
TIMEOUT_SECONDS=330 INTERVAL=0.5 bash scripts/snatch_invite.sh
```

Disable autofill / fill without submit:

```bash
AUTO_FILL_APP=0 bash scripts/snatch_invite.sh    # disable autofill
AUTO_SUBMIT_APP=0 bash scripts/snatch_invite.sh  # fill only, no submit
```

## Manual Install (Developers)

For local development or debugging:

```bash
# 1. Create and activate venv
uv venv .venv
source .venv/bin/activate          # macOS / Linux
# source .venv/Scripts/activate    # Windows Git Bash

# 2. Install project (choose by platform)
uv pip install -e .                        # macOS
# uv pip install -e ".[tesseract]"         # Windows / Linux
# uv pip install -e ".[tesseract,autofill]" # Windows / Linux + autofill

# 3. Launch Web UI
uv run wukong-invite-webui --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787` in your browser.

## Platform Support

| Capability | macOS | Windows (Git Bash / MSYS2) | Linux |
|---|---|---|---|
| OCR engine | Vision Framework | Tesseract | Tesseract |
| Clipboard | `pbcopy` | `clip.exe` | `xclip` / `xsel` |
| Alert sound | `afplay` | `winsound` | terminal bell |
| Autofill Wukong App | osascript + System Events | pyautogui | pyautogui |

## How It Works

1. Poll the official JS endpoint:

```text
https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js
```

2. Parse the payload and extract the latest image URL:

```text
img_url({"img_url":"https://gw.alicdn.com/imgextra/...png"})
```

3. Extract the numeric `asset_id` from the image URL.
4. Compare the `asset_id` against `data/seen_ids.txt`.
5. If unseen, download the image and run OCR.
6. If OCR succeeds:
   - Print the invite code
   - Copy to clipboard
   - Play an alert
   - Autofill Wukong App and submit
   - Append `asset_id` to `data/seen_ids.txt`
7. If OCR fails, keep the `asset_id` eligible for retry.

## `seen_ids.txt` Behavior

`data/seen_ids.txt` stores processed invite image IDs, one per line.

- Only successful OCR results are persisted
- Failed OCR does not mark the `asset_id` as seen
- Manually deleting an `asset_id` makes that image eligible for reprocessing

## Configuration

CLI Watcher is configured via environment variables (`scripts/snatch_invite.sh`):

| Variable | Default | Meaning |
|---|---|---|
| `INTERVAL` | `1` | Poll interval in seconds |
| `TIMEOUT_SECONDS` | `300` | Max watcher runtime |
| `ENABLE_CLIPBOARD` | `1` | Copy invite code to clipboard |
| `ENABLE_SOUND` | `1` | Play alert sound |
| `SOUND_NAME` | `Glass` | macOS alert sound name |
| `AUTO_FILL_APP` | `1` | Autofill Wukong App |
| `AUTO_SUBMIT_APP` | `1` | Press Enter after filling |
| `SEEN_IDS_FILE` | `data/seen_ids.txt` | Override seen-id storage file |

## OCR Strategy

OCR implementation: `src/wukong_invite/ocr.py`.

- Preprocess image via alpha compositing
- Try OCR on candidate preprocessed images first
- Fall back to OCR on the original image
- macOS: `VisionOCR`
- Non-macOS: `TesseractOCR`

Invite code extraction: `src/wukong_invite/core.py`.

- Prefer labeled text like `当前邀请码：xxxxx` or `邀请码：xxxxx`
- Accept a unique 5-character Chinese token if no label found
- Filter known UI text like `已领完`, `欢迎回来`, `立即体验`
- Mixed alphanumeric fallback for older formats

## Common Commands

```bash
# OCR a local image
uv run python -m wukong_invite.ops extract-code --image scratch/wukong-new.png

# Test autofill (no submit)
uv run python -m wukong_invite.ops fill-app --code 春江花月夜 --no-submit

# Test autofill + submit
uv run python -m wukong_invite.ops fill-app --code 春江花月夜

# Run tests
uv run python -m unittest discover -s tests
```

## Troubleshooting

| Symptom | What to check |
|---|---|
| No invite code printed | Check if `asset_id` is already in `data/seen_ids.txt`; delete the line to force retry |
| OCR keeps failing | Faint white text / image format changed / missing Tesseract Chinese data on non-macOS |
| macOS autofill not working | Confirm Terminal has Accessibility permission; confirm Wukong App is open with input field visible |
| Windows autofill not working | Confirm pyautogui is installed; confirm window title contains "Wukong" |
| `python is not using project .venv` | Re-run `uv venv .venv && source .venv/bin/activate && uv pip install -e .` |

## Verification

```bash
uv run python -m unittest discover -s tests
```

Current local test suite: `25` tests, all passing.

## Project Structure

- `start.command`: macOS one-click launcher (double-click)
- `start.bat`: Windows one-click launcher (double-click)
- `scripts/snatch_invite.sh`: CLI watcher entrypoint
- `src/wukong_invite/webui.py`: Web UI server
- `src/wukong_invite/core.py`: payload parsing and invite-code extraction
- `src/wukong_invite/ocr.py`: OCR engines and preprocessing
- `src/wukong_invite/autofill.py`: cross-platform autofill (macOS osascript / Windows pyautogui)
- `src/wukong_invite/ops.py`: operational CLI helpers
- `src/wukong_invite/cli.py`: Python watcher entrypoint
- `tests/test_core.py`: unit tests

## Known Limitations

- OCR accuracy depends on invite image quality
- macOS autofill requires osascript + Accessibility permission
- Windows/Linux autofill requires pyautogui (extra install)

## License

Licensed under the [MIT License](./LICENSE).

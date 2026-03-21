# wukong-invite-helper

[中文](./README.md) | English

A lightweight watcher for Wukong invite images. It polls the official endpoint, OCRs unseen invite images, alerts on success, copies the invite code to the clipboard, and can autofill `Wukong.app` on macOS.

## TL;DR

- Poll the official `.js` endpoint and parse the latest invite image URL.
- Process only unseen `asset_id` values recorded in `data/seen_ids.txt`.
- After OCR succeeds, print the invite code, alert the user, copy it to the clipboard, try to fill `Wukong.app`, and persist the processed `asset_id`.

## Features

- Parse JSONP-like invite image payloads such as `img_url({...})`
- Track processed invite images via `data/seen_ids.txt`
- OCR invite images on macOS and non-macOS platforms
- Copy invite codes to the clipboard
- Play a local alert sound
- Autofill `Wukong.app` on macOS with AppleScript
- Retry the same unseen image if OCR fails
- Provide a local `Web UI` with start, stop, clear-seen-id, and manual retry controls

## Platform Support

| Capability | macOS | Windows (Git Bash / MSYS2) | Linux |
|---|---|---|---|
| OCR engine | Vision Framework | Tesseract | Tesseract |
| Clipboard | `pbcopy` | `clip.exe` | `xclip` / `xsel` |
| Alert sound | `afplay` | `winsound` | terminal bell |
| Autofill `Wukong.app` | Yes | No | No |

## Requirements

### Common

- Python `3.11+`
- [uv](https://docs.astral.sh/uv/)

### macOS

- Xcode Command Line Tools
- Accessibility permission for Terminal / iTerm and `Wukong.app` automation if you want autofill
  Path:
  `System Settings -> Privacy & Security -> Accessibility`
  On older macOS versions:
  `System Preferences -> Security & Privacy -> Privacy -> Accessibility`

### Windows

- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- Chinese language data `chi_sim`
- Git Bash or MSYS2

If `tessdata` is not installed in the default location, set `TESSDATA_PREFIX`.

## Installation

### 1. Create the local virtual environment

```bash
uv venv .venv
```

### 2. Activate the environment

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows Git Bash / MSYS2:

```bash
source .venv/Scripts/activate
```

### 3. Install the project

macOS:

```bash
uv pip install -e .
```

Windows / Linux with Tesseract:

```bash
uv pip install -e ".[tesseract]"
```

## Quick Start

### macOS

```bash
TIMEOUT_SECONDS=330 INTERVAL=0.5 AUTO_FILL_APP=1 AUTO_SUBMIT_APP=0 ENABLE_SOUND=1 bash scripts/snatch_invite.sh
```

### Windows

`fill-app` is skipped automatically:

```bash
TIMEOUT_SECONDS=330 INTERVAL=0.5 AUTO_FILL_APP=0 ENABLE_SOUND=1 bash scripts/snatch_invite.sh
```

### Start the local Web UI

```bash
source .venv/bin/activate
uv run python -m wukong_invite.webui --host 127.0.0.1 --port 8787
```

After installation, you can also run:

```bash
source .venv/bin/activate
uv run wukong-invite-webui --host 127.0.0.1 --port 8787
```

Open in your browser:

```text
http://127.0.0.1:8787
```

## How It Works

1. Poll the official JS endpoint:

```text
https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js
```

2. Parse the payload and extract the latest image URL:

```text
img_url({"img_url":"https://gw.alicdn.com/imgextra/...png"})
```

3. Extract the numeric invite image `asset_id` from the image URL.
4. Compare the `asset_id` against `data/seen_ids.txt`.
5. If the `asset_id` is unseen, download the image and run OCR.
6. If OCR succeeds:
   - print the invite code
   - copy it to the clipboard
   - play an alert
   - try to autofill `Wukong.app` on macOS
   - append the `asset_id` to `data/seen_ids.txt`
7. If OCR fails, keep the `asset_id` eligible for retry.

## `seen_ids.txt` Behavior

The file `data/seen_ids.txt` stores processed invite image IDs, one per line.

Important behavior:

- Only successful OCR results are persisted
- Failed OCR does not mark the `asset_id` as seen
- If you delete an `asset_id` manually, the current image becomes eligible for processing again

Successful persistence logs look like this:

```text
[wukong-invite-helper] saved seen asset id [6000000009999] to /path/to/data/seen_ids.txt
```

## Configuration

The main entrypoint is `scripts/snatch_invite.sh`.

| Variable | Default | Meaning |
|---|---|---|
| `INTERVAL` | `1` | Poll interval in seconds |
| `TIMEOUT_SECONDS` | `300` | Max watcher runtime |
| `ENABLE_CLIPBOARD` | `1` | Copy invite code to clipboard |
| `ENABLE_SOUND` | `1` | Play alert sound |
| `SOUND_NAME` | `Glass` | macOS sound name |
| `AUTO_FILL_APP` | `1` | Try to autofill `Wukong.app` on macOS |
| `AUTO_SUBMIT_APP` | `0` | Click `立即体验` after filling |
| `SEEN_IDS_FILE` | `data/seen_ids.txt` | Override the seen-id storage file |

## OCR Strategy

OCR implementation lives in `src/wukong_invite/ocr.py`.

Current behavior:

- Preprocess the input image by compositing alpha onto a black background
- Try OCR on generated candidate images first
- Fall back to OCR on the original image
- Use `VisionOCR` on macOS
- Use `TesseractOCR` on non-macOS platforms

Invite code parsing lives in `src/wukong_invite/core.py`.

Current extraction rules:

- Prefer labeled text such as `当前邀请码：xxxxx` or `邀请码：xxxxx`
- If no label exists, accept a unique 5-character Chinese token
- Filter known UI text such as `已领完`, `欢迎回来`, `立即体验`
- Keep a mixed alphanumeric fallback for older formats

## Commands

### Run the full watcher

```bash
bash scripts/snatch_invite.sh
```

### Start the Web UI

```bash
source .venv/bin/activate
uv run python -m wukong_invite.webui
```

### Parse the image URL from stdin

```bash
source .venv/bin/activate
uv run python -m wukong_invite.ops parse-js
```

### Extract the invite code from a local image

```bash
source .venv/bin/activate
uv run python -m wukong_invite.ops extract-code --image scratch/wukong-new.png
```

### Fill `Wukong.app` only

```bash
source .venv/bin/activate
uv run python -m wukong_invite.ops fill-app --code 春江花月夜 --no-submit
```

## Troubleshooting

### No invite code is printed

Check:

- whether the latest image is actually new
- whether the current `asset_id` is already present in `data/seen_ids.txt`
- whether OCR can extract text from the current image

To force reprocessing, delete the corresponding line from `data/seen_ids.txt`.

### OCR fails repeatedly

Common causes:

- the white text is too faint
- the invite image format changed
- `Tesseract` Chinese language data is missing on non-macOS systems

### `Wukong.app` is not filled on macOS

Check:

- `Wukong.app` is installed
- the underlying process is still `DingTalkReal`
- Terminal has Accessibility permission
- the invite page is open and contains an editable text field

### `python is not using project .venv`

The shell script requires the local environment. Re-run:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .
```

## Verification

Run tests:

```bash
source .venv/bin/activate
uv run python -m unittest discover -s tests
```

At the time of writing, the local suite passes with `25` tests.

## Project Structure

- `scripts/snatch_invite.sh`: main watcher entrypoint
- `src/wukong_invite/core.py`: payload parsing and invite-code extraction
- `src/wukong_invite/ocr.py`: OCR engines and preprocessing flow
- `src/wukong_invite/ops.py`: operational CLI helpers
- `src/wukong_invite/cli.py`: Python watcher entrypoint
- `tests/test_core.py`: unit tests

## Known Limitations

- OCR accuracy depends on the invite image quality
- `Wukong.app` autofill is macOS-only
- UI automation depends on the current app structure and process name

## License

This project is licensed under the [MIT License](./LICENSE).

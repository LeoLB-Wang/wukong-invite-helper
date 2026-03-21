# wukong-invite-helper

中文 | [English](./README_EN.md)

一个轻量的悟空邀请码图片 watcher。它会轮询官方接口，针对未处理过的邀请码图片执行 OCR，在识别成功后发出提示、复制邀请码到剪贴板，并跨平台自动填入悟空 App。

## TL;DR

- 轮询官方 `.js` 接口并解析最新邀请码图片地址。
- 仅处理 `data/seen_ids.txt` 中尚未记录的 `asset_id`。
- OCR 成功后输出邀请码、发出提示、复制到剪贴板、自动填入悟空 App 并提交，并持久化对应的 `asset_id`。

## 功能特性

- 解析 `img_url({...})` 这类 JSONP 风格响应
- 通过 `data/seen_ids.txt` 跟踪已处理的邀请码图片
- 在 macOS 和非 macOS 平台执行 OCR
- 自动复制邀请码到剪贴板
- 播放本地提示音
- 跨平台自动填入悟空 App（macOS 使用 osascript，Windows/Linux 使用 pyautogui）
- OCR 失败时允许同一张未成功图片继续重试
- 提供本地 `Web UI`，支持开始监听、停止监听、清空指定 `seen_id`、手动重试

## 平台支持

| 功能 | macOS | Windows (Git Bash / MSYS2) | Linux |
|---|---|---|---|
| OCR 引擎 | Vision Framework | Tesseract | Tesseract |
| 剪贴板 | `pbcopy` | `clip.exe` | `xclip` / `xsel` |
| 提示音 | `afplay` | `winsound` | terminal bell |
| 自动填入悟空 App | osascript + System Events | pyautogui | pyautogui |

## 环境要求

### 通用

- Python `3.11+`
- [uv](https://docs.astral.sh/uv/)

### macOS

- Xcode Command Line Tools
- 自动填入需为 Terminal / iTerm 打开辅助功能权限
  路径：`系统设置 -> 隐私与安全性 -> 辅助功能`
  老版本 macOS：`系统偏好设置 -> 安全性与隐私 -> 隐私 -> 辅助功能`

### Windows

- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- 中文语言数据 `chi_sim`
- Git Bash 或 MSYS2

如果 `tessdata` 不在默认目录，需要配置 `TESSDATA_PREFIX`。

## 安装

### 1. 创建本地虚拟环境

```bash
uv venv .venv
```

### 2. 激活环境

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows Git Bash / MSYS2:

```bash
source .venv/Scripts/activate
```

### 3. 安装项目

macOS:

```bash
uv pip install -e .
```

Windows / Linux:

```bash
uv pip install -e ".[tesseract]"
```

如需自动填入悟空 App（Windows/Linux），额外安装 `autofill`：

```bash
uv pip install -e ".[tesseract,autofill]"
```

## 快速开始

```bash
TIMEOUT_SECONDS=330 INTERVAL=0.5 bash scripts/snatch_invite.sh
```

默认行为：自动填入 + 自动提交。如需禁用，设置对应变量为 `0`：

```bash
AUTO_FILL_APP=0 bash scripts/snatch_invite.sh    # 禁用自动填入
AUTO_SUBMIT_APP=0 bash scripts/snatch_invite.sh  # 仅填入不提交
```

### 启动本地 Web UI

```bash
source .venv/bin/activate
uv run python -m wukong_invite.webui --host 127.0.0.1 --port 8787
```

安装为可执行命令后，也可以直接运行：

```bash
source .venv/bin/activate
uv run wukong-invite-webui --host 127.0.0.1 --port 8787
```

打开浏览器访问：

```text
http://127.0.0.1:8787
```

## 工作原理

1. 轮询官方 JS 接口：

```text
https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js
```

2. 解析响应，提取最新图片地址：

```text
img_url({"img_url":"https://gw.alicdn.com/imgextra/...png"})
```

3. 从图片 URL 中提取数值型 `asset_id`。
4. 将该 `asset_id` 与 `data/seen_ids.txt` 进行比对。
5. 如果该 `asset_id` 未处理过，则下载图片并执行 OCR。
6. 如果 OCR 成功：
   - 输出邀请码
   - 复制到剪贴板
   - 播放提示音
   - 自动填入悟空 App 并提交
   - 将 `asset_id` 追加写入 `data/seen_ids.txt`
7. 如果 OCR 失败，则不标记为已处理，允许后续继续重试。

## `seen_ids.txt` 说明

文件 `data/seen_ids.txt` 用于保存已经成功处理过的邀请码图片 ID，一行一个。

关键行为：

- 只有 OCR 成功后，才会写入该文件
- OCR 失败不会把该 `asset_id` 标记为已处理
- 如果你手动删除某个 `asset_id`，当前图片会重新变成可处理状态

成功写入时会输出类似日志：

```text
[wukong-invite-helper] saved seen asset id [6000000009999] to /path/to/data/seen_ids.txt
```

## 配置项

主入口是 `scripts/snatch_invite.sh`。

| 变量 | 默认值 | 含义 |
|---|---|---|
| `INTERVAL` | `1` | 轮询间隔，单位秒 |
| `TIMEOUT_SECONDS` | `300` | watcher 最长运行时间 |
| `ENABLE_CLIPBOARD` | `1` | 是否复制邀请码到剪贴板 |
| `ENABLE_SOUND` | `1` | 是否播放提示音 |
| `SOUND_NAME` | `Glass` | macOS 提示音名称 |
| `AUTO_FILL_APP` | `1` | 是否自动填入悟空 App |
| `AUTO_SUBMIT_APP` | `1` | 填入后是否自动回车提交 |
| `SEEN_IDS_FILE` | `data/seen_ids.txt` | 自定义 seen-id 存储文件 |

## OCR 策略

OCR 实现在 `src/wukong_invite/ocr.py`。

当前行为：

- 先对输入图片做 alpha 合成预处理
- 优先对候选预处理图执行 OCR
- 再 fallback 到原图 OCR
- macOS 使用 `VisionOCR`
- 非 macOS 使用 `TesseractOCR`

邀请码提取逻辑在 `src/wukong_invite/core.py`。

当前提取规则：

- 优先匹配 `当前邀请码：xxxxx` 或 `邀请码：xxxxx`
- 无标签时，接受唯一的 5 个中文字符 token
- 过滤已知 UI 文案，如 `已领完`、`欢迎回来`、`立即体验`
- 保留早期 mixed alphanumeric fallback 以兼容旧格式

## 常用命令

### 运行完整 watcher

```bash
bash scripts/snatch_invite.sh
```

### 启动 Web UI

```bash
source .venv/bin/activate
uv run python -m wukong_invite.webui
```

### 从 stdin 解析图片 URL

```bash
source .venv/bin/activate
uv run python -m wukong_invite.ops parse-js
```

### 对本地图片执行 OCR

```bash
source .venv/bin/activate
uv run python -m wukong_invite.ops extract-code --image scratch/wukong-new.png
```

### 测试自动填入（不提交）

```bash
source .venv/bin/activate
uv run python -m wukong_invite.ops fill-app --code 春江花月夜 --no-submit
```

### 测试自动填入 + 提交

```bash
source .venv/bin/activate
uv run python -m wukong_invite.ops fill-app --code 春江花月夜
```

## 故障排查

### 没有输出邀请码

请优先检查：

- 当前图片是否确实是新的
- 当前 `asset_id` 是否已经在 `data/seen_ids.txt` 中
- OCR 是否能从当前图片中提取出文本

如果要强制重新处理当前图片，可以删除 `data/seen_ids.txt` 中对应的那一行。

### OCR 连续失败

常见原因：

- 图片上的白色文字太淡
- 邀请图片版式发生变化
- 非 macOS 平台缺少 `Tesseract` 中文语言数据

### 自动填入不生效

**macOS**：
- 确认 Terminal / iTerm 已有辅助功能权限
- 确认 `Wukong.app` 已打开且邀请码输入框可见

**Windows/Linux**：
- 确认已安装 `pyautogui`：`uv pip install -e ".[autofill]"`
- 确认悟空 App 窗口标题包含 "Wukong"

### 出现 `python is not using project .venv`

说明 shell 脚本没有使用项目本地环境。重新执行：

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .
```

## 验证

运行测试：

```bash
source .venv/bin/activate
uv run python -m unittest discover -s tests
```

当前本地测试套件为 `25` 个测试，已通过。

## 项目结构

- `scripts/snatch_invite.sh`：主 watcher 入口
- `src/wukong_invite/core.py`：响应解析与邀请码提取
- `src/wukong_invite/ocr.py`：OCR 引擎与预处理流程
- `src/wukong_invite/autofill.py`：跨平台自动填入（macOS osascript / Windows pyautogui）
- `src/wukong_invite/ops.py`：操作型 CLI helper
- `src/wukong_invite/cli.py`：Python watcher 入口
- `tests/test_core.py`：单元测试

## 已知限制

- OCR 识别率依赖当前图片质量
- macOS 自动填入依赖 osascript + 辅助功能权限
- Windows/Linux 自动填入依赖 pyautogui（需额外安装）

## License

本项目使用 [MIT License](./LICENSE)。

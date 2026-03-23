# wukong-invite-helper

中文 | [English](./README_EN.md)

一个轻量的悟空邀请码图片 watcher。它会轮询官方接口，针对未处理过的邀请码图片执行 OCR，在识别成功后发出提示、复制邀请码到剪贴板，并跨平台自动填入悟空 App。

> [!IMPORTANT]
> 使用前请先下载 [悟空 App](https://wukong.dingtalk.com/)，通过钉钉扫码完成登录，并停留在邀请码输入页面。

## 一键启动（推荐）

无需手动安装 Python 或任何依赖，双击即跑。脚本会自动完成：安装 uv → 安装 Python → 创建虚拟环境 → 安装依赖 → 启动 Web UI → 打开浏览器。


**macOS**

双击 `start.command`（首次运行需右键 → 打开 → 点"打开"确认）

**Windows**

双击 `start.bat`

> 首次启动需下载依赖，约 1-2 分钟；之后秒开。

### macOS 辅助功能权限

如需「自动填入悟空 App」功能，需为 Terminal / iTerm 打开辅助功能权限：

`系统设置 → 隐私与安全性 → 辅助功能` → 勾选你的终端 App

### Windows 额外依赖

Windows 双击 `start.bat` 时会自动尝试安装 Tesseract OCR，并把中文语言数据 `chi_sim` 下载到当前用户可写目录。

若系统缺少 `winget` / App Installer，脚本会提示后退出；此时再手动安装 Tesseract 即可。

## 命令行启动

适合习惯终端操作的用户。脚本同样会自动安装 `uv` 和配置环境。

### Web UI 模式

```bash
bash start.command
```

### CLI Watcher 模式

```bash
bash scripts/snatch_invite.sh
```

自定义参数：

```bash
TIMEOUT_SECONDS=330 INTERVAL=0.5 bash scripts/snatch_invite.sh
```

禁用自动填入 / 仅填入不提交：

```bash
AUTO_FILL_APP=0 bash scripts/snatch_invite.sh    # 禁用自动填入
AUTO_SUBMIT_APP=0 bash scripts/snatch_invite.sh  # 仅填入不提交
```

## 手动安装（开发者）

如需本地开发或调试，可手动搭建环境：

```bash
# 1. 创建并激活虚拟环境
uv venv .venv
source .venv/bin/activate          # macOS / Linux
# source .venv/Scripts/activate    # Windows Git Bash

# 2. 安装项目（按平台选择）
uv pip install -e .                        # macOS
# uv pip install -e ".[tesseract]"         # Windows / Linux
# uv pip install -e ".[tesseract,autofill]" # Windows / Linux + 自动填入

# 3. 启动 Web UI
uv run wukong-invite-webui --host 127.0.0.1 --port 8787
```

浏览器访问 `http://127.0.0.1:8787`

## 一键启动（推荐）

无需手动安装 Python 或任何依赖，双击即跑。脚本会自动完成：安装 uv → 安装 Python → 创建虚拟环境 → 安装依赖 → 启动 Web UI → 打开浏览器。

**macOS**

双击 `start.command`（首次运行需右键 → 打开 → 点"打开"确认）

**Windows**

双击 `start.bat`

> 首次启动需下载依赖，约 1-2 分钟；之后秒开。

### macOS 辅助功能权限

如需「自动填入悟空 App」功能，需为 Terminal / iTerm 打开辅助功能权限：

`系统设置 → 隐私与安全性 → 辅助功能` → 勾选你的终端 App

### Windows 额外依赖

Windows 双击 `start.bat` 时会自动尝试安装 Tesseract OCR，并补齐中文语言数据 `chi_sim`。

若系统缺少 `winget` / App Installer，脚本会提示后退出；此时再手动安装 Tesseract 即可。

## 命令行启动

适合习惯终端操作的用户。脚本同样会自动安装 `uv` 和配置环境。

### Web UI 模式

```bash
bash start.command
```

### CLI Watcher 模式

```bash
bash scripts/snatch_invite.sh
```

自定义参数：

```bash
TIMEOUT_SECONDS=330 INTERVAL=0.5 bash scripts/snatch_invite.sh
```

禁用自动填入 / 仅填入不提交：

```bash
AUTO_FILL_APP=0 bash scripts/snatch_invite.sh    # 禁用自动填入
AUTO_SUBMIT_APP=0 bash scripts/snatch_invite.sh  # 仅填入不提交
```

## 手动安装（开发者）

如需本地开发或调试，可手动搭建环境：

```bash
# 1. 创建并激活虚拟环境
uv venv .venv
source .venv/bin/activate          # macOS / Linux
# source .venv/Scripts/activate    # Windows Git Bash

# 2. 安装项目（按平台选择）
uv pip install -e .                        # macOS
# uv pip install -e ".[tesseract]"         # Windows / Linux
# uv pip install -e ".[tesseract,autofill]" # Windows / Linux + 自动填入

# 3. 启动 Web UI
uv run wukong-invite-webui --host 127.0.0.1 --port 8787
```

浏览器访问 `http://127.0.0.1:8787`

## 平台支持

| 功能 | macOS | Windows (Git Bash / MSYS2) | Linux |
|---|---|---|---|
| OCR 引擎 | Vision Framework | Tesseract | Tesseract |
| 剪贴板 | `pbcopy` | `clip.exe` | `xclip` / `xsel` |
| 提示音 | `afplay` | `winsound` | terminal bell |
| 自动填入悟空 App | osascript + System Events | pyautogui | pyautogui |

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

CLI Watcher 通过环境变量配置（`scripts/snatch_invite.sh`）：

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

```bash
# 对本地图片执行 OCR
uv run python -m wukong_invite.ops extract-code --image scratch/wukong-new.png

# 测试自动填入（不提交）
uv run python -m wukong_invite.ops fill-app --code 春江花月夜 --no-submit

# 测试自动填入 + 提交
uv run python -m wukong_invite.ops fill-app --code 春江花月夜

# 运行测试
uv run python -m unittest discover -s tests
```

## 故障排查

| 症状 | 排查方向 |
|---|---|
| 没有输出邀请码 | 检查 `asset_id` 是否已在 `data/seen_ids.txt` 中；删除对应行可强制重试 |
| OCR 连续失败 | 白色文字太淡 / 图片版式变化 / 非 macOS 缺少 Tesseract 中文语言数据 |
| macOS 自动填入不生效 | 确认 Terminal 有辅助功能权限；确认悟空 App 已打开且输入框可见 |
| Windows 自动填入不生效 | 确认已安装 pyautogui；确认窗口标题包含 "Wukong" |
| `python is not using project .venv` | 重新执行 `uv venv .venv && source .venv/bin/activate && uv pip install -e .` |

## 验证

```bash
uv run python -m unittest discover -s tests
```

当前本地测试套件为 `25` 个测试，已通过。

## 项目结构

- `start.command`：macOS 一键启动（双击运行）
- `start.bat`：Windows 一键启动（双击运行）
- `scripts/snatch_invite.sh`：CLI watcher 入口
- `src/wukong_invite/webui.py`：Web UI 服务
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

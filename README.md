# wukong-invite-helper

Monitor Wukong invite image updates, extract invite codes with OCR, and optionally autofill the Wukong app on macOS.

## TL;DR

当前工具的目标流程是：

1. 定时请求官网 `.js`
2. 解析最新 `img_url`
3. 当 `img_url` 发生变化时下载新图片
4. 对图片做固定版式预处理
5. 用 `OCR` 提取邀请码
6. 识别成功后自动复制、提醒，并可自动填入 `Wukong.app`

当前状态：

- 抓图链路已验证可用
- `img_url` 更新检测已验证可用
- `Wukong.app` 自动填入链路已验证可用
- OCR 仍在调优中，当前对“5 个中文字符的邀请码”还没有稳定识别成功

## Current Source

官网入口：

```text
https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js?获取图片地址，然后直接张贴
```

返回格式：

```text
img_url({"img_url":"https://gw.alicdn.com/imgextra/...png"})
```

脚本会从这个响应里解析出最新图片地址。

## Current Pipeline

### 1. Poll JS Endpoint

脚本入口：

[`scripts/snatch_invite.sh`](scripts/snatch_invite.sh)

行为：

- 轮询 `.js` 地址
- 解析 `img_url`
- 只有当 `img_url` 变化时，才处理新图

默认环境变量：

```bash
INTERVAL=1
TIMEOUT_SECONDS=300
AUTO_FILL_APP=1
AUTO_SUBMIT_APP=0
ENABLE_CLIPBOARD=1
ENABLE_SOUND=1
SOUND_NAME=Glass
```

### 2. Parse Image URL

解析逻辑：

[`src/wukong_invite/core.py`](src/wukong_invite/core.py)

处理内容：

- 兼容 `img_url({...})` 这类 JSONP 样式返回
- 提取真实图片 URL

### 3. Preprocess Image

预处理逻辑：

[`tools/preprocess_invite_image.m`](tools/preprocess_invite_image.m)

当前预处理假设：

- 图片是固定版式
- 邀请码位于图片上半区
- 邀请码是较淡的白色中文文字

当前会生成多组候选图：

- `upper_white_240`
- `upper_white_245`
- `upper_white_250`
- `upper_tight_white_245`
- `upper_tight_white_250`
- `upper_soft`
- `upper_contrast`
- `upper_wide`

处理方式包括：

- 固定区域裁切
- 灰度化
- 对比度增强
- 白字阈值提取
- 放大

### 4. OCR Strategy

OCR 主逻辑：

[`src/wukong_invite/ocr.py`](src/wukong_invite/ocr.py)

当前顺序：

1. 对候选预处理图优先跑 `Vision OCR`
2. 再对候选预处理图跑 `Tesseract`
3. 最后对整图做兜底 OCR

当前已接入：

- macOS `Vision`
- `Tesseract 5.5.2`

### 5. Invite Code Extraction

提取逻辑：

[`src/wukong_invite/core.py`](src/wukong_invite/core.py)

当前提取规则：

1. 优先匹配：

```text
当前邀请码：xxxxx
邀请码：xxxxx
```

2. 无标签时：

- 优先接受唯一的 `5 个中文字符`
- 会过滤明显 UI 文案：
  - `已领完`
  - `欢迎回来`
  - `立即体验`
  - `退出登录`
  - `刷新验证`
  - `客服咨询`

3. 为兼容早期实验逻辑，仍保留 mixed token 提取，但当前重点目标是 `5 个中文字符`

### 6. Fill Wukong App

App 自动填入逻辑：

[`src/wukong_invite/ops.py`](src/wukong_invite/ops.py)

当前已确认：

- App 路径：
  `/Applications/Wukong.app`
- 真实进程名：
  `DingTalkReal`
- 邀请码页存在可访问的 `text field`
- 可自动把识别结果填入输入框

默认行为：

- 自动填入
- 默认不自动点击 `立即体验`

可开启自动提交：

```bash
AUTO_SUBMIT_APP=1
```

## Commands

### Run Full Flow

```bash
TIMEOUT_SECONDS=330 INTERVAL=0.5 AUTO_FILL_APP=1 AUTO_SUBMIT_APP=0 ENABLE_SOUND=1 bash scripts/snatch_invite.sh
```

### Test URL Parsing

```bash
source .venv/bin/activate
PYTHONPATH=src python -m wukong_invite.ops parse-js
```

### Test OCR on a Local Image

```bash
source .venv/bin/activate
PYTHONPATH=src python -m wukong_invite.ops extract-code --image scratch/wukong-new.png
```

### Test App Fill Only

```bash
source .venv/bin/activate
PYTHONPATH=src python -m wukong_invite.ops fill-app --code 春江花月夜 --no-submit
```

## Verification Status

已验证：

- `.js` 可以正常拉取
- `img_url` 更新可以检测到
- 图片下载正常
- `Wukong.app` Accessibility 自动化可用
- 自动填入邀请码页可用
- `Tesseract` 已安装并接入
- 单元测试当前通过

未解决：

- 对最新样图，OCR 还没有稳定提取出真实的 `5 个中文字符邀请码`

## Current Risk

当前最大的风险不是抓图，而是 OCR 识别率。

也就是说：

- 如果下一张图里邀请码更清晰，当前流程可能直接成功
- 如果下一张图里的白字仍然很淡，仍可能识别失败

## Key Files

- [`README.md`](README.md)
- [`scripts/snatch_invite.sh`](scripts/snatch_invite.sh)
- [`src/wukong_invite/core.py`](src/wukong_invite/core.py)
- [`src/wukong_invite/ocr.py`](src/wukong_invite/ocr.py)
- [`src/wukong_invite/ops.py`](src/wukong_invite/ops.py)
- [`tools/preprocess_invite_image.m`](tools/preprocess_invite_image.m)
- [`tests/test_core.py`](tests/test_core.py)

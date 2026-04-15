# Email Body Cleaner 设计规格

## 问题

`email read` 返回的邮件正文是原始 HTML，包含大量对 LLM 无意义的冗余内容：

- Microsoft Office/Outlook 生成的 `<style>` 块（字体定义、样式规则）
- MS Office 条件注释（`<!--[if !mso]-->` 等）
- XML 命名空间声明（`xmlns:v="urn:schemas-microsoft-com:vml"` 等）
- 内联样式属性（`style="font-family:..."` 等）
- 内联图片的 base64 数据或 `cid:` 引用

这些冗余内容将实际几百字的通知邮件膨胀为数千字的 HTML，直接传给 LLM 极度浪费 token。

## 设计目标

- 默认将邮件正文从 HTML 转换为 Markdown，大幅减少 token 消耗
- 保留文本结构信息（标题、表格、列表、链接）
- 用占位符替代内联图片
- 保留原始 HTML 作为可选输出

## 方案概览

新建独立模块 `content_cleaner.py` 负责 HTML → Markdown 转换，serializer 层默认调用该模块，CLI 通过 `--body-format` 选项提供格式选择。

## 模块设计

### `exchange_cli/core/content_cleaner.py`

核心函数：

```python
def html_to_markdown(html: str) -> str
```

处理流程（按顺序执行）：

#### 1. 预清洗（BeautifulSoup + 正则）

- 移除 `<style>` 和 `<script>` 标签及其内容
- 移除 MS Office 条件注释（`<!--[if ... <![endif]-->`）
- 移除 XML 命名空间声明

#### 2. 图片占位符替换

| 原始 HTML | 替换结果 |
|-----------|----------|
| `<img src="cid:...">` | `[图片: {filename}]`（从 alt 或 src 提取文件名） |
| `<img src="data:image/...;base64,...">` | `[图片: 内嵌图片]` |
| `<img src="https://...">` | `[图片: {alt_or_url}]` |

#### 3. HTML → Markdown 转换

使用 `markdownify` 库，配置：
- `strip` 纯样式标签（`span`、`div`、`font` 等）
- 保留表格、链接、列表、标题等结构

#### 4. 后清洗

- 合并连续空行（3+ 行 → 2 行）
- 去除首尾空白
- 将残留 HTML 实体转为对应字符（`&nbsp;` → 空格等）

### Serializer 改动

`serialize_email_detail` 增加 `body_format` 参数：

```python
def serialize_email_detail(message, body_format="markdown"):
    result = serialize_email_summary(message)
    if body_format == "markdown":
        result["body"] = html_to_markdown(_safe_str(message.body))
    else:
        result["body"] = _safe_str(message.body)
    result["body_format"] = body_format
    result["bcc"] = _serialize_mailbox_list(message.bcc_recipients)
    result["attachments"] = [serialize_attachment_summary(att) for att in (message.attachments or [])]
    return result
```

- 默认 `"markdown"`，LLM 优先
- `"html"` 返回原始 HTML
- 输出 JSON 增加 `body_format` 字段

### CLI 选项

`email read` 新增 `--body-format` 选项：

```
exchange-cli email read MESSAGE_ID                          # 默认 markdown
exchange-cli email read MESSAGE_ID --body-format html       # 原始 HTML
exchange-cli email read MESSAGE_ID --body-format markdown   # 显式指定
```

## 影响范围

| 组件 | 影响 |
|------|------|
| `core/content_cleaner.py` | 新建模块 |
| `core/serializers.py` | `serialize_email_detail` 增加 `body_format` 参数，默认 markdown |
| `commands/email.py` | `email read` 新增 `--body-format` CLI 选项 |
| `core/daemon.py` | 详情序列化同步传递 `body_format`，默认 markdown |
| `pyproject.toml` | 新增 `markdownify`、`beautifulsoup4` 依赖 |

**不改动**：
- `email list` / `email search` — 使用 `serialize_email_summary`，`body_preview` 仍为 `text_body[:200]`
- 附件处理逻辑 — 仅元数据 + `--save-attachments` 落盘
- 输出格式层（`output.py`）

## 边界情况与容错

### 纯文本邮件

检测输入是否为 HTML（包含 `<html`、`<body`、`<div` 等标签）。非 HTML 输入直接返回原文。

### 转换失败兜底

分两层容错：

**content_cleaner 层**：`html_to_markdown` 内部 `try/except` 包裹转换流程，失败时返回原始输入字符串（即未清洗的 HTML），不抛异常。

**serializer 层**：`serialize_email_detail` 中，如果 `html_to_markdown` 返回的结果仍然看起来像 HTML（转换实际失败），fallback 到 `message.text_body`（服务端纯文本版本）；若 `text_body` 也为空，则保留原始 `body`。`--verbose` 模式输出警告。

### 空邮件

`body` 为 `None` 或空字符串时直接返回空字符串。

### 超长邮件

当前不做截断。理由：
- 清洗后 token 量已大幅减少
- 截断策略涉及 LLM 调用侧的上下文管理，不属于 CLI 职责
- 如需扩展，在 `content_cleaner.py` 加 `max_length` 参数即可

## 依赖

- `markdownify >= 0.14`
- `beautifulsoup4 >= 4.12`

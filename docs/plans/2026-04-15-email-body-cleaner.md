# Email Body Cleaner 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将邮件正文从原始 HTML 转换为 Markdown，大幅减少 LLM token 消耗。

**Architecture:** 新建 `content_cleaner.py` 模块负责 HTML → Markdown 转换（预清洗 → 图片占位符 → markdownify 转换 → 后清洗）。serializer 层默认调用该模块，CLI 通过 `--body-format` 选项控制输出格式。

**Tech Stack:** Python, BeautifulSoup4, markdownify, Click

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `exchange_cli/core/content_cleaner.py` | HTML → Markdown 转换 | 新建 |
| `tests/test_content_cleaner.py` | content_cleaner 单元测试 | 新建 |
| `exchange_cli/core/serializers.py` | `serialize_email_detail` 增加 `body_format` 参数 | 修改 |
| `tests/test_serializers.py` | serializer 测试更新 | 修改 |
| `exchange_cli/commands/email.py` | `email read` 增加 `--body-format` 选项 | 修改 |
| `tests/test_email.py` | email read 测试更新 | 修改 |
| `pyproject.toml` | 新增依赖 | 修改 |

---

### Task 1: 添加依赖

**Files:**
- Modify: `pyproject.toml:19-23`

- [ ] **Step 1: 添加 markdownify 和 beautifulsoup4 到 dependencies**

在 `pyproject.toml` 的 `dependencies` 列表中添加两个新依赖：

```toml
dependencies = [
    "click>=8.1,<9",
    "exchangelib>=5.0",
    "cryptography>=41.0",
    "beautifulsoup4>=4.12",
    "markdownify>=0.14",
]
```

- [ ] **Step 2: 安装依赖**

Run: `pip install -e ".[dev]"`
Expected: 成功安装，无报错

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add beautifulsoup4 and markdownify for email body cleaning"
```

---

### Task 2: content_cleaner 核心模块 — 预清洗 + 图片占位符

**Files:**
- Create: `exchange_cli/core/content_cleaner.py`
- Create: `tests/test_content_cleaner.py`

- [ ] **Step 1: 写 test — MS Office 条件注释和 style 标签被移除**

```python
# tests/test_content_cleaner.py
from exchange_cli.core.content_cleaner import html_to_markdown


class TestPreClean:
    def test_removes_style_tags(self):
        html = '<html><head><style>body{color:red;}</style></head><body><p>Hello</p></body></html>'
        result = html_to_markdown(html)
        assert "color:red" not in result
        assert "Hello" in result

    def test_removes_ms_office_conditional_comments(self):
        html = (
            "<html><body>"
            "<!--[if gte mso 9]><xml><o:shapedefaults></o:shapedefaults></xml><![endif]-->"
            "<p>Content</p>"
            "</body></html>"
        )
        result = html_to_markdown(html)
        assert "shapedefaults" not in result
        assert "Content" in result

    def test_removes_script_tags(self):
        html = '<html><body><script>alert("xss")</script><p>Safe</p></body></html>'
        result = html_to_markdown(html)
        assert "alert" not in result
        assert "Safe" in result
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_content_cleaner.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写 test — 图片占位符替换**

在 `tests/test_content_cleaner.py` 中追加：

```python
class TestImagePlaceholders:
    def test_cid_image_with_alt(self):
        html = '<html><body><img src="cid:image001.png" alt="Logo"></body></html>'
        result = html_to_markdown(html)
        assert "[图片: Logo]" in result
        assert "cid:" not in result

    def test_cid_image_without_alt(self):
        html = '<html><body><img src="cid:image001.png@01D00000.00000000"></body></html>'
        result = html_to_markdown(html)
        assert "[图片:" in result
        assert "cid:" not in result

    def test_base64_image(self):
        html = '<html><body><img src="data:image/png;base64,iVBORw0KGgo="></body></html>'
        result = html_to_markdown(html)
        assert "[图片: 内嵌图片]" in result
        assert "base64" not in result

    def test_url_image_with_alt(self):
        html = '<html><body><img src="https://example.com/logo.png" alt="Company Logo"></body></html>'
        result = html_to_markdown(html)
        assert "[图片: Company Logo]" in result

    def test_url_image_without_alt(self):
        html = '<html><body><img src="https://example.com/logo.png"></body></html>'
        result = html_to_markdown(html)
        assert "[图片:" in result
```

- [ ] **Step 4: 实现 content_cleaner.py — 预清洗 + 图片占位符**

```python
# exchange_cli/core/content_cleaner.py
"""Clean HTML email bodies into LLM-friendly Markdown."""

import re

from bs4 import BeautifulSoup

_MS_COMMENT_RE = re.compile(r"<!--\[if[\s\S]*?<!\[endif\]-->", re.IGNORECASE)
_XMLNS_RE = re.compile(r'\s+xmlns:\w+="[^"]*"')
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _is_html(text: str) -> bool:
    return bool(re.search(r"<(?:html|body|div|p|table|br)\b", text, re.IGNORECASE))


def _pre_clean(html: str) -> str:
    html = _MS_COMMENT_RE.sub("", html)
    html = _XMLNS_RE.sub("", html)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()
    return str(soup)


def _replace_images(soup: BeautifulSoup) -> None:
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if src.startswith("data:image"):
            placeholder = "[图片: 内嵌图片]"
        elif src.startswith("cid:"):
            label = alt if alt else src.split("/")[-1].split("@")[0].replace("cid:", "")
            placeholder = f"[图片: {label}]"
        else:
            label = alt if alt else src.split("?")[0].split("/")[-1]
            placeholder = f"[图片: {label}]"
        img.replace_with(placeholder)


def _post_clean(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def html_to_markdown(html: str) -> str:
    if not html:
        return ""
    if not _is_html(html):
        return html
    try:
        import markdownify

        cleaned = _pre_clean(html)
        soup = BeautifulSoup(cleaned, "html.parser")
        _replace_images(soup)
        md = markdownify.markdownify(
            str(soup),
            heading_style="ATX",
            strip=["span", "font"],
        )
        return _post_clean(md)
    except Exception:
        return html
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_content_cleaner.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add exchange_cli/core/content_cleaner.py tests/test_content_cleaner.py
git commit -m "feat: add content_cleaner module with HTML pre-clean and image placeholders"
```

---

### Task 3: content_cleaner — Markdown 转换与边界情况

**Files:**
- Modify: `tests/test_content_cleaner.py`
- Modify: `exchange_cli/core/content_cleaner.py`（如需调整）

- [ ] **Step 1: 写 test — Markdown 结构保留**

在 `tests/test_content_cleaner.py` 中追加：

```python
class TestMarkdownConversion:
    def test_preserves_links(self):
        html = '<html><body><a href="https://example.com">Click here</a></body></html>'
        result = html_to_markdown(html)
        assert "https://example.com" in result
        assert "Click here" in result

    def test_preserves_table_structure(self):
        html = (
            "<html><body><table>"
            "<tr><th>Name</th><th>Value</th></tr>"
            "<tr><td>A</td><td>1</td></tr>"
            "</table></body></html>"
        )
        result = html_to_markdown(html)
        assert "Name" in result
        assert "Value" in result
        assert "|" in result

    def test_preserves_list_structure(self):
        html = "<html><body><ul><li>Item 1</li><li>Item 2</li></ul></body></html>"
        result = html_to_markdown(html)
        assert "Item 1" in result
        assert "Item 2" in result

    def test_preserves_headings(self):
        html = "<html><body><h1>Title</h1><p>Text</p></body></html>"
        result = html_to_markdown(html)
        assert "# Title" in result
        assert "Text" in result
```

- [ ] **Step 2: 运行测试确认通过**

Run: `pytest tests/test_content_cleaner.py::TestMarkdownConversion -v`
Expected: 全部 PASS（实现已在 Task 2 完成）

- [ ] **Step 3: 写 test — 边界情况**

在 `tests/test_content_cleaner.py` 中追加：

```python
class TestEdgeCases:
    def test_empty_input(self):
        assert html_to_markdown("") == ""
        assert html_to_markdown(None) == ""

    def test_plain_text_passthrough(self):
        text = "This is plain text with no HTML tags."
        assert html_to_markdown(text) == text

    def test_collapses_excessive_newlines(self):
        html = "<html><body><p>Line 1</p><br><br><br><br><br><p>Line 2</p></body></html>"
        result = html_to_markdown(html)
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_replaces_nbsp(self):
        html = "<html><body><p>Hello&nbsp;World</p></body></html>"
        result = html_to_markdown(html)
        assert "&nbsp;" not in result
        assert "Hello" in result
        assert "World" in result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_content_cleaner.py::TestEdgeCases -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_content_cleaner.py
git commit -m "test: add markdown structure and edge case tests for content_cleaner"
```

---

### Task 4: 集成到 serializer

**Files:**
- Modify: `exchange_cli/core/serializers.py:53-58`
- Modify: `tests/test_serializers.py:72-77`

- [ ] **Step 1: 写 test — serialize_email_detail 默认输出 markdown**

在 `tests/test_serializers.py` 中，修改现有的 `TestSerializeEmailDetail` 并追加测试：

```python
class TestSerializeEmailDetail:
    def test_default_converts_body_to_markdown(self):
        msg = _mock_message(body="<html><body><p>Hello <b>World</b></p></body></html>")
        result = serialize_email_detail(msg)
        assert "<html>" not in result["body"]
        assert "<p>" not in result["body"]
        assert "Hello" in result["body"]
        assert "World" in result["body"]
        assert result["body_format"] == "markdown"

    def test_html_format_preserves_raw_body(self):
        msg = _mock_message(body="<p>Full body</p>")
        result = serialize_email_detail(msg, body_format="html")
        assert result["body"] == "<p>Full body</p>"
        assert result["body_format"] == "html"

    def test_plain_text_body_passthrough(self):
        msg = _mock_message(body="Just plain text")
        result = serialize_email_detail(msg)
        assert result["body"] == "Just plain text"
        assert result["body_format"] == "markdown"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_serializers.py::TestSerializeEmailDetail -v`
Expected: FAIL（`serialize_email_detail` 还没有 `body_format` 参数）

- [ ] **Step 3: 实现 serializer 改动**

修改 `exchange_cli/core/serializers.py`，在文件顶部添加 import，修改 `serialize_email_detail`：

```python
"""Serialize exchangelib objects to plain dictionaries."""

from .content_cleaner import html_to_markdown


def _safe_str(value):
    # ... 不变 ...
```

将 `serialize_email_detail` 改为：

```python
def serialize_email_detail(message, body_format="markdown"):
    result = serialize_email_summary(message)
    raw_body = _safe_str(message.body)
    if body_format == "markdown" and raw_body:
        result["body"] = html_to_markdown(raw_body)
    else:
        result["body"] = raw_body
    result["body_format"] = body_format
    result["bcc"] = _serialize_mailbox_list(message.bcc_recipients)
    result["attachments"] = [serialize_attachment_summary(att) for att in (message.attachments or [])]
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_serializers.py::TestSerializeEmailDetail -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全部 serializer 测试确认无回归**

Run: `pytest tests/test_serializers.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add exchange_cli/core/serializers.py tests/test_serializers.py
git commit -m "feat: serialize_email_detail defaults to markdown body format"
```

---

### Task 5: CLI 集成 — `--body-format` 选项

**Files:**
- Modify: `exchange_cli/commands/email.py:176-201`
- Modify: `tests/test_email.py:97-108`

- [ ] **Step 1: 写 test — email read 默认用 markdown，支持 --body-format html**

在 `tests/test_email.py` 中，替换 `TestEmailRead`：

```python
class TestEmailRead:
    def test_read_message_default_markdown(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Hello <b>World</b></p></body></html>"
        with patch("exchange_cli.commands.email._find_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["body_format"] == "markdown"
        assert "<html>" not in data["data"]["body"]

    def test_read_message_html_format(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Hello</p></body></html>"
        with patch("exchange_cli.commands.email._find_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123", "--body-format", "html"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["body_format"] == "html"
        assert "<html>" in data["data"]["body"]

    def test_read_not_found(self, runner, mock_conn):
        with patch("exchange_cli.commands.email._find_message", return_value=None):
            result = runner.invoke(cli, ["email", "read", "NONEXISTENT"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["code"] == "NOT_FOUND"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_email.py::TestEmailRead -v`
Expected: FAIL（`--body-format` 选项不存在）

- [ ] **Step 3: 实现 CLI 改动**

修改 `exchange_cli/commands/email.py` 中的 `email_read` 命令，添加 `--body-format` 选项：

```python
@email.command("read")
@click.argument("message_id")
@click.option("--save-attachments", "save_dir", default=None, help="Directory to save attachments")
@click.option(
    "--body-format",
    "body_format",
    default="markdown",
    type=click.Choice(["markdown", "html"]),
    help="Body output format (default: markdown)",
)
@click.pass_context
def email_read(ctx, message_id, save_dir, body_format):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = _find_message(account, message_id)
        if not message:
            formatter.error(f"Message not found: {message_id}", code="NOT_FOUND")
            sys.exit(1)

        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            for attachment in message.attachments:
                if isinstance(attachment, FileAttachment):
                    path = os.path.join(save_dir, attachment.name)
                    with open(path, "wb") as handle:
                        handle.write(attachment.content)
                    click.echo(f"Saved: {path}", err=True)

        formatter.success(serialize_email_detail(message, body_format=body_format))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_email.py::TestEmailRead -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全部 email 测试确认无回归**

Run: `pytest tests/test_email.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add exchange_cli/commands/email.py tests/test_email.py
git commit -m "feat: add --body-format option to email read, default markdown"
```

---

### Task 6: 端到端验证 + Skill 文档更新

**Files:**
- Modify: `skills/exchange-cli/SKILL.md`（如果存在且包含 email read 用法说明）

- [ ] **Step 1: 运行全部测试确认无回归**

Run: `pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 2: Lint 检查**

Run: `ruff check exchange_cli/ tests/`
Expected: 无错误

- [ ] **Step 3: 检查 skill 文档是否需要更新**

Run: `grep -r "email read" skills/` 
如果 skill 文档中有 `email read` 的用法示例，补充 `--body-format` 选项说明。如果没有，跳过。

- [ ] **Step 4: Commit（如有改动）**

```bash
git add -A
git commit -m "docs: update skill docs with --body-format option"
```

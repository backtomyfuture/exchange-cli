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

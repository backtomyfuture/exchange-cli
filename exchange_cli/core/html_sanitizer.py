"""Sanitizer for draft HTML bodies to prevent Outlook WordMail editor crashes."""

import re

# Word document declarations in meta tags
_META_WORD_RE = re.compile(
    r'<meta\b[^>]*?\b(?:name|http-equiv)\s*=\s*["\']?(?:ProgId|Generator|Originator)\b[^>]*\/?>',
    re.IGNORECASE,
)

# Word/Office data and theme links
_LINK_WORD_RE = re.compile(
    r'<link\b[^>]*?\brel\s*=\s*["\']?(?:File-List|Edit-Time-Data|themeData|colorSchemeMapping)\b[^>]*\/?>',
    re.IGNORECASE,
)

# Innermost conditional comments (loop to fixed point for nested comments)
_INNER_MSO_COMMENT_RE = re.compile(
    r'<!--\[if(?:(?!<!--\[if)[\s\S])*?<!\[endif\]-->',
    re.IGNORECASE,
)

# Orphaned conditional comment markers from server-side partial stripping
_ORPHAN_ENDIF_RE = re.compile(r'<!\[endif\]-->', re.IGNORECASE)
_ORPHAN_IF_RE = re.compile(r'<!--\[if[^\]]*\](?:-->)?', re.IGNORECASE)

# XML blocks and tags
_XML_BLOCK_RE = re.compile(r'<xml\b[\s\S]*?</xml>', re.IGNORECASE)
_XML_TAG_RE = re.compile(r'</?xml\b[^>]*>', re.IGNORECASE)

# Office custom element tags like <o:p>, <w:WordDocument>, <v:shape>
_OFFICE_TAG_RE = re.compile(r'</?[wovmx]:[a-zA-Z0-9_-]+[^>]*>', re.IGNORECASE)

# Empty @font-face rules that break Outlook DOM parser
_EMPTY_FONT_FACE_RE = re.compile(
    r'@font-face\s*\{\s*(?:font-family:\s*;?\s*)?\}',
    re.IGNORECASE,
)

# XML namespace declarations
_XMLNS_RE = re.compile(
    r'\s+xmlns:[a-zA-Z0-9_-]+\s*=\s*["\'][^"\']*["\']',
    re.IGNORECASE,
)


def sanitize_draft_html(html: str) -> tuple[str, list[str]]:
    """Sanitize HTML body against WordMail/Outlook editor crashes.

    Removes Word document declarations, edit data links, broken MSO conditional
    comments, XML blocks, Office namespaces, and empty @font-face rules while
    preserving normal W3C HTML content and styling.

    Args:
        html: Raw HTML string to sanitize.

    Returns:
        tuple[str, list[str]]: (cleaned_html, list_of_rule_names_applied)
    """
    if not html or not isinstance(html, str):
        return html or "", []

    rules_applied: list[str] = []
    cleaned = html

    if _META_WORD_RE.search(cleaned):
        cleaned = _META_WORD_RE.sub("", cleaned)
        rules_applied.append("word_meta")

    if _LINK_WORD_RE.search(cleaned):
        cleaned = _LINK_WORD_RE.sub("", cleaned)
        rules_applied.append("word_links")

    comment_matched = False
    while True:
        nxt = _INNER_MSO_COMMENT_RE.sub("", cleaned)
        if nxt == cleaned:
            break
        cleaned = nxt
        comment_matched = True

    if _ORPHAN_ENDIF_RE.search(cleaned) or _ORPHAN_IF_RE.search(cleaned):
        cleaned = _ORPHAN_ENDIF_RE.sub("", cleaned)
        cleaned = _ORPHAN_IF_RE.sub("", cleaned)
        comment_matched = True

    if comment_matched:
        rules_applied.append("conditional_comments")

    xml_matched = False
    if _XML_BLOCK_RE.search(cleaned) or _XML_TAG_RE.search(cleaned):
        cleaned = _XML_BLOCK_RE.sub("", cleaned)
        cleaned = _XML_TAG_RE.sub("", cleaned)
        xml_matched = True

    if _OFFICE_TAG_RE.search(cleaned):
        cleaned = _OFFICE_TAG_RE.sub("", cleaned)
        xml_matched = True

    if xml_matched:
        rules_applied.append("office_xml_tags")

    if _EMPTY_FONT_FACE_RE.search(cleaned):
        cleaned = _EMPTY_FONT_FACE_RE.sub("", cleaned)
        rules_applied.append("empty_font_face")

    if _XMLNS_RE.search(cleaned):
        cleaned = _XMLNS_RE.sub("", cleaned)
        rules_applied.append("xmlns_declarations")

    return cleaned, rules_applied

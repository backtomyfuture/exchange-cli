from exchange_cli.core.html_sanitizer import sanitize_draft_html


def test_sanitize_clean_html_unchanged():
    html = "<div><p>Normal text with <b>bold</b> and <a href='https://example.com'>link</a></p></div>"
    cleaned, rules = sanitize_draft_html(html)
    assert cleaned == html
    assert rules == []


def test_sanitize_empty_or_none():
    assert sanitize_draft_html("") == ("", [])
    assert sanitize_draft_html(None) == ("", [])


def test_sanitize_word_meta_tags():
    html = (
        '<html><head>'
        '<meta name="ProgId" content="Word.Document">'
        '<meta content="Microsoft Word 15" name="Generator">'
        '<meta name="Originator" content="Microsoft Word 15">'
        '<meta name="viewport" content="width=device-width">'
        '</head><body><p>Text</p></body></html>'
    )
    cleaned, rules = sanitize_draft_html(html)
    assert "ProgId" not in cleaned
    assert "Generator" not in cleaned
    assert "Originator" not in cleaned
    assert '<meta name="viewport" content="width=device-width">' in cleaned
    assert "word_meta" in rules


def test_sanitize_word_links():
    html = (
        '<head>'
        '<link rel="File-List" href="cid:filelist.xml">'
        '<link href="cid:editdata.mso" rel="Edit-Time-Data">'
        '<link rel="themeData" href="cid:themedata.thmx">'
        '<link rel="stylesheet" href="https://example.com/style.css">'
        '</head>'
    )
    cleaned, rules = sanitize_draft_html(html)
    assert "File-List" not in cleaned
    assert "Edit-Time-Data" not in cleaned
    assert "themeData" not in cleaned
    assert '<link rel="stylesheet" href="https://example.com/style.css">' in cleaned
    assert "word_links" in rules


def test_sanitize_nested_conditional_comments():
    html = (
        '<div>'
        '<!--[if gte mso 9]>'
        '<xml>'
        '  <w:WordDocument>'
        '    <!--[if supportFields]><![endif]-->'
        '  </w:WordDocument>'
        '</xml>'
        '<![endif]-->'
        '<p>Visible Content</p>'
        '</div>'
    )
    cleaned, rules = sanitize_draft_html(html)
    assert "<!--[if" not in cleaned
    assert "<![endif]-->" not in cleaned
    assert "<p>Visible Content</p>" in cleaned
    assert "conditional_comments" in rules


def test_sanitize_orphan_conditional_comments():
    html = '<p>Start</p><![endif]--><p>Middle</p><!--[if gte mso 9]><p>End</p>'
    cleaned, rules = sanitize_draft_html(html)
    assert "<![endif]-->" not in cleaned
    assert "<!--[if" not in cleaned
    assert "<p>Start</p>" in cleaned
    assert "<p>Middle</p>" in cleaned
    assert "<p>End</p>" in cleaned
    assert "conditional_comments" in rules


def test_sanitize_office_tags_and_xml_blocks():
    html = (
        '<body>'
        '<xml><test>secret</test></xml>'
        '<p class="MsoNormal">Line 1<o:p></o:p></p>'
        '<w:WordDocument></w:WordDocument>'
        '<v:shape id="shape1"></v:shape>'
        '</body>'
    )
    cleaned, rules = sanitize_draft_html(html)
    assert "<xml" not in cleaned
    assert "<o:p" not in cleaned
    assert "</o:p>" not in cleaned
    assert "<w:WordDocument" not in cleaned
    assert "<v:shape" not in cleaned
    assert '<p class="MsoNormal">Line 1</p>' in cleaned
    assert "office_xml_tags" in rules


def test_sanitize_empty_font_face():
    html = (
        '<style>'
        '@font-face { font-family:; }'
        '@font-face { font-family: "Segoe UI"; }'
        'p { color: red; }'
        '</style>'
    )
    cleaned, rules = sanitize_draft_html(html)
    assert "font-family:;" not in cleaned
    assert '@font-face { font-family: "Segoe UI"; }' in cleaned
    assert "p { color: red; }" in cleaned
    assert "empty_font_face" in rules


def test_sanitize_xmlns_declarations():
    html = (
        '<html xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:w="urn:schemas-microsoft-com:office:word" '
        'lang="en">'
    )
    cleaned, rules = sanitize_draft_html(html)
    assert "xmlns:v" not in cleaned
    assert "xmlns:o" not in cleaned
    assert "xmlns:w" not in cleaned
    assert 'lang="en"' in cleaned
    assert "xmlns_declarations" in rules


def test_full_outlook_wordmail_blank_sample():
    # Mirroring real-world Outlook/Exchange corrupted draft HTML
    corrupted_html = (
        '<html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:w="urn:schemas-microsoft-com:office:word" xmlns:m="http://schemas.microsoft.com/office/2004/12/omml">'
        '<head>'
        '<meta name="ProgId" content="Word.Document">'
        '<meta name="Generator" content="Microsoft Word 15">'
        '<meta name="Originator" content="Microsoft Word 15">'
        '<link rel="File-List" href="cid:filelist.xml">'
        '<link rel="Edit-Time-Data" href="cid:editdata.mso">'
        '<style>'
        '<!--'
        '@font-face { font-family:; }'
        '@font-face { font-family: "Microsoft YaHei"; }'
        'p.MsoNormal, li.MsoNormal, div.MsoNormal { margin: 0cm; font-size: 11.0pt; }'
        '-->'
        '</style>'
        '<!--[if gte mso 9]><xml><w:WordDocument><w:View>Normal</w:View></w:WordDocument></xml><![endif]-->'
        '</head>'
        '<body>'
        '<div class="WordSection1">'
        '<p class="MsoNormal">尊敬的领导：<o:p></o:p></p>'
        '<p class="MsoNormal">这是一封真实的测试草稿邮件。<o:p></o:p></p>'
        '</div>'
        '</body>'
        '</html>'
    )
    cleaned, rules = sanitize_draft_html(corrupted_html)

    # All crash-inducing triggers removed
    assert "ProgId" not in cleaned
    assert "Generator" not in cleaned
    assert "Originator" not in cleaned
    assert "File-List" not in cleaned
    assert "Edit-Time-Data" not in cleaned
    assert "<!--[if" not in cleaned
    assert "<w:WordDocument" not in cleaned
    assert "<o:p" not in cleaned
    assert "xmlns:o" not in cleaned
    assert "xmlns:w" not in cleaned
    assert "@font-face { font-family:; }" not in cleaned

    # Legitimate content and styling preserved
    assert "尊敬的领导：" in cleaned
    assert "这是一封真实的测试草稿邮件。" in cleaned
    assert 'class="WordSection1"' in cleaned
    assert 'font-family: "Microsoft YaHei";' in cleaned
    assert 'p.MsoNormal' in cleaned
    assert set(rules) == {
        "word_meta",
        "word_links",
        "conditional_comments",
        "office_xml_tags",
        "empty_font_face",
        "xmlns_declarations",
    }

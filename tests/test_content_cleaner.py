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

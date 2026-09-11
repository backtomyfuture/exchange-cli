from types import SimpleNamespace

from exchange_cli.core.query import scan_matching, take_page


def test_take_page_reports_truncation():
    items = list(range(5))
    page, truncated = take_page(items, limit=3)

    assert page == [0, 1, 2]
    assert truncated is True


def test_scan_matching_does_not_stop_at_the_first_page():
    items = [
        SimpleNamespace(id="A", status="Completed"),
        SimpleNamespace(id="B", status="NotStarted"),
        SimpleNamespace(id="C", status="Completed"),
        SimpleNamespace(id="D", status="NotStarted"),
    ]

    page, truncated = scan_matching(
        items,
        limit=2,
        predicate=lambda item: item.status == "NotStarted",
    )

    assert [item.id for item in page] == ["B", "D"]
    assert truncated is False


def test_scan_matching_reports_scan_cap_truncation():
    items = [SimpleNamespace(id=str(index), status="NotStarted") for index in range(5)]

    page, truncated = scan_matching(
        items,
        limit=2,
        scan_limit=3,
        predicate=lambda item: item.status == "NotStarted",
    )

    assert [item.id for item in page] == ["0", "1"]
    assert truncated is True

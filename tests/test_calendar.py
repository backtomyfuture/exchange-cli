import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.calendar.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestCalendarList:
    def test_list_today(self, runner, mock_conn):
        mock_conn.calendar.view.return_value = []
        result = runner.invoke(cli, ["calendar", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_list_range(self, runner, mock_conn):
        mock_conn.calendar.view.return_value = []
        result = runner.invoke(cli, ["calendar", "list", "--start", "2024-07-01", "--end", "2024-07-31"])
        assert result.exit_code == 0
        start, end = mock_conn.calendar.view.call_args.kwargs["start"], mock_conn.calendar.view.call_args.kwargs["end"]
        assert (start.year, start.month, start.day) == (2024, 7, 1)
        assert (end.year, end.month, end.day) == (2024, 8, 1)

    def test_list_same_day_is_inclusive(self, runner, mock_conn):
        mock_conn.calendar.view.return_value = []
        result = runner.invoke(cli, ["calendar", "list", "--start", "2024-07-15", "--end", "2024-07-15"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["truncated"] is False
        start, end = mock_conn.calendar.view.call_args.kwargs["start"], mock_conn.calendar.view.call_args.kwargs["end"]
        assert (start.year, start.month, start.day) == (2024, 7, 15)
        assert (end.year, end.month, end.day) == (2024, 7, 16)

    def test_list_with_limit_and_truncation(self, runner, mock_conn):
        mock_events = [MagicMock() for _ in range(3)]
        mock_conn.calendar.view.return_value = mock_events
        result = runner.invoke(cli, ["calendar", "list", "--limit", "2"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["truncated"] is True


class TestCalendarCreate:
    def test_create_event(self, runner, mock_conn):
        with patch("exchange_cli.commands.calendar.CalendarItem") as event_cls:
            event = MagicMock()
            event.id = "E1"
            event_cls.return_value = event
            result = runner.invoke(
                cli,
                [
                    "calendar",
                    "create",
                    "--subject",
                    "Meeting",
                    "--start",
                    "2024-07-15 10:00",
                    "--end",
                    "2024-07-15 11:00",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        event.save.assert_called_once()
        assert event.save.call_args.kwargs["send_meeting_invitations"] == "SendToNone"

    def test_create_with_attendees_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.calendar.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                [
                    "calendar",
                    "create",
                    "--subject",
                    "Meeting",
                    "--start",
                    "2024-07-15 10:00",
                    "--end",
                    "2024-07-15 11:00",
                    "--attendees",
                    "a@x.com",
                ],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

    def test_create_rejects_reversed_range_before_connection(self, runner):
        with patch("exchange_cli.commands.calendar.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                [
                    "calendar",
                    "create",
                    "--subject",
                    "Meeting",
                    "--start",
                    "2024-07-15 11:00",
                    "--end",
                    "2024-07-15 10:00",
                ],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_TIME_RANGE"
        get_connection.assert_not_called()


class TestCalendarUpdate:
    def test_update_requires_at_least_one_field_before_connection(self, runner):
        with patch("exchange_cli.commands.calendar.get_connection") as get_connection:
            result = runner.invoke(cli, ["calendar", "update", "E1"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()


class TestCalendarDelete:
    def test_delete_event(self, runner, mock_conn):
        event = MagicMock()
        event.id = "E1"
        mock_conn.calendar.get.return_value = event
        result = runner.invoke(cli, ["calendar", "delete", "E1", "--confirm"])
        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["permanent"] is True
        event.delete.assert_called_once()
        assert event.delete.call_args.kwargs["send_meeting_cancellations"] == "SendToNone"

    def test_update_with_notify_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.calendar.get_connection") as get_connection:
            result = runner.invoke(cli, ["calendar", "update", "E1", "--subject", "New", "--notify", "all"])
        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

    def test_delete_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.calendar.get_connection") as get_connection:
            result = runner.invoke(cli, ["calendar", "delete", "E1"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

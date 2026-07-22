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


class TestCalendarCreate:
    def test_create_event(self, runner, mock_conn):
        result = runner.invoke(
            cli,
            ["calendar", "create", "--subject", "Meeting", "--start", "2024-07-15 10:00", "--end", "2024-07-15 11:00"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

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

    def test_delete_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.calendar.get_connection") as get_connection:
            result = runner.invoke(cli, ["calendar", "delete", "E1"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

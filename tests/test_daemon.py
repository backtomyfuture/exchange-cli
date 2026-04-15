from exchange_cli.core.daemon import build_daemon_state, daemon_ping


def test_build_daemon_state_uses_custom_config_dir(tmp_path):
    config_dir = tmp_path / "custom-config"
    state = build_daemon_state(str(config_dir))
    assert state.config_dir == config_dir
    assert state.runtime_dir == config_dir / "run"
    assert state.socket_path == config_dir / "run" / "agent.sock"


def test_daemon_ping_returns_none_when_socket_missing(tmp_path):
    state = build_daemon_state(str(tmp_path / "missing-config"))
    assert daemon_ping(state) is None

import pytest
from desk import cli

def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.parse_server_args(["server", "--help"])
    assert exc.value.code == 0

def test_cli_server_args():
    args = cli.parse_server_args(["server", "--port", "9999", "--fps", "24", "--quality", "75"])
    assert args.port == 9999
    assert args.fps == 24
    assert args.quality == 75

def test_cli_client_args():
    args = cli.parse_client_args(["client", "192.168.1.100:8765", "--headless"])
    assert args.target == "192.168.1.100:8765"
    assert args.headless is True

def test_local_ips():
    ips = cli.get_local_ips()
    assert isinstance(ips, list)
    assert len(ips) > 0

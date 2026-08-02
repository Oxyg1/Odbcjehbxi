from __future__ import annotations

import pytest

from tgmarket.cli import build_parser, load_config, main
from tgmarket.config import ConfigError

CONFIG = """
runtime:
  poll_interval: 30
filters:
  max_price: 100
buy:
  dry_run: true
  recipients: [me]
  budget:
    max_stars_total: 500
"""


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TG_API_ID", "1")
    monkeypatch.setenv("TG_API_HASH", "h")
    monkeypatch.delenv("DRY_RUN", raising=False)
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


def parse(argv):
    return build_parser().parse_args(argv)


def test_subcommand_is_required(capsys):
    with pytest.raises(SystemExit):
        parse([])


def test_run_defaults_to_the_configured_dry_run(config_file):
    config = load_config(parse(["-c", str(config_file), "run"]))
    assert config.buy.dry_run is True


def test_live_flag_disables_dry_run(config_file):
    config = load_config(parse(["-c", str(config_file), "run", "--live"]))
    assert config.buy.dry_run is False


def test_dry_run_flag_beats_live_flag(config_file):
    config = load_config(parse(["-c", str(config_file), "run", "--live", "--dry-run"]))
    assert config.buy.dry_run is True, "the safe flag must win when both are passed"


def test_live_flag_still_requires_a_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("TG_API_ID", "1")
    monkeypatch.setenv("TG_API_HASH", "h")
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG.replace("    max_stars_total: 500", "    max_stars_total: 0"), encoding="utf-8")
    with pytest.raises(ConfigError, match="spending ceiling"):
        load_config(parse(["-c", str(path), "run", "--live"]))


def test_log_level_override(config_file):
    config = load_config(parse(["-c", str(config_file), "--log-level", "DEBUG", "watch"]))
    assert config.runtime.log_level == "DEBUG"


def test_watch_has_no_live_flag(config_file):
    with pytest.raises(SystemExit):
        parse(["-c", str(config_file), "watch", "--live"])


def test_config_errors_exit_with_code_2(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("TG_API_ID", raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)
    assert main(["-c", str(tmp_path / "missing.yaml"), "watch"]) == 2
    assert "configuration error" in capsys.readouterr().err

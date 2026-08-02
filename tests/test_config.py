from __future__ import annotations

import pytest

from tgmarket.config import MIN_POLL_INTERVAL, AppConfig, ConfigError, load_dotenv

BASE_YAML = """
telegram:
  session_name: bot
runtime:
  poll_interval: 60
filters:
  max_price: 100
buy:
  dry_run: true
  recipients: [me]
"""


def write(tmp_path, text, name="config.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("TG_API_ID", "TG_API_HASH", "TG_PHONE", "TG_PROXY", "TG_SESSION_STRING",
                "DRY_RUN", "NOTIFY_BOT_TOKEN", "NOTIFY_CHAT_ID", "NOTIFY_ENABLED",
                "LOG_LEVEL", "STATE_PATH", "TG_SESSION_NAME", "TG_SESSION_DIR"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TG_API_ID", "12345")
    monkeypatch.setenv("TG_API_HASH", "deadbeef")


def test_loads_yaml_and_env(tmp_path):
    config = AppConfig.load(write(tmp_path, BASE_YAML), use_dotenv=False)
    assert config.telegram.api_id == 12345
    assert config.telegram.api_hash == "deadbeef"
    assert config.telegram.session_name == "bot"
    assert config.filters.max_price == 100
    assert config.buy.dry_run is True


def test_env_overrides_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("TG_SESSION_NAME", "from-env")
    monkeypatch.setenv("STATE_PATH", "/tmp/other.json")
    config = AppConfig.load(write(tmp_path, BASE_YAML), use_dotenv=False)
    assert config.telegram.session_name == "from-env"
    assert config.runtime.state_path == "/tmp/other.json"


def test_dry_run_env_wins_over_config(tmp_path, monkeypatch):
    yaml_text = BASE_YAML.replace("dry_run: true", "dry_run: false") + """
    """
    monkeypatch.setenv("DRY_RUN", "true")
    config = AppConfig.load(write(tmp_path, yaml_text), use_dotenv=False)
    assert config.buy.dry_run is True, "DRY_RUN is the emergency brake and must win"


def test_missing_credentials_are_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_API_ID")
    monkeypatch.delenv("TG_API_HASH")
    with pytest.raises(ConfigError, match="TG_API_ID"):
        AppConfig.load(write(tmp_path, BASE_YAML), use_dotenv=False)


def test_unknown_option_is_rejected(tmp_path):
    text = BASE_YAML + "\n  max_prise: 10\n"
    with pytest.raises(ConfigError, match="unknown option"):
        AppConfig.load(write(tmp_path, text), use_dotenv=False)


def test_poll_interval_floor(tmp_path):
    text = BASE_YAML.replace("poll_interval: 60", "poll_interval: 1")
    with pytest.raises(ConfigError, match="poll_interval"):
        AppConfig.load(write(tmp_path, text), use_dotenv=False)
    assert MIN_POLL_INTERVAL == 15


def test_live_mode_requires_a_spending_ceiling(tmp_path):
    text = BASE_YAML.replace("dry_run: true", "dry_run: false")
    with pytest.raises(ConfigError, match="spending ceiling"):
        AppConfig.load(write(tmp_path, text), use_dotenv=False)

    with_budget = text + """
  budget:
    max_stars_total: 500
"""
    config = AppConfig.load(write(tmp_path, with_budget, "ok.yaml"), use_dotenv=False)
    assert config.buy.dry_run is False and config.buy.budget.max_stars_total == 500


def test_contradictory_filters_are_rejected(tmp_path):
    text = BASE_YAML.replace("max_price: 100", "max_price: 100\n  limited_only: true\n  unlimited_only: true")
    with pytest.raises(ConfigError, match="mutually exclusive"):
        AppConfig.load(write(tmp_path, text), use_dotenv=False)


def test_price_window_must_be_coherent(tmp_path):
    text = BASE_YAML.replace("max_price: 100", "max_price: 10\n  min_price: 100")
    with pytest.raises(ConfigError, match="max_price"):
        AppConfig.load(write(tmp_path, text), use_dotenv=False)


def test_resale_needs_gift_ids(tmp_path):
    text = BASE_YAML.replace("max_price: 100", "max_price: 100\n  include_resale: true")
    with pytest.raises(ConfigError, match="resale_gift_ids"):
        AppConfig.load(write(tmp_path, text), use_dotenv=False)


def test_notifications_switch_on_when_both_secrets_present(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTIFY_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("NOTIFY_CHAT_ID", "42")
    config = AppConfig.load(write(tmp_path, BASE_YAML), use_dotenv=False)
    assert config.notify.enabled is True

    monkeypatch.setenv("NOTIFY_ENABLED", "false")
    config = AppConfig.load(write(tmp_path, BASE_YAML), use_dotenv=False)
    assert config.notify.enabled is False, "an explicit NOTIFY_ENABLED must be honoured"


def test_notifications_without_chat_id_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTIFY_ENABLED", "true")
    monkeypatch.setenv("NOTIFY_BOT_TOKEN", "123:abc")
    with pytest.raises(ConfigError, match="NOTIFY_CHAT_ID"):
        AppConfig.load(write(tmp_path, BASE_YAML), use_dotenv=False)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        AppConfig.load(tmp_path / "nope.yaml", use_dotenv=False)


def test_dotenv_does_not_clobber_real_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('TG_API_ID=999\nNOTIFY_CHAT_ID="77"\n# comment\nBROKEN LINE\n', encoding="utf-8")
    load_dotenv(env)
    assert os_environ("TG_API_ID") == "12345", "the shell wins over .env"
    assert os_environ("NOTIFY_CHAT_ID") == "77", "quotes are stripped"


def os_environ(key):
    import os

    return os.environ.get(key)

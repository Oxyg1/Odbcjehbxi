from __future__ import annotations

import pytest

from tgmarket.client import ProxyConfigError, build_client, parse_proxy
from tgmarket.config import ConfigError, TelegramConfig


def test_no_proxy():
    assert parse_proxy(None) == (None, None)
    assert parse_proxy("") == (None, None)


def test_mtproxy_url():
    proxy, connection = parse_proxy("mtproxy://proxy.example.com:443?secret=ee0102ff")
    assert proxy == ("proxy.example.com", 443, "ee0102ff")
    assert connection is not None and "MTProxy" in connection.__name__


def test_mtproxy_requires_a_secret():
    with pytest.raises(ProxyConfigError, match="secret"):
        parse_proxy("mtproxy://proxy.example.com:443")


def test_proxy_needs_host_and_port():
    with pytest.raises(ProxyConfigError, match="host and port"):
        parse_proxy("mtproxy://proxy.example.com")


def test_unsupported_scheme():
    with pytest.raises(ProxyConfigError, match="unsupported proxy scheme"):
        parse_proxy("ftp://example.com:21")


def test_socks_proxy_when_dependency_present():
    pytest.importorskip("python_socks")
    proxy, connection = parse_proxy("socks5://user:pw@127.0.0.1:1080")
    assert proxy == {"proxy_type": "socks5", "addr": "127.0.0.1", "port": 1080,
                     "username": "user", "password": "pw"}
    assert connection is None


def test_build_client_rejects_missing_credentials():
    with pytest.raises(ConfigError, match="TG_API_ID"):
        build_client(TelegramConfig())


def test_build_client_creates_the_session_directory(tmp_path):
    config = TelegramConfig(api_id=1, api_hash="h", session_dir=str(tmp_path / "s"), session_name="bot")
    client = build_client(config)
    assert (tmp_path / "s").is_dir()
    assert config.session_path.endswith("bot")
    assert client.session is not None


def test_string_session_leaves_no_files_on_disk(tmp_path):
    from telethon.crypto import AuthKey
    from telethon.sessions import StringSession

    source = StringSession()
    source.set_dc(2, "149.154.167.51", 443)
    source.auth_key = AuthKey(b"\x00" * 256)

    config = TelegramConfig(api_id=1, api_hash="h", session_string=source.save(),
                            session_dir=str(tmp_path / "unused"))
    client = build_client(config)
    assert isinstance(client.session, StringSession)
    assert not (tmp_path / "unused").exists()

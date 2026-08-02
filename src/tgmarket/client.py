"""Telethon client construction, session handling and proxy wiring.

The session file is the credential: once created it is a full login to the
account, so it is stored outside the repo (``sessions/`` is git-ignored) and the
interactive login lives in its own CLI command rather than in the run loop.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import TelegramConfig

log = logging.getLogger(__name__)


class ProxyConfigError(ValueError):
    """The ``TG_PROXY`` string could not be understood."""


def parse_proxy(url: Optional[str]) -> tuple[Optional[dict[str, Any]], Optional[Any]]:
    """Translate a proxy URL into Telethon ``proxy``/``connection`` arguments.

    Supported forms::

        mtproxy://server:port?secret=<hex>     # Telegram's own MTProto proxy
        socks5://user:pass@host:port
        http://user:pass@host:port

    An MTProto proxy is a transport, not extra privileges: it changes how the
    traffic reaches Telegram and nothing about what the account may do.
    """
    if not url:
        return None, None

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if not parsed.hostname or not parsed.port:
        raise ProxyConfigError(f"proxy URL needs host and port: {url}")

    if scheme in {"mtproxy", "mtproto"}:
        secret = (parse_qs(parsed.query).get("secret") or [""])[0]
        if not secret:
            raise ProxyConfigError("mtproxy:// URL needs a ?secret=<hex> parameter")
        from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

        return (parsed.hostname, parsed.port, secret), ConnectionTcpMTProxyRandomizedIntermediate

    if scheme in {"socks5", "socks4", "http"}:
        try:
            import python_socks  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on extras
            raise ProxyConfigError(
                f"{scheme}:// proxies need the optional dependency: pip install 'telethon[socks]'"
            ) from exc
        proxy: dict[str, Any] = {
            "proxy_type": scheme,
            "addr": parsed.hostname,
            "port": parsed.port,
        }
        if parsed.username:
            proxy["username"] = parsed.username
        if parsed.password:
            proxy["password"] = parsed.password
        return proxy, None

    raise ProxyConfigError(f"unsupported proxy scheme: {scheme}")


def build_client(config: TelegramConfig) -> TelegramClient:
    """Create an unconnected client from credentials + session settings."""
    config.validate()
    proxy, connection = parse_proxy(config.proxy)

    if config.session_string:
        session: Any = StringSession(config.session_string)
        log.debug("using in-memory string session")
    else:
        Path(config.session_dir).mkdir(parents=True, exist_ok=True)
        session = config.session_path
        log.debug("using session file %s.session", session)

    kwargs: dict[str, Any] = {
        "device_model": config.device_model,
        "app_version": config.app_version,
    }
    if proxy is not None:
        kwargs["proxy"] = proxy
    if connection is not None:
        kwargs["connection"] = connection

    return TelegramClient(session, config.api_id, config.api_hash, **kwargs)


async def connect(config: TelegramConfig, *, interactive: bool = False) -> TelegramClient:
    """Connect and authorise, or fail with an actionable message.

    ``interactive=False`` (the run loop) never prompts: an unattended process
    that blocks on ``input()`` looks exactly like a hang.
    """
    client = build_client(config)
    if interactive:
        kwargs: dict[str, Any] = {"phone": lambda: config.phone or input("Phone number: ")}
        if config.password:
            # Otherwise let Telethon prompt for the 2FA password itself.
            kwargs["password"] = config.password
        await client.start(**kwargs)
        return client

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "not logged in — run `python -m tgmarket login` once to create the session file"
        )
    return client

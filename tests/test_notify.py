from __future__ import annotations

import json
import urllib.error

from tgmarket.config import NotifyConfig
from tgmarket.notify import Notifier, NullNotifier, build_notifier


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_build_notifier_returns_null_when_disabled():
    assert isinstance(build_notifier(None), NullNotifier)
    assert isinstance(build_notifier(NotifyConfig(enabled=False)), NullNotifier)
    assert not isinstance(
        build_notifier(NotifyConfig(enabled=True, bot_token="t", chat_id="1")), NullNotifier
    )


async def test_disabled_notifier_sends_nothing(monkeypatch):
    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: called.append(1))
    assert await NullNotifier().info("hello") is False
    assert called == []


async def test_message_is_posted_to_the_bot_api(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = Notifier(NotifyConfig(enabled=True, bot_token="123:abc", chat_id="42"))

    assert await notifier.success("bought a gift") is True
    assert sent["url"] == "https://api.telegram.org/bot123:abc/sendMessage"
    assert sent["body"]["chat_id"] == "42"
    assert "bought a gift" in sent["body"]["text"]


async def test_long_messages_are_truncated_to_the_api_limit(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = Notifier(NotifyConfig(enabled=True, bot_token="t", chat_id="1"))
    await notifier.info("x" * 9000)
    assert len(sent["body"]["text"]) == 4096


async def test_transport_failure_never_propagates(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    notifier = Notifier(NotifyConfig(enabled=True, bot_token="t", chat_id="1"))
    assert await notifier.error("something broke") is False


async def test_http_error_is_reported_as_failure(monkeypatch):
    def forbidden(request, timeout=None):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    notifier = Notifier(NotifyConfig(enabled=True, bot_token="t", chat_id="1"))
    assert await notifier.info("hi") is False

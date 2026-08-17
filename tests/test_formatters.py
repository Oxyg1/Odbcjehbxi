from __future__ import annotations

from app import formatters as fmt


def _report(records, **kwargs):
    params = dict(
        chat_title="Иван",
        chat_username="ivan",
        records=records,
        unknown_count=0,
        hidden_own=0,
        chat_deleted=False,
        tz_name="Europe/Moscow",
        preview_limit=700,
        max_messages=25,
    )
    params.update(kwargs)
    return fmt.deletion_report(**params)


def test_single_deletion_report(make_record):
    texts = _report([make_record(1, text="секрет")])
    assert len(texts) == 1
    assert "Сообщение удалено" in texts[0]
    assert "секрет" in texts[0]
    assert "Иван" in texts[0]


def test_chat_deleted_header(make_record):
    texts = _report([make_record(i) for i in range(1, 6)], chat_deleted=True)
    assert "удалена вся переписка" in texts[0]


def test_unknown_and_own_counters(make_record):
    texts = _report([make_record(1)], unknown_count=3, hidden_own=2)
    joined = "\n".join(texts)
    assert "Удалено сообщений: 6" in joined
    assert "ваших собственных: 2" in joined
    assert "3 сообщ. бот не видел" in joined


def test_report_is_split_into_telegram_sized_chunks(make_record):
    records = [make_record(i, text="я" * 600) for i in range(1, 21)]
    texts = _report(records, preview_limit=600)
    assert len(texts) > 1
    assert all(len(text) <= fmt.TELEGRAM_LIMIT for text in texts)


def test_max_messages_limit(make_record):
    records = [make_record(i) for i in range(1, 31)]
    texts = _report(records, max_messages=5)
    joined = "\n".join(texts)
    assert "и ещё 25 сообщ. не показаны" in joined


def test_html_is_escaped(make_record):
    texts = _report([make_record(1, text="<b>жирный</b> & <script>")], chat_title="A<b>B")
    joined = "\n".join(texts)
    assert "&lt;b&gt;жирный&lt;/b&gt;" in joined
    assert "&amp;" in joined
    assert "A&lt;b&gt;B" in joined


def test_media_label_and_empty_text(make_record):
    texts = _report([make_record(1, text="", media_type="voice", file_id="F")])
    assert "голосовое сообщение" in texts[0]
    assert "(без текста)" in texts[0]


def test_edit_report_shows_before_and_after(make_record):
    before = make_record(1, text="было так")
    after = make_record(1, text="стало иначе", edited_at=1_700_000_000, edits=1)
    text = fmt.edit_report(before, after, "Europe/Moscow", 700)
    assert "Сообщение изменено" in text
    assert "было так" in text
    assert "стало иначе" in text


def test_edit_report_without_cached_original(make_record):
    after = make_record(1, text="новая версия", edited_at=1_700_000_000)
    text = fmt.edit_report(None, after, "Europe/Moscow", 700)
    assert "не видел исходную версию" in text


def test_truncate_adds_ellipsis():
    assert fmt.truncate("абвгде", 4) == "абв…"
    assert fmt.truncate("абв", 10) == "абв"


def test_unknown_timezone_falls_back_to_utc():
    assert fmt.fmt_time(1_700_000_000, "Nowhere/Nothing")
    assert fmt.fmt_time(None, "Europe/Moscow") == "неизвестно когда"


def test_connection_report_states():
    on = fmt.connection_report(
        enabled=True, can_reply=True, owner_name="Пётр", tz_name="Europe/Moscow"
    )
    assert "подключён" in on and "Пётр" in on
    off = fmt.connection_report(
        enabled=False, can_reply=False, owner_name="Пётр", tz_name="Europe/Moscow"
    )
    assert "отключён" in off

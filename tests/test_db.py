from __future__ import annotations

import time


async def _connect(storage, owner_user_id=42):
    await storage.save_connection(
        connection_id="conn",
        owner_user_id=owner_user_id,
        owner_chat_id=owner_user_id,
        owner_name="Владелец",
        is_enabled=True,
        can_reply=False,
    )


async def test_save_and_read_message(storage, make_record):
    record = make_record(1, text="привет", media_type="photo", file_id="F1")
    await storage.save_message(record)

    loaded = await storage.get_message("conn", -100, 1)
    assert loaded is not None
    assert loaded.text == "привет"
    assert loaded.media_type == "photo"
    assert loaded.file_id == "F1"
    assert loaded.outgoing is False
    assert loaded.deleted_at is None


async def test_save_message_is_idempotent(storage, make_record):
    await storage.save_message(make_record(1, text="было"))
    await storage.set_local_path("conn", -100, 1, "/tmp/file.jpg")
    await storage.save_message(make_record(1, text="стало"))

    loaded = await storage.get_message("conn", -100, 1)
    assert loaded.text == "стало"
    # Путь к скачанному файлу не должен теряться при повторном сохранении.
    assert loaded.local_path == "/tmp/file.jpg"


async def test_mark_deleted_and_alive_count(storage, make_record):
    for i in (1, 2, 3):
        await storage.save_message(make_record(i))
    assert await storage.count_alive_in_chat("conn", -100) == 3

    await storage.mark_deleted("conn", -100, [1, 2])
    assert await storage.count_alive_in_chat("conn", -100) == 1

    deleted = await storage.get_messages("conn", -100, [1, 2, 3])
    assert [record.message_id for record in deleted] == [1, 2, 3]
    assert deleted[0].deleted_at is not None
    assert deleted[2].deleted_at is None


async def test_get_messages_ignores_unknown_ids(storage, make_record):
    await storage.save_message(make_record(7))
    found = await storage.get_messages("conn", -100, [7, 8, 9])
    assert [record.message_id for record in found] == [7]


async def test_apply_edit_keeps_history(storage, make_record):
    await storage.save_message(make_record(1, text="первая версия"))
    await storage.apply_edit("conn", -100, 1, "первая версия", "вторая версия", 1700)

    loaded = await storage.get_message("conn", -100, 1)
    assert loaded.text == "вторая версия"
    assert loaded.edits == 1
    assert loaded.edited_at == 1700


async def test_settings_roundtrip(storage):
    defaults = {"notify_edits": True, "include_own": False}
    assert await storage.get_settings(1, defaults) == defaults

    await storage.set_setting(1, "include_own", True)
    assert (await storage.get_settings(1, defaults))["include_own"] is True
    # Настройки другого владельца не задеты.
    assert (await storage.get_settings(2, defaults))["include_own"] is False


async def test_stats_scoped_to_owner(storage, make_record):
    await _connect(storage)
    await storage.save_message(make_record(1))
    await storage.save_message(make_record(2, chat_id=-200))
    await storage.mark_deleted("conn", -100, [1])
    await storage.apply_edit("conn", -200, 2, "a", "b", 10)

    stats = await storage.stats(42)
    assert stats == {"total": 2, "deleted": 1, "edited": 1, "chats": 2}
    assert (await storage.stats(999))["total"] == 0


async def test_cleanup_removes_old_rows(storage, make_record):
    old = int(time.time()) - 40 * 86400
    await storage.save_message(make_record(1, date=old, local_path="/tmp/old.jpg"))
    await storage.save_message(make_record(2))

    removed, paths = await storage.cleanup(retention_days=30)
    assert removed == 1
    assert paths == ["/tmp/old.jpg"]
    assert await storage.get_message("conn", -100, 1) is None
    assert await storage.get_message("conn", -100, 2) is not None

    # retention_days = 0 отключает очистку.
    assert await storage.cleanup(retention_days=0) == (0, [])


async def test_purge_owner(storage, make_record):
    await _connect(storage)
    await storage.save_message(make_record(1, local_path="/tmp/a.jpg"))
    await storage.save_message(make_record(2))

    removed, paths = await storage.purge_owner(42)
    assert removed == 2
    assert paths == ["/tmp/a.jpg"]
    assert (await storage.stats(42))["total"] == 0

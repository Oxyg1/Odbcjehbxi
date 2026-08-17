from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Storage  # noqa: E402
from app.models import StoredMessage  # noqa: E402


@pytest_asyncio.fixture
async def storage(tmp_path: Path):
    store = await Storage(tmp_path / "test.db").connect()
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
def make_record():
    def _make(message_id: int = 1, **kwargs) -> StoredMessage:
        defaults = dict(
            connection_id="conn",
            chat_id=-100,
            message_id=message_id,
            chat_title="Иван Клиент",
            chat_username="ivan",
            sender_id=555,
            sender_name="Иван Клиент",
            sender_username="ivan",
            outgoing=False,
            text=f"сообщение {message_id}",
            media_type=None,
            file_id=None,
            file_unique_id=None,
            file_size=None,
            local_path=None,
            date=int(time.time()),
        )
        defaults.update(kwargs)
        return StoredMessage(**defaults)

    return _make

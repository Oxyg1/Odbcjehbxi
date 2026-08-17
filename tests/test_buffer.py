from __future__ import annotations

import asyncio

from app.buffer import DeletionBuffer


async def test_bursts_are_merged_into_one_flush():
    calls: list[tuple[str, int, list[int]]] = []

    async def flush(connection_id: str, chat_id: int, ids: list[int]) -> None:
        calls.append((connection_id, chat_id, ids))

    buffer = DeletionBuffer(delay=0.05, flush=flush)
    await buffer.add("conn", -100, [3, 1])
    await asyncio.sleep(0.01)
    await buffer.add("conn", -100, [2, 1])
    await asyncio.sleep(0.2)

    assert calls == [("conn", -100, [1, 2, 3])]


async def test_different_chats_are_reported_separately():
    calls: list[tuple[int, list[int]]] = []

    async def flush(_: str, chat_id: int, ids: list[int]) -> None:
        calls.append((chat_id, ids))

    buffer = DeletionBuffer(delay=0.05, flush=flush)
    await buffer.add("conn", -100, [1])
    await buffer.add("conn", -200, [7])
    await asyncio.sleep(0.2)

    assert sorted(calls) == [(-200, [7]), (-100, [1])]


async def test_max_wait_prevents_endless_postponing():
    calls: list[list[int]] = []

    async def flush(_: str, __: int, ids: list[int]) -> None:
        calls.append(ids)

    buffer = DeletionBuffer(delay=0.1, flush=flush, max_wait=0.15)
    for i in range(10):
        await buffer.add("conn", -100, [i])
        await asyncio.sleep(0.03)
    await asyncio.sleep(0.2)

    assert calls, "пачка должна быть отправлена, несмотря на непрерывный поток удалений"
    assert calls[0] == sorted(calls[0])


async def test_close_flushes_pending():
    calls: list[list[int]] = []

    async def flush(_: str, __: int, ids: list[int]) -> None:
        calls.append(ids)

    buffer = DeletionBuffer(delay=5.0, flush=flush)
    await buffer.add("conn", -100, [5, 4])
    await buffer.close()

    assert calls == [[4, 5]]


async def test_flush_errors_do_not_break_buffer():
    attempts: list[int] = []

    async def flush(_: str, __: int, ids: list[int]) -> None:
        attempts.append(ids[0])
        raise RuntimeError("Telegram недоступен")

    buffer = DeletionBuffer(delay=0.01, flush=flush)
    await buffer.add("conn", -100, [1])
    await asyncio.sleep(0.1)
    await buffer.add("conn", -100, [2])
    await asyncio.sleep(0.1)

    assert attempts == [1, 2]

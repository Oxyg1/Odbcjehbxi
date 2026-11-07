"""
Проверка запуска: настоящий main() и post_init бота на пустой временной базе.

Ловит то, что py_compile не видит: падение при старте. Так 5 октября бот
ушёл в перезапуски — post_init подменял методы JobQueue, а у неё __slots__.
Тесты с самодельной очередью этого не заметили.

Запуск (из любого каталога):
    python3 tools/test_startup.py [каталог_бота]

Безопасно для боевого сервера: база, лог и .env — временные, токен
поддельный, все запросы к Telegram заглушены. Живую базу не открывает.
Кончается «ЗАПУСК ОК» или кодом 1 с причиной.
"""
import os, sys, asyncio, tempfile, logging, traceback


def finish(code: int) -> None:
    """Выйти сразу: потоки пула базы и aiosqlite иначе держат процесс вечно."""
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


APP = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TMP = tempfile.mkdtemp(prefix="frog_startup_")
os.chdir(TMP)                                  # всё относительное — во временный каталог
os.environ["DB_PATH"] = os.path.join(TMP, "test.db")
os.environ["LOG_FILE"] = os.path.join(TMP, "bot.log")
os.environ["ENV_FILE"] = os.path.join(TMP, "no.env")
os.environ["BOT_TOKEN"] = "1:startup-check"
sys.path.insert(0, APP)

import bot as B                                # noqa: E402
import telegram.ext as TE                      # noqa: E402
from telegram import Bot                       # noqa: E402


async def _noop(self, *a, **kw):
    return True

for _m in ("set_my_commands", "delete_my_commands", "send_message", "send_document",
           "get_me", "get_chat", "set_my_description", "set_my_short_description",
           "set_chat_menu_button"):
    for _cls in (Bot, TE.ExtBot):
        if hasattr(_cls, _m):
            setattr(_cls, _m, _noop)

LOGGED = []


class _Errors(logging.Handler):
    def emit(self, r):
        msg = r.getMessage()
        # На пустой базе миграции сначала идут до создания таблиц — это шум
        if r.levelno >= logging.ERROR and "no such table" not in msg and "duplicate column" not in msg:
            LOGGED.append(msg.split("\n")[0][:200])

logging.getLogger().addHandler(_Errors())

RESULT = {}


def _fake_run_polling(self, *a, **kw):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(self.post_init(self))
    RESULT["jobs"] = len(self.job_queue.scheduler.get_jobs())
    RESULT["first"] = [type(h).__name__ for h in self.handlers.get(-100, [])]
    loop.run_until_complete(self.post_shutdown(self))
    for t in asyncio.all_tasks(loop):
        t.cancel()
    RESULT["ok"] = True


TE.Application.run_polling = _fake_run_polling

try:
    B.main()
except BaseException:
    print("\n✗ БОТ НЕ ЗАПУСТИТСЯ:\n")
    traceback.print_exc()
    finish(1)

problems = []
if not RESULT.get("ok"):
    problems.append("post_init/post_shutdown не дошли до конца")
if RESULT.get("first") != ["TypeHandler"]:
    problems.append(f"нет первого обработчика статистики: {RESULT.get('first')}")
if RESULT.get("jobs", 0) < 10:
    problems.append(f"мало фоновых задач: {RESULT.get('jobs')}")
if LOGGED:
    print("\n! Ошибки в логе при старте (запуск не блокируют):")
    for m in LOGGED[:15]:
        print("  ·", m)
if problems:
    print("\n✗ " + "\n✗ ".join(problems))
    finish(1)
print(f"\nЗАПУСК ОК: фоновых задач {RESULT['jobs']}, обработчиков в группе −100: {len(RESULT['first'])}")
finish(0)

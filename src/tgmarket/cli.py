"""Command line interface: ``python -m tgmarket <command>``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from . import __version__
from .client import connect
from .config import AppConfig, ConfigError
from .filters import LotFilter
from .logging_setup import setup_logging
from .market import MarketClient
from .notify import build_notifier
from .purchase import Budget, Purchaser
from .ratelimit import ApiGuard, RateLimiter
from .runner import Sniper
from .state import State

log = logging.getLogger("tgmarket")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tgmarket",
        description="Monitor the Telegram Star gift market and buy lots that match your filters.",
    )
    parser.add_argument("--version", action="version", version=f"tgmarket {__version__}")
    parser.add_argument("-c", "--config", default="config.yaml", help="path to the YAML config (default: config.yaml)")
    parser.add_argument("--log-level", help="override runtime.log_level")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="interactive login; creates the session file")
    sub.add_parser("balance", help="print the account's Stars balance")
    sub.add_parser("whoami", help="print the logged-in account")

    catalog = sub.add_parser("catalog", help="print the current gift catalogue and how it is filtered")
    catalog.add_argument("--all", action="store_true", help="include lots your filters reject")

    watch = sub.add_parser("watch", help="monitor and report matches, never buy")
    watch.add_argument("--once", action="store_true", help="run a single cycle and exit")

    run = sub.add_parser("run", help="monitor and buy matching lots")
    run.add_argument("--once", action="store_true", help="run a single cycle and exit")
    run.add_argument("--live", action="store_true", help="actually spend Stars (overrides dry_run)")
    run.add_argument("--dry-run", action="store_true", help="force dry-run even if the config says otherwise")
    run.add_argument("--max-cycles", type=int, help="stop after this many cycles")

    return parser


def load_config(args: argparse.Namespace) -> AppConfig:
    config = AppConfig.load(args.config)
    if args.log_level:
        config.runtime.log_level = args.log_level
    if getattr(args, "dry_run", False):
        config.buy.dry_run = True
    elif getattr(args, "live", False):
        config.buy.dry_run = False
        config.buy.validate()  # live mode has extra requirements (spending caps)
    return config


def build_sniper(config: AppConfig, client, *, buy_enabled: bool = True) -> Sniper:
    guard = ApiGuard(
        RateLimiter(config.runtime.min_api_interval),
        max_flood_wait=config.runtime.max_flood_wait,
        max_retries=config.runtime.max_retries,
    )
    state = State.load(config.runtime.state_path)
    return Sniper(
        config=config,
        client=client,
        market=MarketClient(client, guard),
        purchaser=Purchaser(
            client,
            guard,
            dry_run=config.buy.dry_run,
            hide_sender_name=config.buy.hide_sender_name,
            include_upgrade=config.buy.include_upgrade,
            message=config.buy.message,
        ),
        lot_filter=LotFilter(config.filters),
        budget=Budget(config.buy.budget, state),
        state=state,
        notifier=build_notifier(config.notify),
        buy_enabled=buy_enabled,
    )


async def cmd_login(config: AppConfig) -> int:
    client = await connect(config.telegram, interactive=True)
    try:
        me = await client.get_me()
        print(f"logged in as {me.first_name} (@{me.username or me.id})")
        print(f"session stored at {config.telegram.session_path}.session — treat it like a password")
    finally:
        await client.disconnect()
    return 0


async def cmd_whoami(config: AppConfig) -> int:
    client = await connect(config.telegram)
    try:
        me = await client.get_me()
        print(f"{me.first_name} (@{me.username or ''} id={me.id})")
    finally:
        await client.disconnect()
    return 0


async def cmd_balance(config: AppConfig) -> int:
    client = await connect(config.telegram)
    try:
        sniper = build_sniper(config, client)
        print(f"{await sniper.market.balance()}⭐")
    finally:
        await client.disconnect()
    return 0


async def cmd_catalog(config: AppConfig, show_all: bool) -> int:
    client = await connect(config.telegram)
    try:
        sniper = build_sniper(config, client, buy_enabled=False)
        lots = await sniper.market.catalog()
        lot_filter = sniper.filter
        shown = 0
        for lot in sorted(lots, key=lambda l: l.price):
            reason = lot_filter.reject_reason(lot)
            if reason and not show_all:
                continue
            marker = "  " if reason else "→ "
            suffix = f"   ({reason})" if reason else "   MATCH"
            print(f"{marker}{lot.describe()}{suffix}")
            shown += 1
        print(f"\n{shown} of {len(lots)} catalogue lots shown")
    finally:
        await client.disconnect()
    return 0


async def cmd_loop(config: AppConfig, *, buy_enabled: bool, once: bool, max_cycles: Optional[int]) -> int:
    client = await connect(config.telegram)
    try:
        sniper = build_sniper(config, client, buy_enabled=buy_enabled)
        await sniper.resolve_recipients()
        if once:
            report = await sniper.run_once()
            print(report.describe())
            for purchase in report.purchases:
                print(f"  • {purchase.describe()}")
            return 0
        await sniper.run_forever(max_cycles=max_cycles)
    except KeyboardInterrupt:
        log.info("interrupted — shutting down")
    finally:
        await client.disconnect()
    return 0


async def dispatch(args: argparse.Namespace) -> int:
    config = load_config(args)
    setup_logging(config.runtime.log_level, config.runtime.log_file)

    if args.command == "login":
        return await cmd_login(config)
    if args.command == "whoami":
        return await cmd_whoami(config)
    if args.command == "balance":
        return await cmd_balance(config)
    if args.command == "catalog":
        return await cmd_catalog(config, args.all)
    if args.command == "watch":
        return await cmd_loop(config, buy_enabled=False, once=args.once, max_cycles=None)
    if args.command == "run":
        if not config.buy.dry_run:
            log.warning("LIVE mode: matching lots will be paid for with real Telegram Stars")
        return await cmd_loop(config, buy_enabled=True, once=args.once, max_cycles=args.max_cycles)

    raise SystemExit(f"unknown command: {args.command}")


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(dispatch(args))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - top level: report, do not traceback-dump
        logging.getLogger("tgmarket").debug("fatal", exc_info=True)
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

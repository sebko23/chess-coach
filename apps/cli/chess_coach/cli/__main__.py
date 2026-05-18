"""``python -m chess_coach.cli`` entrypoint."""
from __future__ import annotations

import argparse
import sys


def _cmd_gateway(_: argparse.Namespace) -> int:
    from chess_coach.gateway.__main__ import main as gateway_main

    return gateway_main()


def _cmd_migrate(_: argparse.Namespace) -> int:
    from chess_coach.gateway.config import GatewaySettings
    from chess_coach.storage import migrate

    settings = GatewaySettings()
    applied = migrate(settings.sqlite_path, backups_dir=settings.backups_dir)
    if applied:
        for m in applied:
            print(f"applied {m.name} -> user_version={m.version}")
    else:
        print("up-to-date")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chess-coach", description="CHESS COACH backend CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gw = sub.add_parser("gateway", help="run the FastAPI gateway")
    p_gw.set_defaults(func=_cmd_gateway)

    p_mg = sub.add_parser("migrate", help="run pending SQL migrations and exit")
    p_mg.set_defaults(func=_cmd_migrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
# user/cli.py
"""CLI interface and main entry point for database management."""
import asyncio
import os
import sys

from clinictracker.user.config import load_config_for_service
from clinictracker.user.startup import get_args_and_logger_for_service
from clinictracker.user.user_service import run_service


async def cli() -> None:
    """Gets CLI arguments and runs the user service."""
    try:
        args, logger = get_args_and_logger_for_service()
        config = load_config_for_service(args)
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        await run_service(config=config, logger=logger)
    except asyncio.CancelledError:
        print("\nCancelled by user.", file=sys.stderr)
        os._exit(130)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception:
        sys.exit(1)


def main() -> None:
    asyncio.run(cli())

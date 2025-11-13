# -*- coding: utf-8 -*-
# cli.py
"""CLI interface and main entry point."""

import asyncio
import os
import sys

from clinictracker.config import load_config
from clinictracker.startup import get_args_and_logger, load_query
from clinictracker.core import run


async def cli() -> None:
    """Gets CLI arguments and runs application."""
    try:
        args, logger = get_args_and_logger()
        config = load_config(args)
        query = load_query(args)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        _ = await run(
            queries=[query], config=config, logger=logger, check_date=True
        )
    except asyncio.CancelledError:
        print("\nCancelled by user.", file=sys.stderr)
        os._exit(130)
    # except KeyboardInterrupt:
    #     print("\nInterrupted by user.", file=sys.stderr)
    #     sys.exit(130)
    except TimeoutError:
        os._exit(130)
    except Exception:
        # print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    asyncio.run(cli())

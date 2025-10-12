# -*- coding: utf-8 -*-
# cli.py
"""CLI interface and main entry point."""
import sys

from clinictracker.config import load_config
from clinictracker.startup import get_args_and_logger, load_query
from clinictracker.core import run


def main() -> None:
    """Gets CLI arguments and runs application."""
    try:
        args, logger = get_args_and_logger()
        config = load_config(args)
        query = load_query(args)
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        run(query, config, logger)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception:
        sys.exit(1)

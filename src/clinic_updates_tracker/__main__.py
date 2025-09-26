import sys
from .helpers import get_options
from .core import run


def main():
    """Gets options, runs program, cleans up on exception."""
    args, logger, target_url = get_options()
    if not args.url:
        logger.error("Error: URL not given.")
        sys.exit(1)

    success = run(args, logger, target_url)
    if success:
        args.quiet or logger.info("Done!")
    else:
        logger.error("Exit with error.")
        sys.exit(1)


if __name__ == "__main__":
    main()

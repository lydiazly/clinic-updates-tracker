import sys
from .helpers import get_full_url, get_options
from .core import run


def main():
    """Gets options, runs program, cleans up on exception."""
    args, logger = get_options()

    if not args.url.strip():
        logger.error("URL not given.")
        sys.exit(1)

    if args.days < 1:
        args.quiet or logger.info("days < 1. Nothing to do.")
        sys.exit(0)

    if args.nmax < 1:
        args.quiet or logger.info("nmax < 1. Nothing to do.")
        sys.exit(0)

    # Note: argument 'only_accepting' only affects the clinic table but not the update list
    query_dict = ({'only_accepting': 'yes'} if not args.all else {}) | {'list_town': args.city}
    target_url = get_full_url(args.url, '?', query_dict)

    success = run(args, logger, target_url)
    if success:
        args.quiet or logger.info("Done!")
    else:
        logger.error("Exit with error.")
        sys.exit(1)


if __name__ == "__main__":
    main()

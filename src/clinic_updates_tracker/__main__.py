import sys
from .helpers import get_options
from .core import run


def main():
    """Gets options, runs program, cleans up on exception."""
    args, logger, target_url = get_options()
    success = run(args, logger, target_url)
    if success:
        print("Done!", file=sys.stderr)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

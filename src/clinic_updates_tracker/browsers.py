# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/browsers.py
import argparse
import logging
import os
import subprocess
import sys
from playwright.sync_api import Playwright, Browser


def get_browser(
        p: Playwright,
        args: argparse.Namespace,
        logger: logging.Logger = logging.getLogger(),
        quiet: bool = False,
) -> Browser | None:
    """Checks/Installs and returns a browser.

    If in headless mode without setting `--headless-shell`, use the
    new chromium headless mode instead of a separate chromium headless shell.
    See: <https://playwright.dev/python/docs/browsers#chromium-new-headless-mode>
    """
    kwargs = {"headless": not args.headed}
    if args.browser == "chromium" and not args.headed and not args.shell:
        kwargs["channel"] = "chromium"
    logger.debug(f"Options: {kwargs}")

    env = os.environ.copy()  # including PLAYWRIGHT_BROWSERS_PATH
    try:
        browser = getattr(p, args.browser).launch(**kwargs)
        # browser = p.chromium.launch(**kwargs)
        return browser

    except Exception:
        deps_cmd = [sys.executable, "-m", "playwright", "install-deps"]
        cmd = [sys.executable, "-m", "playwright", "install"]
        # For chromium (headless)
        if args.browser == "chromium" and not args.headed:
            # Only use a separate chromium headless shell
            # https://playwright.dev/python/docs/browsers#chromium-headless-shell
            if args.shell:
                deps_cmd.append("chromium-headless-shell")
                cmd.append("--only-shell")
            # Use the new headless mode of real chrome, skipping a separate headless shell
            # https://playwright.dev/python/docs/browsers#chromium-new-headless-modehttps://playwright.dev/python/docs/browsers#chromium-headless-shell
            else:
                deps_cmd.append("chromium")
                cmd.append("--no-shell")
        cmd.append(args.browser)

        # Install system dependencies
        quiet or logger.info(f"Installing system dependencies for {args.browser}...")
        try:
            subprocess.run(deps_cmd, text=True, check=True, env=env)
            quiet or logger.info(f"Dependencies for {args.browser} installed.")
        except KeyboardInterrupt:
            logger.error("Interrupted by user.")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Failed to install dependencies for {args.browser}: {e}\n\n"
                + "> Install manually (will ask for sudo permissions):\n"
                + f"\t{' '.join(['python3']+deps_cmd[1:])}\n"
                + "  then try again.\n"
            )
            return None

        # Install browser
        quiet or logger.info(f"Installing {args.browser}...")
        try:
            subprocess.run(cmd, text=True, check=True, env=env)
            quiet or logger.info(f"{args.browser} installed.")
        except KeyboardInterrupt:
            logger.error("Interrupted by user.")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install {args.browser}: {e}")
            return None

        try:
            browser = getattr(p, args.browser).launch(**kwargs)
            return browser
        except Exception as e:
            logger.error(f"Failed to launch {args.browser}: {e}")
            return None

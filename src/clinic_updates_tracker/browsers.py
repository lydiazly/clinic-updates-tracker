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
        logger.info("Installing Chromium...")
        cmd = [sys.executable, "-m", "playwright", "install", "--with-deps"]
        # For chromium headless shell / chromium new headless mode
        if args.browser == "chromium" and not args.headed:
            if args.shell:
                cmd.append("--only-shell")
            else:
                cmd.append("--no-shell")
        cmd.append(args.browser)
        # Install
        try:
            subprocess.run(cmd, text=True, check=True, env=env)
            logger.info(f"{args.browser} installed.")
        except KeyboardInterrupt:
            logger.error("Interrupted by user.")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install browser: {args.browser}. Error: {e}")
            return None

        try:
            browser = getattr(p, args.browser).launch(**kwargs)
            return browser
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            return None

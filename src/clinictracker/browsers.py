# -*- coding: utf-8 -*-
# browsers.py
"""Installs and launches browsers."""
from logging import Logger, getLogger
import os
from playwright.sync_api import Playwright, Browser
import subprocess
import sys

from clinictracker.config import Config
from clinictracker.startup import MyLogger


def get_browser(
    p: Playwright,
    config: Config,
    logger: Logger | MyLogger = getLogger(),
) -> Browser:
    """Installs and returns a Browser object.

    If in headless mode without setting `--headless-shell`, use the
    new chromium headless mode instead of a separate chromium headless shell.
    See:
    <https://playwright.dev/python/docs/browsers#chromium-new-headless-mode>
    """
    kwargs: dict[str, bool | str] = {'headless': not config.headed_mode}
    # Add channel=chromium only for using new chromium headless mode
    if (
        config.browser_name == 'chromium'
        and not config.headed_mode
        and not config.headless_shell
    ):
        kwargs['channel'] = 'chromium'

    logger.debug(f"Options: {kwargs}")

    env = os.environ.copy()  # including PLAYWRIGHT_BROWSERS_PATH
    browser: Browser | None = None
    # Launch
    try:
        browser = getattr(p, config.browser_name).launch(**kwargs)
        # browser = p.chromium.launch(**kwargs)

    # If browser not found, install
    except Exception:
        deps_cmd = [sys.executable, '-m', 'playwright', 'install-deps']
        cmd = [sys.executable, '-m', 'playwright', 'install']
        # For chromium (headless)
        if config.browser_name == 'chromium' and not config.headed_mode:
            # Only use a separate chromium headless shell
            # https://playwright.dev/python/docs/browsers#chromium-headless-shell
            if config.headless_shell:
                deps_cmd.append('chromium-headless-shell')
                cmd.append('--only-shell')
            # Use the new headless mode of real chrome,
            # skipping installing a separate headless shell
            # https://playwright.dev/python/docs/browsers#chromium-new-headless-mode
            else:
                deps_cmd.append('chromium')
                cmd.append('--no-shell')
        cmd.append(config.browser_name)

        # Install system dependencies
        logger.info(
            f"Installing system dependencies for {config.browser_name}..."
        )
        try:
            subprocess.run(deps_cmd, text=True, check=True, env=env)
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Unable to install dependencies for {config.browser_name}:"
                f" {e}\n"
                "    Install manually via the following command "
                "(will ask for sudo permissions):\n\n"
                f"\t{' '.join(['python3'] + deps_cmd[1:])}\n"
            )
            raise RuntimeError
        else:
            logger.info("System dependencies installed.")

        # Install browser
        logger.info(f"Installing {config.browser_name}...")
        try:
            subprocess.run(cmd, text=True, check=True, env=env)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error installing '{config.browser_name}': {e}")
            raise RuntimeError
        else:
            logger.info(f"{config.browser_name} installed.")

        # Launch
        try:
            browser = getattr(p, config.browser_name).launch(**kwargs)
        except Exception as e:
            logger.error(
                f"{config.browser_name} not launched:\n"
                f"{type(e).__name__}: {e}"
            )
            raise RuntimeError
        else:
            return browser

    else:
        return browser

# clinic-updates-tracker

[![Run](https://github.com/lydiazly/clinic-updates-tracker/actions/workflows/run-task.yml/badge.svg?branch=main)](https://github.com/lydiazly/clinic-updates-tracker/actions/workflows/run-task.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![python](https://img.shields.io/badge/Python-3.11,3.12-3776AB?logo=python&logoColor=white)](https://www.python.org)

A Python package for tracking updates across all clinics in specified regions from a target website.

***This tool is developed for educational and personal use only.***

## Table of Contents<!-- omit in toc -->

- [Installation](#installation)
- [Usage](#usage)
- [Testing](#testing)
- [Important Legal Notice](#important-legal-notice)
  - [Usage Restrictions](#usage-restrictions)
  - [Target Website Information](#target-website-information)
  - [Your Responsibilities](#your-responsibilities)
  - [Disclaimer](#disclaimer)

## Installation

Install this module:

```sh
# Install from GitHub
python3 -m pip install git+https://github.com/lydiazly/clinic-updates-tracker.git
# Installs: clinictracker
```

To uninstall:

```sh
python3 -m pip uninstall clinictracker
```

## Usage

Example:

```sh
clinictracker
```

Usage:

```sh
clinictracker -h
```

```text
usage: clinictracker [-h] [options] [town/city]

Check updates on target website.

positional arguments:
  town/city             The town/city to be queried (default from $CITY)

options:
  -h, --help            show this help message and exit
  --url str             The target base URL (default from $TARGET_BASE_URL)
  --tz str              TZ identifier (IANA Time Zones) of the target website
                        (use local time zone if empty) (default from $TARGET_TZ)
  -d int, --days int    Number of days to look back for data collection
                        (default to 1 or from $DAYS_BACK)
  -n int, --nmax int    Maximum number of items to collect
                        (default to 1 or from $MAX_ITEMS)
  -p, --print           Print results as plain text to STDOUT (default: false)
  -o str, --output str  Path of output file (empty is interpreted as '.')
                        (default to './output/content.html' or from
                        $OUTPUT_HTML_PATH)
  --no-o                No export (default: export to a file)
  -H, --headed          Run in headed mode (default: headless)
  -b str, --browser str
                        Select a browser from: chromium, firefox, webkit
                        (default: chromium)
  --headless-shell      Use a separate headless shell for chromium headless mode
                        (https://playwright.dev/python/docs/browsers#chromium-headless-shell)
  --debug               Set the logging level to DEBUG
                        (default to false or from $DEBUG_MODE)
  --test                Exit after opening a page without any further operation
                        (default: false)
  -q, --quiet           Suppress INFO level outputs unless selecting --test or --debug
                        (default: print all)
```

## Testing

Run tests:

```sh
pytest tests --browser-channel chromium -s
```

## Important Legal Notice

### Usage Restrictions

- **Personal Use Only**: This tool is intended only for personal, educational, and research purposes.
- **No Commercial Use**: Commercial usage requires separate authorization.
- **Compliance Required**: Users must comply with target website's Terms of Service.

### Target Website Information

- **Website**: [Find a Doctor BC](https://findadoctorbc.ca)
- **Terms of Service**: [WWW.FINDADOCTORBC.CA TERMS OF SERVICE](https://findadoctorbc.ca/wp-content/uploads/2020/10/findadoctor-ca-terms-of-use-Ver2.htm)

### Your Responsibilities

By using this tool, you acknowledge that:

- You will use it in compliance with all applicable laws.
- You will respect rate limits and not overload servers.
- You will not use it for any prohibited or harmful purposes.
- You understand that web scraping may violate some websites' Terms of Service.

### Disclaimer

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND. THE AUTHORS ARE NOT RESPONSIBLE FOR ANY MISUSE, LEGAL ISSUES, OR DAMAGES ARISING FROM THE USE OF THIS SOFTWARE.

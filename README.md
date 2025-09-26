# clinic-updates-tracker

[![Run](https://github.com/lydiazly/clinic-updates-tracker/actions/workflows/run-task.yml/badge.svg?branch=main)](https://github.com/lydiazly/clinic-updates-tracker/actions/workflows/run-task.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org)

Fetches updates on a target public service platform such as Find a Doctor BC.

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
# Or install from local clone in editable/develop mode
git clone https://github.com/lydiazly/clinic-updates-tracker.git
cd clinic-updates-tracker
python3 -m pip install -e .
```

To uninstall:

```sh
python3 -m pip uninstall clinic-updates-tracker
```

## Usage

Example:

```sh
clinic-updates-tracker
```

Usage:

```sh
clinic-updates-tracker -h
```

```text
usage: clinic-updates-tracker [-h] [options] [city]

Check updates on target URL.

positional arguments:
  city                  town/city (default: Vancouver)

options:
  -h, --help            show this help message and exit
  --url [URL]           URL (default: read from .env if exists)
  -d [N], --days [N]    only show items within N days (default: read from .env if exists)
  -n [N], --nmax [N]    show first N items (default: read from .env if exists)
  -a, --all             all updates (only affects the clinic table but not the update list)
  -p, --print           print result as plain text to stdout
  -q, --quiet           only show errors but suppress info output in stderr, unless --test or --debug is set
  -H, --headed          run in headed mode (default: headless)
  --debug               print debug logs
  -b <browser>, --browser <browser>
                        choose a browser: chromium, firefox, webkit (default: chromium)
  --headless-shell      use a separate headless shell for chromium headless mode
  --test                test the browser without any page operation
```

## Testing

Install requirements:

```sh
python3 -m pip install -r requirements.txt
```

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

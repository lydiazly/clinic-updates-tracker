#!/bin/bash
set -e

export TEST_MODE=${TEST_MODE:-true}
export SEND_EMAILS=${SEND_EMAILS:-false}
export DAYS_BACK_MIN=${DAYS_BACK_MIN:-2}
export PERIOD_USER=${PERIOD_USER:-1}
export MAX_ITEMS_MIN=${MAX_ITEMS_MIN:-10}
export MAX_ITEMS_USER=${MAX_ITEMS_USER:-10}
export CLEANUP_BUFFER_DAYS=${CLEANUP_BUFFER_DAYS:-7}
export USERS_JSON_PATH="/app/data/users.json"
export IGNORE_HASH=${IGNORE_HASH:-false}
export RETRIES=${RETRIES:-3}
export PGSERVICEFILE="/app/config/pg_service.conf"
export PGPASSFILE="/app/.pgpass"
export PGSERVICE=${PGSERVICE:-dev}

if [ ! -s "${PGSERVICEFILE}" ]; then
  echo "${PGSERVICEFILE} not found or empty." >&2
  exit 1
fi

if [ ! -s "${PGPASSFILE}" ]; then
  echo "${PGPASSFILE} not found or empty." >&2
  exit 1
fi

sed -E -i 's/^localhost:/db:/' "${PGPASSFILE}"

if [ "${PGSERVICE}" = 'dev-local' ]; then
  export PGSERVICE=dev
fi

if [ -z "${SECRETS_PATH}" ] || [ ! -s "${SECRETS_PATH}" ]; then
  export SECRETS_PATH="/app/.secrets"
  echo "GMAIL_CLIENT_ID=${GMAIL_CLIENT_ID}" > "${SECRETS_PATH}"
  echo "GMAIL_CLIENT_SECRET=${GMAIL_CLIENT_SECRET}" >> "${SECRETS_PATH}"
  echo "GMAIL_REFRESH_TOKEN=${GMAIL_REFRESH_TOKEN}" >> "${SECRETS_PATH}"
  echo "GMAIL_SENDER=${GMAIL_SENDER}" >> "${SECRETS_PATH}"
fi

source "${SECRETS_PATH}"

echo -e "=== Environment Variables & Secrets ===\n"
echo "             TZ: ${TZ}"
echo "      TEST_MODE: ${TEST_MODE}"
echo "    SEND_EMAILS: ${SEND_EMAILS}"
echo "  DAYS_BACK_MIN: ${DAYS_BACK_MIN}"
echo "    PERIOD_USER: ${PERIOD_USER}"
echo "  MAX_ITEMS_MIN: ${MAX_ITEMS_MIN}"
echo " MAX_ITEMS_USER: ${MAX_ITEMS_USER}"
echo "        RETRIES: ${RETRIES}"
echo "TARGET_BASE_URL: ${TARGET_BASE_URL}"
echo "      TARGET_TZ: ${TARGET_TZ}"
echo "USERS_JSON_PATH: ${USERS_JSON_PATH}"
echo "    IGNORE_HASH: ${IGNORE_HASH}"
echo "   SECRETS_PATH: ${SECRETS_PATH:-none}"
echo ""
echo "PGSERVICEFILE: $(ls ${PGSERVICEFILE})"
echo "   PGPASSFILE: $(ls ${PGPASSFILE})"
echo "               $(cat ${PGPASSFILE} | rev | cut -d':' -f2- | rev):***"
echo "    PGSERVICE: ${PGSERVICE}"
echo ""
echo "    GMAIL_CLIENT_ID: ${GMAIL_CLIENT_ID:0:13}***"
echo "GMAIL_CLIENT_SECRET: ${GMAIL_CLIENT_SECRET:0:7}***"
echo "GMAIL_REFRESH_TOKEN: ${GMAIL_REFRESH_TOKEN:0:32}***"
echo "       GMAIL_SENDER: ${GMAIL_SENDER}"

# Run pytest
if [ "$1" = 'pytest' ]; then
  shift
  exec pytest "$@"
fi

# Run script
args=(
  --debug
  --headless-shell
  --url "${TARGET_BASE_URL}"
  --tz "${TARGET_TZ}"
  --retries ${RETRIES}
)
if [ "${SEND_EMAILS}" = 'true' ]; then
  args+=(--send)
fi
if [ "${IGNORE_HASH}" = 'true' ]; then
  args+=(--ignore-hash)
fi

echo -e "\n=== Step: Run script and send emails ===\n"
date

exec clinictracker-user "${args[@]}" "$@"

#!/bin/bash
set -e

# Set default environment variables
export TEST_MODE=${TEST_MODE:-true}
export KEEP_ALIVE=${KEEP_ALIVE:-false}
export SEND_EMAILS=${SEND_EMAILS:-false}
export DAYS_SINCE=${DAYS_SINCE:-90}
export MAX_N_ITEMS=${MAX_N_ITEMS:-10}
export RETRIES=${RETRIES:-3}
export OUTPUT_NAME="./output/content_docker.html"

echo "=== Environment Variables ==="
echo "TEST_MODE: ${TEST_MODE}"
echo "KEEP_ALIVE: ${KEEP_ALIVE}"
echo "SEND_EMAILS: ${SEND_EMAILS}"
echo "DAYS_SINCE: ${DAYS_SINCE}"
echo "MAX_N_ITEMS: ${MAX_N_ITEMS}"
echo "RETRIES: ${RETRIES}"
echo "TARGET_BASE_URL: ${TARGET_BASE_URL}"
echo "CITY: ${CITY}"
echo "OUTPUT_NAME: ${OUTPUT_NAME}"

echo "=== Running script ==="
for i in $(seq 1 ${RETRIES}); do
  clinic-updates-tracker --headless-shell \
    --url "${TARGET_BASE_URL}" \
    --days ${DAYS_SINCE} \
    --nmax ${MAX_N_ITEMS} \
    --output "${OUTPUT_NAME}" \
    "${CITY}"
  if [ $? -eq 0 ]; then break; fi
  echo "> Waiting to retry ($i/${RETRIES})..."
  sleep 5
done
echo "✓ Script completed successfully."

echo "=== Checking generated files ==="
[ -f "${OUTPUT_NAME}" ] || echo "No HTML files found" >&2

if [ -s "${OUTPUT_NAME}" ]; then
  content=$(cat "${OUTPUT_NAME}" | tr '\n' ' ')
  echo "✓ HTML content loaded (${#content} characters)"
  has_updates='true'
else
  echo "No updates in ${CITY} in the past ${DAYS_SINCE} days. Nothing to do."
  has_updates='false'
fi

echo "=== Checking parsed email list ==="
if [ "${TEST_MODE}" = 'true' ] || [ "${has_updates}" = 'true' ]; then
  recipient_list=$(echo "${RECIPIENT_LIST}" | xargs | sed -E 's/ *[\t ,]+ */, /g')
  if [ -z "${recipient_list}" ]; then
    echo "WARNING: No emails found in RECIPIENT_LIST" >&2
    has_recipients='false'
  else
    echo "> Parsed emails: ${recipient_list}"
    has_recipients='true'
    emails=${recipient_list}
  fi
fi

# If HTML file and emails exist, test email functionality
if [ "${SEND_EMAILS}" = 'true' ] \
    && { [ "${TEST_MODE}" = 'true' ] || [ "${has_updates}" = 'true' ]; } \
    && [ "${has_recipients}" = 'true' ]; then
  echo "=== Testing email functionality ==="
  echo "> Requesting Gmail access token..."

  access_token=$(curl -s \
    -d "client_id=${GMAIL_CLIENT_ID}" \
    -d "client_secret=${GMAIL_CLIENT_SECRET}" \
    -d "refresh_token=${GMAIL_REFRESH_TOKEN}" \
    -d "grant_type=refresh_token" \
    https://oauth2.googleapis.com/token | jq -r .access_token)

  if [ "${access_token}" != "null" ] && [ -n "${access_token}" ]; then
    echo "✓ Successfully obtained Gmail access token."
    echo "Token: ${access_token}"

    sender="Lydia Zhang <${GMAIL_SENDER}>"
    recipients="${emails}"
    repo="clinic-updates-tracker"
    is_test="${TEST_MODE}"

    subject_prefix=""
    [ "${is_test}" = "true" ] && subject_prefix=" [TEST]"
    subject_encoded=$(echo -n "${subject_prefix} Clinic News Alert" | base64)
    subject="=?UTF-8?B?${subject_encoded}?="

    body="<body>"
    body+="${content}"
    body+="<br><hr><p style=\"color:gray\">"
    body+="You are receiving this email because "
    body+="a GitHub Actions workflow <strong>run-task</strong> "
    body+="in repository <strong>${repo}</strong> is triggered."
    body+="</p>"
    body+="<p style=\"color:gray\">Sent by Docker container. Please do not reply directly.</p>"
    body+="</body>"

    raw_message="From: ${sender}\nTo: ${recipients}\nSubject: ${subject}"
    raw_message+="\nContent-Type: text/html; charset=UTF-8"
    raw_message=$(printf "${raw_message}\n\n${body}" | base64 | tr -d '\n')

    echo "> Sending to: ${recipients}"
    response=$(curl -s -X POST \
      -H "Authorization: Bearer ${access_token}" \
      -H "Content-Type: application/json" \
      -d "{\"raw\": \"${raw_message}\"}" \
      https://gmail.googleapis.com/gmail/v1/users/me/messages/send)
    if echo "${response}" | jq -e '.id' > /dev/null 2>&1; then
      echo "✓ Email sent successfully."
      echo "Response: ${response}"
    else
      echo "✗ Failed to send email: ${response}"
    fi
  else
    echo "✗ Failed to get Gmail access token."
  fi
elif [ "${SEND_EMAILS}" != 'true' ]; then
  echo "Skipping email test (SEND_EMAILS=false)."
else
  echo "Skipping email test (no updates or no recipients)."
fi

# Keep container running if requested
if [ "$KEEP_ALIVE" = "true" ]; then
  echo "Keeping container alive..."
  tail -f /dev/null
fi

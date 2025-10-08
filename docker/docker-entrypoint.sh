#!/bin/bash
set -e

export TEST_MODE=${TEST_MODE:-true}
export KEEP_ALIVE=${KEEP_ALIVE:-false}
export SEND_EMAILS=${SEND_EMAILS:-false}
export DAYS_SINCE=${DAYS_SINCE:-90}
export MAX_N_ITEMS=${MAX_N_ITEMS:-10}
export RETRIES=${RETRIES:-3}
export OUTPUT_NAME="./output/content_docker.html"

if [ -n "${SECRETS_FILE}" ] && [ -s "${SECRETS_FILE}" ]; then
  source "${SECRETS_FILE}"
fi

echo -e "=== Environment Variables ===\n"
echo "             TZ: ${TZ}"
echo "      TEST_MODE: ${TEST_MODE}"
echo "     KEEP_ALIVE: ${KEEP_ALIVE}"
echo "    SEND_EMAILS: ${SEND_EMAILS}"
echo "     DAYS_SINCE: ${DAYS_SINCE}"
echo "    MAX_N_ITEMS: ${MAX_N_ITEMS}"
echo "        RETRIES: ${RETRIES}"
echo "TARGET_BASE_URL: ${TARGET_BASE_URL}"
echo "      TARGET_TZ: ${TARGET_TZ}"
echo "           CITY: ${CITY}"
echo "    OUTPUT_NAME: ${OUTPUT_NAME}"
echo "   SECRETS_FILE: ${SECRETS_FILE:-none}"
echo ""
echo "    GMAIL_CLIENT_ID: ${GMAIL_CLIENT_ID:0:13}***"
echo "GMAIL_CLIENT_SECRET: ${GMAIL_CLIENT_SECRET:0:7}***"
echo "GMAIL_REFRESH_TOKEN: ${GMAIL_REFRESH_TOKEN:0:32}***"
echo "       GMAIL_SENDER: ${GMAIL_SENDER}"

echo -e "\n=== Step: Run script and save to OUTPUT_NAME ===\n"
date
set +e
for i in $(seq 1 ${RETRIES}); do
  clinic-updates-tracker --headless-shell \
    --url "${TARGET_BASE_URL}" \
    --tz "${TARGET_TZ}" \
    --days ${DAYS_SINCE} \
    --nmax ${MAX_N_ITEMS} \
    --output "${OUTPUT_NAME}" \
    "${CITY}"
  if [ $? -eq 0 ]; then break; fi
  echo "> Waiting to retry ($i/${RETRIES})..."
  sleep 5
done
set -e
echo "✓ Script completed successfully."

# Read the HTML file and set it as output, escaping newlines
if [ -s "${OUTPUT_NAME}" ]; then
  echo -e "\n=== Step: Check HTML content ===\n"
  content=$(cat "${OUTPUT_NAME}" | sed -E 's/^.*<body>(.+)<\/body>.*$/\1/')
  has_updates=true
  echo "has_updates=true"
  echo "✓ HTML content loaded (${#content} characters)"
else
  has_updates=false
  echo "has_updates=false"
  echo "No updates in ${CITY} in the past ${DAYS_SINCE} days. Nothing to do."
fi

if [ "${TEST_MODE}" = 'true' ] || [ "${has_updates}" = 'true' ]; then
  echo -e "\n=== Step: Parse recipient email list ===\n"
  recipient_list=$(echo "${RECIPIENT_LIST}" | xargs | sed -E 's/ *[\t ,]+ */, /g')
  if [ -z "${recipient_list}" ]; then
    echo "WARNING: No emails found in RECIPIENT_LIST" >&2
    has_recipients=false
    echo "has_recipients=false"
  else
    echo "> Parsed emails: ${recipient_list}"
    has_recipients=true
    echo "has_recipients=true"
    emails=${recipient_list}
    echo "emails=${recipient_list}"
  fi
else
  echo "> Skipping email parsing (no updates)."
fi

if [ "${SEND_EMAILS}" = 'true' ] \
    && { [ "${TEST_MODE}" = 'true' ] || [ "${has_updates}" = 'true' ]; } \
    && [ "${has_recipients}" = 'true' ]; then
  echo -e "\n=== Step: Send email to all listed users via Gmail API ===\n"
  if [ -n "${GMAIL_CLIENT_ID}" ] && [ -n "${GMAIL_CLIENT_SECRET}" ] && [ -n "${GMAIL_REFRESH_TOKEN}" ] && [ -n "${GMAIL_SENDER}" ]; then
    echo "> Requesting Gmail access token..."
    token_response=$(curl -s \
      -d "client_id=${GMAIL_CLIENT_ID}" \
      -d "client_secret=${GMAIL_CLIENT_SECRET}" \
      -d "refresh_token=${GMAIL_REFRESH_TOKEN}" \
      -d "grant_type=refresh_token" \
      https://oauth2.googleapis.com/token)
    access_token=$(echo ${token_response} | jq -r .access_token)

    if [ "${access_token}" = "null" ] || [ -z "${access_token}" ]; then
      echo -e "✗ Failed to get Gmail access token:\n${token_response}" >&2
    else
      echo "✓ Successfully obtained Gmail access token."
      echo -e "Token: ${access_token}\n"

      sender="Lydia Zhang <${GMAIL_SENDER}>"
      recipients="${emails}"
      repo="clinic-updates-tracker"
      is_test="${TEST_MODE}"

      subject_prefix=""
      [ "${is_test}" = "true" ] && subject_prefix=" [TEST]"
      subject_encoded=$(echo -n "${subject_prefix} Clinic News Alert" | base64)
      subject="=?UTF-8?B?${subject_encoded}?="

      body="<body>"
      body+=$(cat "${OUTPUT_NAME}" | sed -E 's/^.*<body>(.+)<\/body>.*$/\1/' | tr '\n' ' ')
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

      if echo "${response}" | jq -e '.id' >/dev/null 2>&1; then
        echo "✓ Email sent successfully."
        echo -e "Response:\n${response}\n"
      else
        echo -e "✗ Failed to send email:\n${response}" >&2
      fi
    fi

  else
    echo "✗ Gmail ID, secrets, token, or sender is missing." >&2
  fi

elif [ "${SEND_EMAILS}" != 'true' ]; then
  echo "> Skipping email sending (SEND_EMAILS=false)."

elif [ "${has_recipients}" != 'true' ]; then
  echo "> Skipping email sending (no recipients)."

else
  echo "> Skipping email sending (no updates)."
fi

# Keep container running if requested
if [ "$KEEP_ALIVE" = "true" ]; then
  echo "Keeping container alive..."
  tail -f /dev/null
fi

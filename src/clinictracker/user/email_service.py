# -*- coding: utf-8 -*-
# user/email_service.py
import base64
from dataclasses import dataclass
from dotenv import load_dotenv, dotenv_values
import json
from logging import Logger
import os
import requests
from textwrap import dedent

from clinictracker.startup import MyLogger, default_logger
from clinictracker.user.models import User
from clinictracker.user.config import SECRETS_PATH


@dataclass
class EmailParams:
    """Parameters for sending emails to a user.

    Attribute:
        user (User): user object containing username, emails, etc.
        body (str): email body in HTML format
    """

    user: User
    body: str = ''


class EmailService:
    SUBJECT = "Clinic Update Alerts"
    BODY_TEMPLATE: str = dedent(
        """
        <body>
        %s
        <br><hr>
        <p style="color:gray">
        You are receiving this email because a&nbsp;
        GitHub Actions workflow <strong>user-service</strong> in&nbsp;
        repository <strong>clinic-updates-tracker</strong> is triggered.
        </p>
        <p style="color:gray">Sent automatically.
         Please do not reply directly.</p>
        </body>
        """
    ).strip()
    MESSAGE_TEMPLATE: str = dedent(
        """
        From: %(from)s
        To: %(to)s
        Subject: %(subject)s
        Content-Type: text/html; charset=UTF-8

        %(body)s
        """
    ).strip()

    def __init__(
        self,
        logger: Logger | MyLogger = default_logger,
    ) -> None:
        self.logger: Logger | MyLogger = logger
        load_dotenv()
        self.test: bool = (
            os.getenv('TEST_MODE', 'false').strip().lower() == 'true'
        )
        self.__secrets: dict[str, str | None] = dotenv_values(SECRETS_PATH)
        self.sender: str = self.__secrets.get('GMAIL_SENDER') or ''
        if not self.sender:
            raise RuntimeError("✗ Sender is missing.")
        if not all(
            [
                self.__secrets.get('GMAIL_CLIENT_ID'),
                self.__secrets.get('GMAIL_CLIENT_SECRET'),
                self.__secrets.get('GMAIL_REFRESH_TOKEN'),
            ]
        ):
            raise RuntimeError("✗ Gmail ID, secrets, or token, is missing.")
        self.__access_token: str = ''

    def preview(self, email_params: EmailParams) -> None:
        """Print email content for this user to STDOUT."""
        hr = '-' * 60  # horizontal line
        # Prepare email
        recipients: str = ', '.join(email_params.user.emails)
        body_content: str = email_params.body
        # Build subject
        subject_prefix: str = " [TEST]" if self.test else ''
        subject_text: str = f"{subject_prefix} {self.SUBJECT}"
        # Create RFC 2822 message
        message: str = self.MESSAGE_TEMPLATE % {
            'from': self.sender,
            'to': recipients,
            'subject': subject_text,
            'body': body_content.strip(),
        }
        print(
            '\n'.join(
                [
                    f"\n>>> Email preview for {email_params.user.username} <<<",
                    hr,
                    message,
                    hr,
                ]
            )
        )

    def send(self, email_params: EmailParams) -> None:
        """Sends content to this user via Gmail API."""
        _user: User = email_params.user
        self.logger.debug(
            f"Recipients of {_user.username}: {', '.join(_user.emails)}"
        )
        self.call_gmail_api(email_params)

    def get_access_token(self) -> None:
        """Requests and returns access token."""
        if self.__access_token:
            return

        client_id: str = self.__secrets.get('GMAIL_CLIENT_ID') or ''
        client_secret: str = self.__secrets.get('GMAIL_CLIENT_SECRET') or ''
        refresh_token: str = self.__secrets.get('GMAIL_REFRESH_TOKEN') or ''

        if not all([client_id, client_secret, refresh_token, self.sender]):
            self.logger.error(
                "✗ Gmail ID, secrets, token, or sender is missing."
            )
            raise ValueError

        # Request access token
        self.logger.info(">>> Requesting Gmail access token...")
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }

        _access_token: str = ''
        try:
            _token_response = requests.post(token_url, data=token_data)
            _token_json = _token_response.json()
            _access_token = _token_json.get('access_token')
        except Exception as e:
            raise RuntimeError("✗ Error requesting access token.") from e
        else:
            if not _access_token:
                raise RuntimeError(
                    f"✗ Failed to get Gmail access token:\n"
                    f"{json.dumps(_token_json, indent=2)}"
                )
            self.logger.info("✓ Successfully obtained Gmail access token.")

        self.__access_token = _access_token

    def call_gmail_api(self, email_params: EmailParams) -> None:
        """Sends email via Gmail API using OAuth2 credentials."""
        self.get_access_token()

        # Prepare email
        recipients: str = ', '.join(email_params.user.emails)
        body_content: str = email_params.body

        # Build subject
        subject_prefix: str = " [TEST]" if self.test else ''
        subject_text: str = f"{subject_prefix} {self.SUBJECT}"
        subject_encoded: str = base64.b64encode(
            subject_text.encode('utf-8')
        ).decode('ascii')
        subject: str = f"=?UTF-8?B?{subject_encoded}?="

        # Build body
        body: str = self.BODY_TEMPLATE % body_content

        # Create RFC 2822 message
        message: str = self.MESSAGE_TEMPLATE % {
            'from': self.sender,
            'to': recipients,
            'subject': subject,
            'body': body,
        }

        # Encode message for Gmail API
        raw_message: str = base64.urlsafe_b64encode(
            message.encode('utf-8')
        ).decode('ascii')

        # Send email
        self.logger.info(f">>> Sending to: {recipients}")
        send_url: str = (
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        )
        headers = {
            'Authorization': f'Bearer {self.__access_token}',
            'Content-Type': 'application/json',
        }
        payload = {'raw': raw_message}

        try:
            response = requests.post(send_url, headers=headers, json=payload)
            response_json = response.json()

            if 'id' in response_json:
                self.logger.info("✓ Email sent successfully.")
                self.logger.debug(
                    f"Response:\n{json.dumps(response_json, indent=2)}\n"
                )
            else:
                raise RuntimeError(
                    "✗ Failed to send email:\n"
                    + json.dumps(response_json, indent=2)
                )

        except Exception as e:
            raise RuntimeError("✗ Error sending email.") from e

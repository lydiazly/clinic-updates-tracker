# -*- coding: utf-8 -*-
# user/email_service.py
from dataclasses import dataclass
from logging import Logger, getLogger

from clinictracker.startup import MyLogger
from clinictracker.user.models import User
from clinictracker.utils import html_to_plain


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

    def __init__(
        self,
        logger: Logger | MyLogger = getLogger(),
    ) -> None:
        self.logger: Logger | MyLogger = logger

    def preview(self, email_params: EmailParams) -> None:
        """Print email content for this user to STDOUT."""
        hr = '-' * 60  # horizontal line
        print(
            '\n'.join(
                [
                    f"- Email preview for {email_params.user.username}:",
                    f"To: {', '.join(email_params.user.emails)}",
                    f"Subject: {self.SUBJECT}",
                    hr,
                    html_to_plain(email_params.body),
                    hr,
                ]
            )
        )

    def send(self, email_params: EmailParams) -> None:
        """Sends content to this user."""
        _user: User = email_params.user
        _body: str = email_params.body
        self.logger.info(f"Sending email to {_user.username}...")
        self.logger.debug(f"Recipients: {', '.join(_user.emails)}")
        # TODO: Gmail API
        print("Mock sending...")
        self.logger.info("Email sent successfully.")

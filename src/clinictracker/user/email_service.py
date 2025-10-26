# -*- coding: utf-8 -*-
# user/email_service.py
from logging import Logger, getLogger

from clinictracker.startup import MyLogger
from clinictracker.user.models import User


class EmailService:
    @staticmethod
    def send_to_user(
        user: User, body: str, logger: Logger | MyLogger = getLogger()
    ) -> None:
        """Sends items to user via email."""
        SUBJECT = "Clinic Update Alerts"
        logger.info(f"Sending email to {user.username}...")
        print('-' * 60)
        print(f"To: {', '.join(user.emails)}")
        print(f"Subject: {SUBJECT}")
        print(f"Body:\n{body}")
        print('-' * 60)
        # TODO: Gmail API
        logger.info("Email sent successfully.")

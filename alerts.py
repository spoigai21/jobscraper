"""Multi-channel alert delivery for internship keyword detections."""

from __future__ import annotations

import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.text import MIMEText

import requests
from twilio.rest import Client

from config import Settings
from models import AlertPayload

logger = logging.getLogger(__name__)

NTFY_BASE_URL = "https://ntfy.sh"
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


class AlertManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._twilio_client: Client | None = None
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self._twilio_client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token,
            )

    def send_sms(self, payload: AlertPayload) -> bool:
        if not self._twilio_client:
            logger.error("SMS skipped: Twilio credentials are not configured")
            return False

        body = (
            f"INTERN ALERT: {payload.company} just posted internships!\n"
            f"Keyword: {payload.trigger_keyword}\n"
            f"Apply NOW: {payload.url}\n"
            f"Detected: {payload.detected_at}"
        )

        try:
            message = self._twilio_client.messages.create(
                body=body,
                from_=self._settings.twilio_from_number,
                to=self._settings.twilio_to_number,
            )
            logger.info("SMS sent (sid=%s)", message.sid)
            return True
        except Exception:
            logger.exception("Failed to send SMS for %s", payload.company)
            return False

    def send_voice_call(self, payload: AlertPayload) -> bool:
        if not self._twilio_client:
            logger.error("Voice call skipped: Twilio credentials are not configured")
            return False

        twiml = (
            "<Response>"
            "<Say voice='Polly.Matthew'>"
            f"{payload.company} internship alert. {payload.company} has posted a new internship "
            f"listing. The keyword {payload.trigger_keyword} was detected on their careers. "
            "Godspeed and good fucking yard."
            "</Say>"
            "<Pause length='1'/>"
            "<Say voice='Polly.Matthew'>"
            f"Repeating. {payload.company} internship detected. Check your messages now."
            "</Say>"
            "</Response>"
        )

        try:
            call = self._twilio_client.calls.create(
                twiml=twiml,
                to=self._settings.twilio_to_number,
                from_=self._settings.twilio_from_number,
            )
            logger.info("Voice call initiated (sid=%s)", call.sid)
            return True
        except Exception:
            logger.exception("Failed to initiate voice call for %s", payload.company)
            return False

    def send_push(self, payload: AlertPayload) -> bool:
        if not self._settings.ntfy_topic:
            logger.error("Push skipped: NTFY_TOPIC is not configured")
            return False

        url = f"{NTFY_BASE_URL}/{self._settings.ntfy_topic}"
        headers = {
            "Title": f"INTERN ALERT: {payload.company} Internship Posted!",
            "Priority": "urgent",
            "Tags": "rotating_light,briefcase",
            "Click": payload.url,
        }
        body = f"Keyword '{payload.trigger_keyword}' detected. Apply within 3 hours!"

        try:
            response = requests.post(
                url,
                headers=headers,
                data=body.encode("utf-8"),
                timeout=self._settings.request_timeout,
            )
            response.raise_for_status()
            logger.info("Push sent for %s", payload.company)
            return True
        except Exception:
            logger.exception("Failed to send push for %s", payload.company)
            return False

    def send_email(self, payload: AlertPayload) -> bool:
        if not all(
            (
                self._settings.gmail_address,
                self._settings.gmail_app_password,
                self._settings.alert_email_to,
            )
        ):
            logger.error("Email skipped: Gmail SMTP credentials are not configured")
            return False

        subject = f"INTERN ALERT: {payload.company} posted internships - apply NOW"
        body = (
            f"Internship alert for {payload.company}\n"
            f"Keyword: {payload.trigger_keyword}\n"
            f"Apply: {payload.url}\n"
            f"Detected: {payload.detected_at}\n\n"
            f"Change preview:\n{payload.diff_snippet}\n\n"
            "Sent by your internship monitor"
        )

        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = self._settings.gmail_address
        message["To"] = self._settings.alert_email_to

        try:
            with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(
                    self._settings.gmail_address,
                    self._settings.gmail_app_password,
                )
                smtp.sendmail(
                    self._settings.gmail_address,
                    [self._settings.alert_email_to],
                    message.as_string(),
                )
            logger.info("Email sent for %s", payload.company)
            return True
        except Exception:
            logger.exception("Failed to send email for %s", payload.company)
            return False

    def fire_all(self, payload: AlertPayload) -> dict[str, bool]:
        channels = {"sms": False, "call": False, "push": False, "email": False}
        tasks = {
            "sms": self.send_sms,
            "call": self.send_voice_call,
            "push": self.send_push,
            "email": self.send_email,
        }

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_channel = {
                executor.submit(handler, payload): name
                for name, handler in tasks.items()
            }
            for future in as_completed(future_to_channel):
                name = future_to_channel[future]
                try:
                    channels[name] = bool(future.result())
                except Exception:
                    logger.exception("Unexpected error in %s alert for %s", name, payload.company)
                    channels[name] = False

        ok = [n for n, v in channels.items() if v]
        bad = [n for n, v in channels.items() if not v]
        if ok:
            logger.info("Alert succeeded for %s: %s", payload.company, ", ".join(ok))
        if bad:
            logger.warning("Alert failed for %s: %s", payload.company, ", ".join(bad))

        return channels

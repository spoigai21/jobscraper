"""Multi-channel alert delivery for internship keyword detections."""

from __future__ import annotations

import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.text import MIMEText

import requests
from twilio.rest import Client

from config import Settings
from models import AlertPayload, AlertTier
from profile import AlertChannel, UserProfile

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

    def _apply_url(self, payload: AlertPayload) -> str:
        return payload.job_url or payload.url

    def _headline(self, payload: AlertPayload) -> str:
        if payload.job_title:
            return f"{payload.company} — {payload.job_title}"
        return payload.company

    def _score_line(self, payload: AlertPayload) -> str:
        if payload.relevance_score > 0:
            return f"Score {payload.relevance_score}"
        return ""

    def send_sms(self, payload: AlertPayload) -> bool:
        if not self._twilio_client:
            logger.error("SMS skipped: Twilio credentials are not configured")
            return False

        apply_url = self._apply_url(payload)
        score_line = self._score_line(payload)
        body = (
            f"INTERN ALERT: {self._headline(payload)}\n"
            f"{score_line + chr(10) if score_line else ''}"
            f"Keyword: {payload.trigger_keyword}\n"
            f"Apply NOW: {apply_url}\n"
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

        title_part = (
            f"{payload.job_title} at {payload.company}"
            if payload.job_title
            else f"{payload.company} internship"
        )
        score_part = (
            f" Relevance score {payload.relevance_score}."
            if payload.relevance_score > 0
            else ""
        )

        twiml = (
            "<Response>"
            "<Say voice='Polly.Matthew'>"
            f"High priority internship alert. {title_part}.{score_part} "
            f"The keyword {payload.trigger_keyword} was detected. "
            "Check your messages now."
            "</Say>"
            "<Pause length='1'/>"
            "<Say voice='Polly.Matthew'>"
            f"Repeating. {title_part}. Apply immediately."
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

        apply_url = self._apply_url(payload)
        url = f"{NTFY_BASE_URL}/{self._settings.ntfy_topic}"
        is_high = payload.tier == "high"
        score_line = self._score_line(payload)
        headers = {
            "Title": (
                f"{'🔥 ' if is_high else ''}{self._headline(payload)}"
            ),
            "Priority": "urgent" if is_high else "default",
            "Tags": "rotating_light,briefcase" if is_high else "briefcase",
            "Click": apply_url,
        }
        body_parts = [f"Keyword '{payload.trigger_keyword}' detected."]
        if score_line:
            body_parts.append(f"{score_line} · Apply within 3 hours!")
        else:
            body_parts.append("Apply within 3 hours!")
        body_parts.append(f"Link: {apply_url}")
        body = " ".join(body_parts)

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

        apply_url = self._apply_url(payload)
        score_line = self._score_line(payload)
        subject = f"INTERN ALERT: {self._headline(payload)} - apply NOW"
        body = (
            f"Internship alert for {self._headline(payload)}\n"
            f"Tier: {payload.tier}\n"
            f"{score_line + chr(10) if score_line else ''}"
            f"Keyword: {payload.trigger_keyword}\n"
            f"Apply: {apply_url}\n"
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

    def fire(self, payload: AlertPayload) -> dict[str, bool]:
        """Route alerts by tier: standard is push-only, high uses all channels."""
        channels = {"sms": False, "call": False, "push": False, "email": False}
        if payload.tier == "high":
            tasks = {
                "push": self.send_push,
                "call": self.send_voice_call,
                "sms": self.send_sms,
                "email": self.send_email,
            }
        else:
            tasks = {"push": self.send_push}

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_channel = {
                executor.submit(handler, payload): name
                for name, handler in tasks.items()
            }
            for future in as_completed(future_to_channel):
                name = future_to_channel[future]
                try:
                    channels[name] = bool(future.result())
                except Exception:
                    logger.exception(
                        "Unexpected error in %s alert for %s", name, payload.company
                    )
                    channels[name] = False

        ok = [n for n, v in channels.items() if v]
        bad = [n for n, v in channels.items() if not v]
        if ok:
            logger.info(
                "Alert succeeded for %s (%s tier): %s",
                payload.company,
                payload.tier,
                ", ".join(ok),
            )
        if bad:
            logger.warning(
                "Alert failed for %s (%s tier): %s",
                payload.company,
                payload.tier,
                ", ".join(bad),
            )

        return channels

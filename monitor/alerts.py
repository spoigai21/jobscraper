"""Multi-channel alert delivery for internship keyword detections."""

from __future__ import annotations

import html
import logging
import smtplib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import requests
from twilio.rest import Client

from monitor.config import Settings
from monitor.models import AlertPayload, AlertTier
from monitor.profile import AlertChannel, UserProfile

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")

NTFY_BASE_URL = "https://ntfy.sh"
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

_DEFAULT_STANDARD_CHANNELS: tuple[AlertChannel, ...] = ("push", "email")
_DEFAULT_HIGH_CHANNELS: tuple[AlertChannel, ...] = ("push", "call", "sms", "email")


class AlertManager:
    def __init__(
        self,
        settings: Settings,
        profile: UserProfile | None = None,
    ) -> None:
        self._settings = settings
        self._profile = profile
        self._twilio_client: Client | None = None
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self._twilio_client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token,
            )

    def _channels_for_tier(self, tier: AlertTier) -> tuple[AlertChannel, ...]:
        if self._profile is not None:
            if tier == "high":
                return self._profile.alerts.high.channels
            return self._profile.alerts.standard.channels
        if tier == "high":
            return _DEFAULT_HIGH_CHANNELS
        return _DEFAULT_STANDARD_CHANNELS

    def _channel_handlers(self) -> dict[AlertChannel, Callable[[AlertPayload], bool]]:
        return {
            "push": self.send_push,
            "call": self.send_voice_call,
            "sms": self.send_sms,
            "email": self.send_email,
        }

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

    @staticmethod
    def _format_voice_datetime(iso_timestamp: str) -> str:
        """Format an ISO timestamp for Twilio speech (e.g. June 20th, 9:34 PM EST)."""
        try:
            parsed = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        except ValueError:
            return iso_timestamp
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        eastern = parsed.astimezone(EASTERN)
        day = eastern.day
        if 11 <= day % 100 <= 13:
            ordinal = f"{day}th"
        else:
            ordinal = f"{day}{({1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th'))}"
        hour = eastern.hour % 12 or 12
        period = "AM" if eastern.hour < 12 else "PM"
        tz = eastern.strftime("%Z")
        return f"{eastern.strftime('%B')} {ordinal}, {hour}:{eastern.minute:02d} {period} {tz}"

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

        role_part = payload.job_title if payload.job_title else "internship"
        spoken_date = self._format_voice_datetime(payload.detected_at)
        company = html.escape(payload.company)
        role = html.escape(role_part)
        spoken_date_xml = html.escape(spoken_date)
        keyword = html.escape(payload.trigger_keyword)
        opening = (
            f"{company} {role} posted. "
            f"Date: {spoken_date_xml}. "
            f"Keyword: {keyword}."
        )
        repeat = html.escape(
            f"Repeating. {payload.company} {role_part} posted. Apply immediately."
        )

        twiml = (
            "<Response>"
            "<Say voice='Polly.Matthew'>"
            f"{opening} "
            "Godspeed and good fucking yard."
            "</Say>"
            "<Pause length='1'/>"
            "<Say voice='Polly.Matthew'>"
            f"{repeat}"
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

    def _http_header_value(self, text: str) -> str:
        """HTTP headers must be latin-1; normalize common Unicode punctuation."""
        return (
            text.replace("\u2014", "-")
            .replace("\u2013", "-")
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
        )

    def _push_title(self, payload: AlertPayload) -> str:
        headline = self._http_header_value(self._headline(payload))
        if payload.tier == "high":
            return f"HIGH: {headline}"
        return headline

    def _push_body(self, payload: AlertPayload) -> str:
        apply_url = self._apply_url(payload)
        parts = [payload.trigger_keyword]
        if payload.relevance_score > 0:
            parts.append(f"score {payload.relevance_score}")
        parts.append(f"Apply: {apply_url}")
        return " | ".join(parts)

    def send_push(self, payload: AlertPayload) -> bool:
        if not self._settings.ntfy_topic:
            logger.error("Push skipped: NTFY_TOPIC is not configured")
            return False

        apply_url = self._apply_url(payload)
        url = f"{NTFY_BASE_URL}/{self._settings.ntfy_topic}"
        is_high = payload.tier == "high"
        headers = {
            "Title": self._push_title(payload),
            "Priority": "urgent" if is_high else "default",
            "Tags": "rotating_light,briefcase" if is_high else "briefcase",
            "Click": apply_url,
        }
        body = self._push_body(payload)

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
        """Route alerts using profile.yaml channel lists for each tier."""
        channels: dict[str, bool] = {
            "sms": False,
            "call": False,
            "push": False,
            "email": False,
        }
        handlers = self._channel_handlers()
        active = self._channels_for_tier(payload.tier)
        tasks = {
            name: handlers[name]
            for name in active
            if name in handlers
        }

        with ThreadPoolExecutor(max_workers=max(len(tasks), 1)) as executor:
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

        attempted = set(tasks)
        ok = [n for n in attempted if channels[n]]
        bad = [n for n in attempted if not channels[n]]
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

    @staticmethod
    def any_success(results: dict[str, bool]) -> bool:
        """Return True when at least one alert channel succeeded."""
        return any(results.values())

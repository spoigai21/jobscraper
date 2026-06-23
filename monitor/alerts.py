"""Multi-channel alert delivery for internship keyword detections."""

from __future__ import annotations

import html
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from twilio.rest import Client

from monitor.config import Settings
from monitor.models import AlertPayload, AlertTier
from monitor.notification_keywords import title_from_diff_snippet
from monitor.profile import AlertChannel, UserProfile

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")

NTFY_BASE_URL = "https://ntfy.sh"

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

    def _priority_score_line(self, payload: AlertPayload) -> str:
        if payload.relevance_score > 0:
            return f"Priority score: {payload.relevance_score}"
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

    def _push_role_line(self, payload: AlertPayload) -> str:
        role = self._http_header_value(
            payload.job_title
            or title_from_diff_snippet(payload.diff_snippet)
            or "internship"
        )
        company = self._http_header_value(payload.company)
        return f"{company} - {role}"

    def _push_title(self, payload: AlertPayload) -> str:
        return self._push_role_line(payload)

    def _push_body(self, payload: AlertPayload) -> str:
        keywords = payload.notification_keywords
        if not keywords and payload.trigger_keyword:
            keywords = (payload.trigger_keyword,)
        keyword_text = ", ".join(keywords)
        apply_url = self._apply_url(payload)

        lines: list[str] = []
        if keyword_text:
            lines.append(f"Keywords detected: {keyword_text}")
        lines.append(f"Application: {apply_url}")
        return "\n".join(lines)

    def _email_subject(self, payload: AlertPayload) -> str:
        return self._push_title(payload)

    def _email_body(self, payload: AlertPayload) -> str:
        keywords = payload.notification_keywords
        if not keywords and payload.trigger_keyword:
            keywords = (payload.trigger_keyword,)
        keyword_text = ", ".join(keywords)
        apply_url = self._apply_url(payload)
        detected_at = self._format_voice_datetime(payload.detected_at)

        lines = [self._push_role_line(payload), ""]
        lines.append(f"Tier: {payload.tier}")
        priority_score = self._priority_score_line(payload)
        if priority_score:
            lines.append(priority_score)
        lines.append("")
        if keyword_text:
            lines.append(f"Keywords detected: {keyword_text}")
        lines.append(f"Application: {apply_url}")
        lines.append(f"Detected: {detected_at}")
        if payload.diff_snippet:
            lines.extend(["", payload.diff_snippet])
        lines.extend(["", "Sent by your internship monitor"])
        return "\n".join(lines)

    def _ntfy_email_topic(self) -> str:
        """Topic for email-only posts; do not subscribe to this on your phone."""
        return f"{self._settings.ntfy_topic}-email"

    def _post_ntfy(
        self,
        payload: AlertPayload,
        *,
        body: str,
        include_email: bool,
        topic: str | None = None,
    ) -> bool:
        if not self._settings.ntfy_topic:
            logger.error("ntfy skipped: NTFY_TOPIC is not configured")
            return False

        apply_url = self._apply_url(payload)
        is_high = payload.tier == "high"
        headers = {
            "Title": self._push_title(payload),
            "Priority": "urgent" if is_high else "default",
            "Click": apply_url,
        }

        if include_email:
            if not self._settings.ntfy_token:
                logger.error(
                    "Email skipped: NTFY_TOKEN is required for ntfy email delivery "
                    "(create one at https://ntfy.sh/account)"
                )
                return False
            if not self._settings.alert_email_to:
                logger.error("Email skipped: ALERT_EMAIL_TO is not configured")
                return False
            headers["Email"] = self._settings.alert_email_to
            headers["Authorization"] = f"Bearer {self._settings.ntfy_token}"

        publish_topic = topic or self._settings.ntfy_topic
        url = f"{NTFY_BASE_URL}/{publish_topic}"
        try:
            response = requests.post(
                url,
                headers=headers,
                data=body.encode("utf-8"),
                timeout=self._settings.request_timeout,
            )
            if not response.ok:
                logger.error(
                    "ntfy request failed for %s (%s): %s",
                    payload.company,
                    response.status_code,
                    response.text.strip(),
                )
                return False
            return True
        except Exception:
            logger.exception("Failed ntfy request for %s", payload.company)
            return False

    def send_push(self, payload: AlertPayload) -> bool:
        if not self._settings.ntfy_topic:
            logger.error("Push skipped: NTFY_TOPIC is not configured")
            return False

        ok = self._post_ntfy(
            payload,
            body=self._push_body(payload),
            include_email=False,
        )
        if ok:
            logger.info("Push sent for %s", payload.company)
        return ok

    def send_health_ping(
        self,
        *,
        uptime_hours: float,
        companies_checked: int,
        last_poll_at: str | None,
    ) -> bool:
        """Send a low-priority ntfy push confirming the monitor is alive."""
        if not self._settings.ntfy_topic:
            logger.error("Health ping skipped: NTFY_TOPIC is not configured")
            return False

        last_poll_line = last_poll_at or "unknown"
        body = (
            f"Monitor is alive.\n"
            f"Uptime: {uptime_hours:.1f} hours\n"
            f"Companies checked (last cycle): {companies_checked}\n"
            f"Last successful poll: {last_poll_line}"
        )
        headers = {
            "Title": "Internship monitor heartbeat",
            "Priority": "low",
            "Tags": "heartbeat,white_check_mark",
        }
        url = f"{NTFY_BASE_URL}/{self._settings.ntfy_topic}"
        try:
            response = requests.post(
                url,
                headers=headers,
                data=body.encode("utf-8"),
                timeout=self._settings.request_timeout,
            )
            if not response.ok:
                logger.error(
                    "Health ping ntfy request failed (%s): %s",
                    response.status_code,
                    response.text.strip(),
                )
                return False
            logger.info("Health ping sent")
            return True
        except Exception:
            logger.exception("Failed to send health ping")
            return False

    def _send_email_ntfy(self, payload: AlertPayload, body: str) -> bool:
        ok = self._post_ntfy(
            payload,
            body=body,
            include_email=True,
            topic=self._ntfy_email_topic(),
        )
        if ok:
            logger.info("Email sent for %s via ntfy", payload.company)
        return ok

    def send_email(self, payload: AlertPayload) -> bool:
        if not self._settings.alert_email_to:
            logger.error("Email skipped: ALERT_EMAIL_TO is not configured")
            return False
        if not self._settings.ntfy_topic:
            logger.error("Email skipped: NTFY_TOPIC is not configured")
            return False
        return self._send_email_ntfy(payload, self._email_body(payload))

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

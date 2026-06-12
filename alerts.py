"""Multi-channel alert delivery for internship keyword detections."""

from __future__ import annotations

import html
import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from twilio.rest import Client

from config import Settings
from models import AlertPayload

logger = logging.getLogger(__name__)

# ntfy.sh public notification endpoint (topic appended at runtime).
NTFY_BASE_URL = "https://ntfy.sh"

# Gmail SMTP endpoint for transactional alert email.
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


class AlertManager:
    """Dispatches internship alerts across SMS, voice, push, and email channels."""

    def __init__(self, settings: Settings) -> None:
        """Store runtime settings and prepare external clients when configured."""
        self._settings = settings
        self._twilio_client: Client | None = None

        if settings.twilio_account_sid and settings.twilio_auth_token:
            self._twilio_client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token,
            )

    def send_sms(self, payload: AlertPayload) -> bool:
        """Send an SMS alert via Twilio.

        Returns ``True`` when Twilio accepts the message, otherwise ``False``.
        """
        if not self._twilio_client:
            logger.error("SMS skipped: Twilio credentials are not configured")
            return False

        message_body = (
            f"🚨 INTERN ALERT: {payload.company} just posted internships!\n"
            f"Keyword: {payload.trigger_keyword}\n"
            f"Apply NOW: {payload.url}\n"
            f"Detected: {payload.detected_at}"
        )

        try:
            message = self._twilio_client.messages.create(
                body=message_body,
                from_=self._settings.twilio_from_number,
                to=self._settings.twilio_to_number,
            )
            logger.info("SMS sent successfully (sid=%s)", message.sid)
            return True
        except Exception:
            logger.exception("Failed to send SMS alert for %s", payload.company)
            return False

    def send_voice_call(self, payload: AlertPayload) -> bool:
        """Place an urgent voice call via Twilio with spoken alert content.

        Returns ``True`` when Twilio accepts the outbound call, otherwise ``False``.
        """
        if not self._twilio_client:
            logger.error("Voice call skipped: Twilio credentials are not configured")
            return False

        # TwiML is passed inline so no hosted webhook is required.
        twiml = (
            "<Response>"
            "<Say voice='Polly.Matthew'>"
            f"Urgent internship alert. {payload.company} has just posted a new internship "
            f"listing. The keyword {payload.trigger_keyword} was detected on their careers "
            "page. Check your phone for the direct link. Good luck."
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
            logger.info("Voice call initiated successfully (sid=%s)", call.sid)
            return True
        except Exception:
            logger.exception("Failed to initiate voice call for %s", payload.company)
            return False

    def send_push(self, payload: AlertPayload) -> bool:
        """Send a push notification through ntfy.sh.

        Returns ``True`` on HTTP success, otherwise ``False``.
        """
        if not self._settings.ntfy_topic:
            logger.error("Push notification skipped: NTFY_TOPIC is not configured")
            return False

        url = f"{NTFY_BASE_URL}/{self._settings.ntfy_topic}"
        headers = {
            "Title": f"🚨 {payload.company} Internship Posted!",
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
            logger.info("Push notification sent successfully for %s", payload.company)
            return True
        except Exception:
            logger.exception("Failed to send push notification for %s", payload.company)
            return False

    def send_email(self, payload: AlertPayload) -> bool:
        """Send a styled HTML email alert through Gmail SMTP.

        Returns ``True`` when the message is accepted by SMTP, otherwise ``False``.
        """
        if not all(
            (
                self._settings.gmail_address,
                self._settings.gmail_app_password,
                self._settings.alert_email_to,
            )
        ):
            logger.error("Email skipped: Gmail SMTP credentials are not configured")
            return False

        subject = f"🚨 INTERN ALERT: {payload.company} posted internships — apply NOW"
        html_body = self._build_email_html(payload)
        plain_body = (
            f"Internship alert for {payload.company}\n"
            f"Keyword: {payload.trigger_keyword}\n"
            f"Apply: {payload.url}\n"
            f"Detected: {payload.detected_at}\n\n"
            f"Change preview:\n{payload.diff_snippet}\n\n"
            "Sent by your internship monitor"
        )

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self._settings.gmail_address
        message["To"] = self._settings.alert_email_to
        message.attach(MIMEText(plain_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

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
            logger.info("Email sent successfully for %s", payload.company)
            return True
        except Exception:
            logger.exception("Failed to send email alert for %s", payload.company)
            return False

    def fire_all(self, payload: AlertPayload) -> dict[str, bool]:
        """Dispatch all alert channels concurrently.

        Each channel runs in its own worker thread so one slow or failing
        provider cannot block the others.

        Returns:
            Mapping of channel name to success flag:
            ``{"sms": bool, "call": bool, "push": bool, "email": bool}``.
        """
        channels: dict[str, bool] = {
            "sms": False,
            "call": False,
            "push": False,
            "email": False,
        }

        tasks = {
            "sms": self.send_sms,
            "call": self.send_voice_call,
            "push": self.send_push,
            "email": self.send_email,
        }

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_channel = {
                executor.submit(handler, payload): channel
                for channel, handler in tasks.items()
            }

            for future in as_completed(future_to_channel):
                channel = future_to_channel[future]
                try:
                    channels[channel] = bool(future.result())
                except Exception:
                    logger.exception(
                        "Unexpected error in %s alert worker for %s",
                        channel,
                        payload.company,
                    )
                    channels[channel] = False

        succeeded = [name for name, ok in channels.items() if ok]
        failed = [name for name, ok in channels.items() if not ok]

        if succeeded:
            logger.info(
                "Alert channels succeeded for %s: %s",
                payload.company,
                ", ".join(succeeded),
            )
        if failed:
            logger.warning(
                "Alert channels failed for %s: %s",
                payload.company,
                ", ".join(failed),
            )

        return channels

    @staticmethod
    def _build_email_html(payload: AlertPayload) -> str:
        """Render the HTML email body with inline styles for broad client support."""
        company = html.escape(payload.company)
        keyword = html.escape(payload.trigger_keyword)
        url = html.escape(payload.url, quote=True)
        detected_at = html.escape(payload.detected_at)
        diff_snippet = html.escape(payload.diff_snippet)

        return f"""\
<!DOCTYPE html>
<html lang="en">
  <body style="margin:0;padding:0;background-color:#f4f6f8;font-family:Arial,sans-serif;color:#1f2937;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0"
                 style="background:#ffffff;border-radius:12px;padding:32px;box-shadow:0 4px 16px rgba(0,0,0,0.08);">
            <tr>
              <td>
                <h1 style="margin:0 0 16px;font-size:28px;line-height:1.2;color:#111827;">
                  {company}
                </h1>
                <p style="margin:0 0 20px;font-size:16px;line-height:1.5;">
                  New internship posting detected on the careers page.
                </p>
                <p style="margin:0 0 12px;font-size:15px;">
                  <strong>Keyword detected:</strong> {keyword}
                </p>
                <p style="margin:0 0 24px;text-align:center;">
                  <a href="{url}"
                     style="display:inline-block;background:#dc2626;color:#ffffff;text-decoration:none;
                            font-weight:bold;font-size:16px;padding:14px 28px;border-radius:8px;">
                    Apply Now
                  </a>
                </p>
                <div style="margin:0 0 20px;padding:16px;background:#f9fafb;border-left:4px solid #2563eb;
                            border-radius:6px;font-family:Consolas,Monaco,monospace;font-size:13px;
                            white-space:pre-wrap;word-break:break-word;">
                  {diff_snippet}
                </div>
                <p style="margin:0 0 8px;font-size:14px;color:#4b5563;">
                  <strong>Detected at:</strong> {detected_at}
                </p>
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
                <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
                  Sent by your internship monitor
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

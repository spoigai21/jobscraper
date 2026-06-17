"""Persistent state and alert logging for the internship monitor.

Uses raw sqlite3 (no ORM) to track per-company poll state and alert delivery
history. A module-level ``start_time`` anchors uptime reporting in ``get_stats``.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from models import AlertPayload, StateRecord

logger = logging.getLogger(__name__)

# Captured once at import so uptime reflects process lifetime, not per-store instance.
start_time: datetime = datetime.now(timezone.utc)

# Channel keys expected in ``log_alert`` results dict.
_ALERT_CHANNELS: tuple[str, ...] = ("sms", "call", "push", "email")


class StateStore:
    """SQLite-backed persistence for company poll state and alert history.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """

    def __init__(self, db_path: str = "monitor.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with Row factory for dict-like row access."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # WAL improves concurrent read/write behaviour for a long-running monitor.
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        """Create schema tables if they do not already exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_state (
                    company      TEXT PRIMARY KEY,
                    url          TEXT NOT NULL,
                    last_hash    TEXT NOT NULL,
                    last_text    TEXT NOT NULL DEFAULT '',
                    last_checked TEXT NOT NULL,
                    last_alerted TEXT,
                    alert_count  INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS alert_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    company         TEXT NOT NULL,
                    url             TEXT NOT NULL,
                    trigger_keyword TEXT NOT NULL,
                    diff_snippet    TEXT NOT NULL,
                    detected_at     TEXT NOT NULL,
                    sms_ok          INTEGER NOT NULL DEFAULT 0,
                    call_ok         INTEGER NOT NULL DEFAULT 0,
                    push_ok         INTEGER NOT NULL DEFAULT 0,
                    email_ok        INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_alert_log_detected_at
                    ON alert_log (detected_at DESC);
                """
            )
            conn.commit()
            self._migrate_schema(conn)
        logger.debug("Initialized database at %s", self.db_path)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Apply additive schema migrations for existing databases."""
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(company_state)").fetchall()
        }
        if "last_text" not in columns:
            conn.execute(
                "ALTER TABLE company_state ADD COLUMN last_text TEXT NOT NULL DEFAULT ''"
            )
            conn.commit()
            logger.info("Migrated company_state: added last_text column")

    def get_state(self, company: str) -> StateRecord | None:
        """Return persisted state for *company*, or ``None`` if never seen.

        Missing or unknown companies are not treated as errors; callers receive
        ``None`` and can seed initial state via ``upsert_state``.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT company, url, last_hash, last_text, last_checked,
                       last_alerted, alert_count
                FROM company_state
                WHERE company = ?
                """,
                (company,),
            ).fetchone()

        if row is None:
            return None

        return StateRecord(
            company=row["company"],
            url=row["url"],
            last_hash=row["last_hash"],
            last_text=row["last_text"] or "",
            last_checked=row["last_checked"],
            last_alerted=row["last_alerted"],
            alert_count=row["alert_count"],
        )

    def upsert_state(self, record: StateRecord) -> None:
        """Insert or replace the full state row for *record.company*."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO company_state (
                    company, url, last_hash, last_text, last_checked,
                    last_alerted, alert_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company) DO UPDATE SET
                    url          = excluded.url,
                    last_hash    = excluded.last_hash,
                    last_text    = excluded.last_text,
                    last_checked = excluded.last_checked,
                    last_alerted = excluded.last_alerted,
                    alert_count  = excluded.alert_count
                """,
                (
                    record.company,
                    record.url,
                    record.last_hash,
                    record.last_text or "",
                    record.last_checked,
                    record.last_alerted,
                    record.alert_count,
                ),
            )
            conn.commit()
        logger.debug("Upserted state for company=%s", record.company)

    def log_alert(self, payload: AlertPayload, results: dict[str, bool]) -> None:
        """Append an alert row and persist per-channel delivery outcomes.

        Args:
            payload: Detected alert metadata.
            results: Map of channel name (``sms``, ``call``, ``push``, ``email``)
                to whether delivery succeeded. Missing keys are stored as failure.
        """
        channel_values = {
            f"{channel}_ok": 1 if results.get(channel, False) else 0
            for channel in _ALERT_CHANNELS
        }

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_log (
                    company, url, trigger_keyword, diff_snippet, detected_at,
                    sms_ok, call_ok, push_ok, email_ok
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.company,
                    payload.url,
                    payload.trigger_keyword,
                    payload.diff_snippet,
                    payload.detected_at,
                    channel_values["sms_ok"],
                    channel_values["call_ok"],
                    channel_values["push_ok"],
                    channel_values["email_ok"],
                ),
            )
            conn.commit()
        logger.info(
            "Logged alert for company=%s keyword=%s",
            payload.company,
            payload.trigger_keyword,
        )

    def get_all_states(self) -> list[StateRecord]:
        """Return every stored company state, ordered by company name."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT company, url, last_hash, last_text, last_checked,
                       last_alerted, alert_count
                FROM company_state
                ORDER BY company
                """
            ).fetchall()

        return [
            StateRecord(
                company=row["company"],
                url=row["url"],
                last_hash=row["last_hash"],
                last_text=row["last_text"] or "",
                last_checked=row["last_checked"],
                last_alerted=row["last_alerted"],
                alert_count=row["alert_count"],
            )
            for row in rows
        ]

    def get_recent_alerts(self, limit: int = 20) -> list[dict]:
        """Return the most recent alert rows as plain dicts (newest first).

        Args:
            limit: Maximum number of rows to return.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id, company, url, trigger_keyword, diff_snippet, detected_at,
                    sms_ok, call_ok, push_ok, email_ok
                FROM alert_log
                ORDER BY detected_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Return aggregate monitor statistics for dashboards and health checks.

        Returns:
            A dict with keys:

            - ``total_alerts``: Count of rows in ``alert_log``.
            - ``companies_monitored``: Count of rows in ``company_state``.
            - ``last_check_time``: ISO timestamp of the most recent poll, or
              ``None`` when no company has been checked yet.
            - ``next_check_time``: Reserved for the scheduler; ``None`` until an
              external component writes schedule metadata.
            - ``uptime_hours``: Hours since module ``start_time``.
        """
        with self._connect() as conn:
            total_alerts = conn.execute(
                "SELECT COUNT(*) AS n FROM alert_log"
            ).fetchone()["n"]
            companies_monitored = conn.execute(
                "SELECT COUNT(*) AS n FROM company_state"
            ).fetchone()["n"]
            last_check_row = conn.execute(
                "SELECT MAX(last_checked) AS ts FROM company_state"
            ).fetchone()

        last_check_time: str | None = last_check_row["ts"]
        now = datetime.now(timezone.utc)
        uptime_hours = round((now - start_time).total_seconds() / 3600, 2)

        return {
            "total_alerts": total_alerts,
            "companies_monitored": companies_monitored,
            "last_check_time": last_check_time,
            "next_check_time": None,
            "uptime_hours": uptime_hours,
        }

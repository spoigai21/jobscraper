"""SQLite persistence for poll state and alert history."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from monitor.models import AlertPayload, ClosedJobEvent, StateRecord

from monitor.config import DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

start_time = datetime.now(timezone.utc)
_CHANNELS = ("sms", "call", "push", "email")


class StateStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_state (
                    company      TEXT PRIMARY KEY,
                    url          TEXT NOT NULL,
                    last_hash    TEXT NOT NULL,
                    last_text    TEXT NOT NULL DEFAULT '',
                    seen_job_ids TEXT NOT NULL DEFAULT '[]',
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

                CREATE TABLE IF NOT EXISTS closed_jobs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    company     TEXT NOT NULL,
                    job_id      TEXT NOT NULL,
                    job_title   TEXT NOT NULL DEFAULT '',
                    company_url TEXT NOT NULL DEFAULT '',
                    detected_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerted_jobs (
                    dedup_key        TEXT PRIMARY KEY,
                    company          TEXT NOT NULL,
                    job_title        TEXT NOT NULL DEFAULT '',
                    job_url          TEXT NOT NULL DEFAULT '',
                    first_alerted_at TEXT NOT NULL,
                    last_alerted_at  TEXT NOT NULL,
                    alert_count      INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_alert_log_detected_at
                    ON alert_log (detected_at DESC);

                CREATE INDEX IF NOT EXISTS idx_alerted_jobs_last_alerted_at
                    ON alerted_jobs (last_alerted_at DESC);

                CREATE INDEX IF NOT EXISTS idx_closed_jobs_detected_at
                    ON closed_jobs (detected_at DESC);
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
        if "seen_job_ids" not in columns:
            conn.execute(
                "ALTER TABLE company_state ADD COLUMN seen_job_ids TEXT NOT NULL DEFAULT '[]'"
            )
            conn.commit()
            logger.info("Migrated company_state: added seen_job_ids column")
        if "seen_job_titles" not in columns:
            conn.execute(
                "ALTER TABLE company_state ADD COLUMN seen_job_titles TEXT NOT NULL DEFAULT '{}'"
            )
            conn.commit()
            logger.info("Migrated company_state: added seen_job_titles column")

    def get_state(self, company: str) -> StateRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT company, url, last_hash, last_text, seen_job_ids, seen_job_titles,
                       last_checked, last_alerted, alert_count
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
            seen_job_ids=row["seen_job_ids"] or "[]",
            seen_job_titles=row["seen_job_titles"] or "{}",
            last_checked=row["last_checked"],
            last_alerted=row["last_alerted"],
            alert_count=row["alert_count"],
        )

    def upsert_state(self, record: StateRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO company_state (
                    company, url, last_hash, last_text, seen_job_ids, seen_job_titles,
                    last_checked, last_alerted, alert_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company) DO UPDATE SET
                    url             = excluded.url,
                    last_hash       = excluded.last_hash,
                    last_text       = excluded.last_text,
                    seen_job_ids    = excluded.seen_job_ids,
                    seen_job_titles = excluded.seen_job_titles,
                    last_checked    = excluded.last_checked,
                    last_alerted    = excluded.last_alerted,
                    alert_count     = excluded.alert_count
                """,
                (
                    record.company,
                    record.url,
                    record.last_hash,
                    record.last_text or "",
                    record.seen_job_ids or "[]",
                    record.seen_job_titles or "{}",
                    record.last_checked,
                    record.last_alerted,
                    record.alert_count,
                ),
            )
            conn.commit()

    def log_alert(self, payload: AlertPayload, results: dict[str, bool]) -> None:
        channel_ok = tuple(1 if results.get(ch, False) else 0 for ch in _CHANNELS)
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
                    *channel_ok,
                ),
            )
            conn.commit()
        logger.info("Logged alert for %s (%s)", payload.company, payload.trigger_keyword)

    def record_alerted_job(self, payload: AlertPayload) -> None:
        """Remember that this role was alerted on, keyed by content not job ID."""
        if not payload.dedup_key:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alerted_jobs (
                    dedup_key, company, job_title, job_url,
                    first_alerted_at, last_alerted_at, alert_count
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(dedup_key) DO UPDATE SET
                    job_title       = excluded.job_title,
                    job_url         = excluded.job_url,
                    last_alerted_at = excluded.last_alerted_at,
                    alert_count     = alerted_jobs.alert_count + 1
                """,
                (
                    payload.dedup_key,
                    payload.company,
                    payload.job_title,
                    payload.job_url,
                    payload.detected_at,
                    payload.detected_at,
                ),
            )
            conn.commit()

    def recent_dedup_keys(self, since_iso: str) -> set[str]:
        """Dedup keys alerted on at or after ``since_iso``."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT dedup_key FROM alerted_jobs WHERE last_alerted_at >= ?",
                (since_iso,),
            ).fetchall()
        return {row["dedup_key"] for row in rows}

    def log_closed_job(self, event: ClosedJobEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO closed_jobs (
                    company, job_id, job_title, company_url, detected_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.company,
                    event.job_id,
                    event.job_title,
                    event.company_url,
                    event.detected_at,
                ),
            )
            conn.commit()
        logger.debug("Logged closed job for %s (%s)", event.company, event.job_id)

    def get_recent_closed_jobs(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT company, job_id, job_title, company_url, detected_at
                FROM closed_jobs
                ORDER BY detected_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_all_states(self) -> list[StateRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT company, url, last_hash, last_text, seen_job_ids, seen_job_titles,
                       last_checked, last_alerted, alert_count
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
                seen_job_ids=row["seen_job_ids"] or "[]",
                seen_job_titles=row["seen_job_titles"] or "{}",
                last_checked=row["last_checked"],
                last_alerted=row["last_alerted"],
                alert_count=row["alert_count"],
            )
            for row in rows
        ]

    def get_recent_alerts(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT company, trigger_keyword, detected_at,
                       sms_ok, call_ok, push_ok, email_ok
                FROM alert_log
                ORDER BY detected_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total_alerts = conn.execute(
                "SELECT COUNT(*) AS n FROM alert_log"
            ).fetchone()["n"]
            companies_monitored = conn.execute(
                "SELECT COUNT(*) AS n FROM company_state"
            ).fetchone()["n"]

        uptime_hours = round(
            (datetime.now(timezone.utc) - start_time).total_seconds() / 3600, 2
        )
        return {
            "total_alerts": total_alerts,
            "companies_monitored": companies_monitored,
            "uptime_hours": uptime_hours,
        }

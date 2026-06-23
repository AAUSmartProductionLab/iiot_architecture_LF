"""Read-only TimescaleDB access for the dashboard (latest ingested values).

Degrades to [] if the DB or table isn't available, so the dashboard still works
without the ingestion stack running.
"""

import logging

import psycopg

from . import config

log = logging.getLogger("measurements")


def latest() -> list[dict]:
    """Latest value per (device, datapoint) from the measurements hypertable."""
    try:
        with psycopg.connect(config.TS_DSN, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (device, datapoint)
                       device, datapoint, value, unit, time, topic
                FROM measurements
                WHERE device IS NOT NULL
                ORDER BY device, datapoint, time DESC
                """
            )
            return [
                {
                    "device": r[0],
                    "datapoint": r[1],
                    "value": r[2],
                    "unit": r[3],
                    "time": r[4].isoformat() if r[4] else None,
                    "topic": r[5],
                }
                for r in cur.fetchall()
            ]
    except Exception as e:
        log.debug("measurements unavailable: %s", e)
        return []

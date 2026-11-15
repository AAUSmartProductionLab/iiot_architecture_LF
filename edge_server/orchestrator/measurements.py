"""Read-only measurements: latest values tolerate outages; history reports them."""

import logging

import psycopg

from . import config

log = logging.getLogger("measurements")


def history(device: str, datapoint: str, start, end, limit: int, offset: int) -> tuple[list[dict], bool]:
    """Bounded read of stored records; preserve their historical unit and topic.

    Failures propagate so callers can distinguish an empty period from an outage.
    Unlike latest(), this never relabels samples using the current topic_map.
    """
    with psycopg.connect(config.TS_DSN, connect_timeout=3,
                         options="-c statement_timeout=5000 -c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT time, device, datapoint, value, unit, topic FROM measurements "
                "WHERE device = %s AND datapoint = %s AND time >= %s AND time < %s "
                "ORDER BY time, topic, value::text, unit LIMIT %s OFFSET %s",
                (device, datapoint, start, end, limit + 1, offset),
            )
            rows = cur.fetchall()
    return ([{"time": r[0].isoformat(), "device": r[1], "datapoint": r[2], "value": r[3],
              "unit": r[4], "topic": r[5]} for r in rows[:limit]], len(rows) > limit)


def latest() -> list[dict]:
    """Latest value per mapped datapoint.

    One index lookup per topic in topic_map (index measurements(topic, time DESC),
    created by the ingestor) instead of a DISTINCT ON over the whole hypertable,
    which slowed the dashboard down as data accumulated.
    """
    try:
        with psycopg.connect(config.TS_DSN, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.device, t.datapoint, m.value, t.unit, m.time, t.topic
                FROM topic_map t
                CROSS JOIN LATERAL (
                    SELECT value, time FROM measurements
                    WHERE topic = t.topic
                    ORDER BY time DESC
                    LIMIT 1
                ) m
                WHERE t.device IS NOT NULL
                ORDER BY t.device, t.datapoint
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

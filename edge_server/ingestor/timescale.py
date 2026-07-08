"""TimescaleDB access: one generic measurements hypertable + a topic_map.

No per-device tables — new devices add rows, not columns.
"""

import json
import logging

import psycopg

log = logging.getLogger("timescale")


class Timescale:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn: psycopg.Connection | None = None

    def connect(self) -> None:
        self.conn = psycopg.connect(self.dsn, autocommit=True)
        self._init_schema()
        log.info("connected to TimescaleDB")

    def _init_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    time      timestamptz NOT NULL DEFAULT now(),
                    topic     text NOT NULL,
                    device    text,
                    datapoint text,
                    value     jsonb,
                    unit      text
                );
                """
            )
            cur.execute(
                "SELECT create_hypertable('measurements', 'time', if_not_exists => TRUE);"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS topic_map (
                    topic     text PRIMARY KEY,
                    device    text,
                    datapoint text,
                    datatype  text,
                    unit      text
                );
                """
            )

    def _exec(self, sql: str, params: tuple):
        """Execute with one reconnect attempt on a dropped connection."""
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                return
            except psycopg.OperationalError:
                if attempt == 2:
                    raise
                log.warning("DB connection lost; reconnecting")
                self.connect()

    def upsert_topic(self, t: dict) -> None:
        self._exec(
            """
            INSERT INTO topic_map (topic, device, datapoint, datatype, unit)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (topic) DO UPDATE SET
                device = EXCLUDED.device, datapoint = EXCLUDED.datapoint,
                datatype = EXCLUDED.datatype, unit = EXCLUDED.unit;
            """,
            (t["topic"], t.get("device"), t.get("datapoint"), t.get("datatype"), t.get("unit")),
        )

    def lookup(self, topic: str) -> dict | None:
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(
                        "SELECT device, datapoint, unit FROM topic_map WHERE topic = %s",
                        (topic,),
                    )
                    r = cur.fetchone()
                    return {"device": r[0], "datapoint": r[1], "unit": r[2]} if r else None
            except psycopg.OperationalError:
                if attempt == 2:
                    raise
                self.connect()

    def insert(self, topic, payload, device, datapoint, unit, ts=None) -> None:
        v = json.dumps(payload) if not isinstance(payload, str) else payload
        if ts:
            self._exec(
                "INSERT INTO measurements (time, topic, device, datapoint, value, unit) "
                "VALUES (to_timestamp(%s), %s, %s, %s, %s, %s)",
                (ts, topic, device, datapoint, v, unit),
            )
        else:
            self._exec(
                "INSERT INTO measurements (topic, device, datapoint, value, unit) "
                "VALUES (%s, %s, %s, %s, %s)",
                (topic, device, datapoint, v, unit),
            )

"""TimescaleDB access: one generic measurements hypertable + a topic_map.

No per-device tables — new devices add rows, not columns. `value` is JSONB so a
datapoint can carry a scalar or a structured value without schema changes.

topic_map (topic -> device/datapoint/unit) is mirrored in memory: it is read for
every incoming message, so a DB round-trip per message would double the load.
The cache is the single writer's view (only this ingestor writes topic_map).
"""

import json
import logging

import psycopg

log = logging.getLogger("timescale")


class Timescale:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn: psycopg.Connection | None = None
        self._topics: dict[str, dict] = {}  # topic -> {device, datapoint, unit}

    def connect(self) -> None:
        self.conn = psycopg.connect(self.dsn, autocommit=True)
        self._init_schema()
        self._load_topic_map()
        log.info("connected to TimescaleDB (%d topic mappings)", len(self._topics))

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
            # Latest-value-per-topic lookups (dashboard) and per-topic queries.
            cur.execute(
                "CREATE INDEX IF NOT EXISTS measurements_topic_time_idx "
                "ON measurements (topic, time DESC);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS measurements_device_point_time_idx "
                "ON measurements (device, datapoint, time);"
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

    def _load_topic_map(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT topic, device, datapoint, unit FROM topic_map")
            self._topics = {
                r[0]: {"device": r[1], "datapoint": r[2], "unit": r[3]} for r in cur.fetchall()
            }

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

    # --- topic_map ------------------------------------------------------------

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
        self._topics[t["topic"]] = {
            "device": t.get("device"),
            "datapoint": t.get("datapoint"),
            "unit": t.get("unit"),
        }

    def remove_device_topics(self, device: str, keep: set[str] | None = None) -> int:
        """Drop a device's mappings except `keep` (datapoints removed from its AID,
        or the whole device when its AID is deleted). Stored measurements stay."""
        stale = [
            topic
            for topic, meta in self._topics.items()
            if meta["device"] == device and topic not in (keep or set())
        ]
        for topic in stale:
            self._exec("DELETE FROM topic_map WHERE topic = %s", (topic,))
            self._topics.pop(topic, None)
        return len(stale)

    def lookup(self, topic: str) -> dict | None:
        return self._topics.get(topic)

    # --- measurements -------------------------------------------------------

    def insert(self, topic, value, device, datapoint, unit, ts=None) -> None:
        """Store one sample. `value` is the datapoint value (scalar or structure),
        not the transport envelope."""
        v = json.dumps(value)
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

-- Same storage layout as the IIoT ingestor (edge_server/ingestor/timescale.py),
-- so the baseline and the architecture are compared on identical output.
CREATE TABLE IF NOT EXISTS measurements (
    time      timestamptz NOT NULL DEFAULT now(),
    topic     text NOT NULL,
    device    text,
    datapoint text,
    value     jsonb,
    unit      text
);
-- Hypertable when TimescaleDB is available (it is in the edge-server stack);
-- plain PostgreSQL works too for the baseline test.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        PERFORM create_hypertable('measurements', 'time', if_not_exists => TRUE);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS measurements_topic_time_idx ON measurements (topic, time DESC);

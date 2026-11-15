"""Real PostgreSQL/Timescale queries, isolated in a temporary schema.

Set HISTORY_TEST_DSN to a disposable test database; never uses TS_DSN implicitly.
"""
import os
import base64
import json
from pathlib import Path
import runpy
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator import api, config, measurements
from orchestrator.basyx_client import to_validated_json
from orchestrator.registration_service import RegistrationService
from festo_module import connector


@pytest.fixture
def database(monkeypatch):
    dsn = os.getenv("HISTORY_TEST_DSN")
    if not dsn:
        pytest.skip("set HISTORY_TEST_DSN to a disposable PostgreSQL database")
    connect = psycopg.connect
    schema = "history_test_" + uuid4().hex
    with connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        conn.execute("CREATE TABLE measurements (time timestamptz NOT NULL, topic text NOT NULL, "
                     "device text, datapoint text, value jsonb, unit text)")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - timedelta(minutes=10)
        rows = [
            (start, "old/topic", "GW1_festo_trial", "carrier_id", Jsonb(101), "old-unit"),
            (start + timedelta(seconds=1), "new/topic", "GW1_festo_trial", "carrier_id", Jsonb(102), "new-unit"),
            (start + timedelta(seconds=1), "new/topic", "GW1_festo_trial", "carrier_id", Jsonb(103), "new-unit"),
            (now, "new/topic", "GW1_festo_trial", "carrier_id", Jsonb(104), "new-unit"),
            (start, "other", "GW2_festo_trial", "carrier_id", Jsonb(999), ""),
            (start, "bool/topic", "GW1_festo_trial", "job_finished", Jsonb(True), ""),
            (start - timedelta(seconds=1), "old/topic", "GW1_festo_trial", "carrier_id", Jsonb(100), "old-unit"),
        ]
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO measurements VALUES (%s,%s,%s,%s,%s,%s)", rows)
    def scoped_connect(dsn, **kwargs):
        kwargs["options"] = kwargs.get("options", "") + " -c search_path=" + schema
        connection = connect(dsn, **kwargs)
        with connection.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            assert cur.fetchone()[0] == "on"
        return connection
    monkeypatch.setattr(measurements, "psycopg", SimpleNamespace(connect=scoped_connect))
    monkeypatch.setattr(config, "TS_DSN", dsn)
    monkeypatch.setattr(config, "PUBLIC_API_BASE_URL", "http://testserver")
    app = FastAPI()
    app.include_router(api.router)
    try:
        yield TestClient(app), start, now
    finally:
        with connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_generated_link_reads_only_its_series_and_pages_tied_times(database):
    client, start, end = database
    svc = RegistrationService()
    sms, _ = svc._build_device("GW1", connector("opc.tcp://localhost:4840"), svc._gateway_mqtt({}))
    ts = next(s for s in map(to_validated_json, sms) if s["idShort"] == "TimeSeries")
    segments = ts["submodelElements"][1]["value"]
    properties = next({e["idShort"]: e.get("value") for e in s["value"]} for s in segments
                      if any(e["idShort"] == "Datapoint" and e["value"] == "carrier_id" for e in s["value"]))
    query = parse_qs(properties["Query"])
    query.update(start=[start.isoformat()], end=[end.isoformat()], limit=[1])
    url = properties["Endpoint"] + "?" + urlencode(query, doseq=True)
    records = []
    for _ in range(5):
        response = client.get(url)
        assert response.status_code == 200
        body = response.json()
        records.extend(body["records"])
        url = body["next_url"]
        if not url:
            break
        assert parse_qs(urlsplit(url).query)["end"] == [end.isoformat()]
    assert [r["value"] for r in records] == [101, 102, 103]
    assert [r["unit"] for r in records] == ["old-unit", "new-unit", "new-unit"]
    assert records[0]["topic"] == "old/topic"
    assert all(r["device"] == "GW1_festo_trial" for r in records)
    assert not body["has_more"] and not body["page_limit_reached"]


def test_parameters_are_literal_and_json_types_survive(database):
    client, start, end = database
    params = {"device": "GW1_festo_trial", "datapoint": "carrier_id' OR TRUE; --",
              "start": start.isoformat(), "end": end.isoformat()}
    response = client.get("/api/measurements/history", params=params)
    assert response.status_code == 200 and response.json()["records"] == []
    params["datapoint"] = "job_finished"
    response = client.get("/api/measurements/history", params=params)
    assert response.status_code == 200 and response.json()["records"][0]["value"] is True


def test_example_discovers_submodel_and_reads_database(database, monkeypatch, capsys):
    client, start, end = database
    svc = RegistrationService()
    sms, shell = svc._build_device("GW1", connector("opc.tcp://localhost:4840"), svc._gateway_mqtt({}))
    shell = to_validated_json(shell)
    models = {s["id"]: s for s in map(to_validated_json, sms)}
    def read_json(url):
        path = urlsplit(url).path
        if path.startswith(("/shells/", "/submodels/")):
            encoded = path.rsplit("/", 1)[-1]
            identifier = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
            if path.startswith("/shells/"):
                assert identifier == shell["id"]
                return shell
            return models[identifier]
        response = client.get(url)
        assert response.status_code == 200
        return response.json()
    example = runpy.run_path(str(Path(__file__).resolve().parents[2] / "examples/read_device_history.py"))
    monkeypatch.setitem(example["main"].__globals__, "read_json", read_json)
    monkeypatch.setattr(sys, "argv", ["read_device_history.py", "--aas-url", "http://testserver",
        "--aas-id", shell["id"], "--datapoint", "carrier_id", "--start", start.isoformat(), "--end", end.isoformat()])
    example["main"]()
    assert [json.loads(line)["value"] for line in capsys.readouterr().out.splitlines()] == [101, 102, 103]

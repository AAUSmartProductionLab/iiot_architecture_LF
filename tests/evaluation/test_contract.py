"""Protect against false success from stale/wrong identity, type or metadata."""
from verify_contract import DEVICES, evaluate, study_points, uns_topic, valid_type


def rows():
    return [(uns_topic(n), DEVICES["s7"]["device"], n, u, 1 if dt == "DINT" else 1.5)
            for n, dt, u, _ in DEVICES["s7"]["datapoints"]]


def test_complete_baseline_and_missing_point():
    assert all(r["pass"] for r in evaluate(rows(), ["s7"], "baseline"))
    assert not all(r["pass"] for r in evaluate(rows()[:-1], ["s7"], "baseline"))


def test_gateway_identity_and_wrong_metadata():
    assert not any(r["pass"] for r in evaluate(rows(), ["s7"], "full", "GW1"))
    full = [(t, "GW1_" + d, n, u, v) for t, d, n, u, v in rows()]
    assert all(r["pass"] for r in evaluate(full, ["s7"], "full", "GW1"))
    bad = rows() + [(rows()[0][0], "wrong", "torque", "Nm", 1.5)]
    assert not evaluate(bad, ["s7"], "baseline")[0]["pass"]


def test_json_type_is_not_coerced():
    assert not valid_type(True, "float32")
    assert not valid_type("12.5", "real")
    assert not valid_type({"value": 12.5}, "real")
    assert not valid_type(float("nan"), "real")
    assert valid_type(False, "Boolean")
    assert not valid_type(1, "Boolean")


def test_festo_contract_uses_device_topics_and_unsigned_integers():
    device, points = study_points("festo")
    samples = [(topic, device, name, unit, False if dtype == "bool" else 123)
               for name, dtype, unit, topic in points]
    assert len(samples) == 5
    assert all("/devices/festo_trial/" in row[0] for row in samples)
    assert all(r["pass"] for r in evaluate(samples, ["festo"], "baseline"))
    qualified = [(t, "GW1_" + d, n, u, v) for t, d, n, u, v in samples]
    assert all(r["pass"] for r in evaluate(qualified, ["festo"], "full", "GW1"))
    assert not valid_type(1.5, "uint16")
    assert not valid_type(-1, "uint32")
    assert not valid_type(65536, "uint16")

"""Raw-bytes decoding for S7 and Modbus (connectors/connector_components/decoding.py)."""

import struct

import pytest

from connectors.connector_components.decoding import (
    modbus_decode,
    modbus_register_count,
    s7_decode,
    s7_read_size,
)


def regs(fmt: str, value) -> list[int]:
    raw = struct.pack(fmt, value)
    return list(struct.unpack(f">{len(raw) // 2}H", raw))


# --- Modbus -------------------------------------------------------------------

@pytest.mark.parametrize(
    "datatype, fmt, value",
    [
        ("int16", ">h", -1234),
        ("uint16", ">H", 65000),
        ("int32", ">i", -70000),
        ("uint32", ">I", 4_000_000_000),
        ("float32", ">f", 12.5),
        ("int64", ">q", -(2**40)),
        ("float64", ">d", 1000.125),
    ],
)
def test_modbus_big_endian(datatype, fmt, value):
    assert modbus_decode(regs(fmt, value), datatype) == value


def test_modbus_float32_is_not_the_raw_register():
    # Regression: the adapter used to publish registers[0] (16712 for 12.5).
    assert modbus_decode([16712, 0], "float32") == 12.5


def test_modbus_word_swapped():
    assert modbus_decode(regs(">f", 230.5)[::-1], "float32", "little") == 230.5


def test_modbus_float32_precision_is_float32_not_noise():
    assert modbus_decode(regs(">f", 12.8), "float32") == 12.8  # not 12.800000190734863


def test_modbus_register_counts():
    assert [modbus_register_count(t) for t in ("int16", "float32", "float64", "bool")] == [1, 2, 4, 1]
    with pytest.raises(ValueError):
        modbus_register_count("float16")


def test_modbus_bool():
    assert modbus_decode([1], "bool") is True


# --- S7 ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "datatype, fmt, value",
    [
        ("real", ">f", 12.5),
        ("lreal", ">d", 1000.25),
        ("int", ">h", -7),
        ("uint", ">H", 60000),
        ("dint", ">i", -42),
        ("udint", ">I", 4_000_000_000),
        ("sint", ">b", -5),
        ("usint", ">B", 200),
    ],
)
def test_s7_numeric(datatype, fmt, value):
    raw = struct.pack(fmt, value)
    assert s7_read_size(datatype) == len(raw)
    assert s7_decode(raw, datatype) == value


def test_s7_lreal_reads_8_bytes():
    # Regression: LREAL was decoded with get_real (4 bytes).
    assert s7_read_size("lreal") == 8


def test_s7_bool_bit():
    assert s7_decode(bytes([0b0000_0100]), "bool", bit=2) is True
    assert s7_decode(bytes([0b0000_0100]), "bool", bit=1) is False


def test_s7_bytes_and_aliases():
    assert s7_read_size("bytes", 3) == 3
    assert s7_decode(b"\x01\xab", "bytes") == "01ab"
    assert s7_read_size("float32") == 4  # older connectors used this name
    with pytest.raises(ValueError):
        s7_read_size("bytes", 0)
    with pytest.raises(ValueError):
        s7_read_size("string")

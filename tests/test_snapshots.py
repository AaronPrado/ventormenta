"""Tests de las instantáneas: ruta, sobre, escritura sin sobrescribir y validación del día."""

import base64
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, BinaryIO

import pytest

from ventormenta.esios import NATIVE_STEPS, RawResponse, day_params
from ventormenta.peninsular import day_bounds
from ventormenta.snapshots import (
    FORMAT_VERSION,
    Status,
    build_envelope,
    check_completeness,
    snapshot_path,
    write_snapshot,
)

ROOT = "/Volumes/ventormenta/raw/esios"
DAY = date(2026, 10, 15)
LONG_DAY = date(2026, 10, 25)
REQUESTED_AT = datetime(2026, 10, 14, 9, 5, 0, 123456, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 10, 14, 9, 5, 2, 654321, tzinfo=UTC)
QUARTER_HOUR = NATIVE_STEPS[541]
HOUR = NATIVE_STEPS[1777]


def make_raw(body: bytes, indicator_id: int = 541, day: date = DAY) -> RawResponse:
    return RawResponse(
        indicator_id=indicator_id,
        url=f"https://api.esios.ree.es/indicators/{indicator_id}",
        params=day_params(day),
        status_code=200,
        body=body,
        server_date="Wed, 14 Oct 2026 09:05:01 GMT",
        requested_at=REQUESTED_AT,
        received_at=RECEIVED_AT,
    )


def day_values(day: date, step: timedelta, count: int | None = None) -> list[dict[str, Any]]:
    """Valores con la forma de e·sios, uno por intervalo desde el inicio del día."""
    start = day_bounds(day)[0].astimezone(UTC)
    end = day_bounds(day)[1].astimezone(UTC)
    total = count if count is not None else (end - start) // step
    return [
        {
            "datetime_utc": (start + i * step).isoformat().replace("+00:00", "Z"),
            "geo_id": 8741,
            "value": 1234.5,
        }
        for i in range(total)
    ]


def body_with(values: list[dict[str, Any]]) -> bytes:
    return json.dumps({"indicator": {"id": 541, "values": values}}).encode()


class FakeUploader:
    """Doble de la Files API: guarda en memoria y falla si se intenta sobrescribir."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.directories: list[str] = []

    def create_directory(self, directory_path: str) -> None:
        self.directories.append(directory_path)

    def upload(self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None) -> None:
        if file_path in self.files and not overwrite:
            raise FileExistsError(file_path)
        self.files[file_path] = contents.read()


# --- Ruta ---


def test_snapshot_path_uses_utc_date_and_instant() -> None:
    assert snapshot_path(ROOT, 541, RECEIVED_AT) == (
        f"{ROOT}/indicators/541/capture_date=2026-10-14/20261014T090502Z.json"
    )


def test_snapshot_path_keeps_utc_date_when_peninsula_is_already_next_day() -> None:
    # 23:30 UTC del 14 son las 01:30 del 15 en la península: la carpeta sigue siendo la del 14.
    late = datetime(2026, 10, 14, 23, 30, tzinfo=UTC)
    assert "/capture_date=2026-10-14/20261014T233000Z.json" in snapshot_path(ROOT, 1777, late)


def test_snapshot_path_rejects_naive_datetime() -> None:
    naive = datetime(2026, 10, 14, 9, 5)  # noqa: DTZ001  (ingenuo a propósito)
    with pytest.raises(ValueError, match="zona horaria"):
        snapshot_path(ROOT, 541, naive)


# --- Sobre ---


def test_envelope_keeps_body_literal_with_its_hash() -> None:
    body = '{"value": 1.50,  "geo_name": "Península"}'.encode()
    envelope = json.loads(build_envelope(make_raw(body), DAY))
    response = envelope["response"]
    assert response["body_encoding"] == "utf-8"
    assert response["body"].encode("utf-8") == body
    assert response["body_sha256"] == hashlib.sha256(body).hexdigest()


def test_envelope_metadata() -> None:
    envelope = json.loads(build_envelope(make_raw(b"{}"), DAY))
    assert envelope["format_version"] == FORMAT_VERSION
    assert envelope["source"] == "esios"
    assert envelope["indicator_id"] == 541
    assert envelope["target_date"] == "2026-10-15"
    assert envelope["request"] == {
        "method": "GET",
        "url": "https://api.esios.ree.es/indicators/541",
        "params": day_params(DAY),
    }
    assert envelope["requested_at"] == "2026-10-14T09:05:00.123456+00:00"
    assert envelope["received_at"] == "2026-10-14T09:05:02.654321+00:00"
    assert envelope["response"]["status_code"] == 200
    assert envelope["response"]["server_date"] == "Wed, 14 Oct 2026 09:05:01 GMT"


def test_envelope_stores_non_utf8_body_as_base64() -> None:
    body = b"\xff\xfe no es UTF-8"
    response = json.loads(build_envelope(make_raw(body), DAY))["response"]
    assert response["body_encoding"] == "base64"
    assert base64.b64decode(response["body"]) == body
    assert response["body_sha256"] == hashlib.sha256(body).hexdigest()


# --- Escritura ---


def test_write_snapshot_uploads_envelope_without_overwrite() -> None:
    uploader = FakeUploader()
    raw = make_raw(b"{}")
    path = write_snapshot(uploader, ROOT, raw, DAY)
    assert path == snapshot_path(ROOT, 541, RECEIVED_AT)
    assert uploader.files[path] == build_envelope(raw, DAY)
    assert uploader.directories == [
        "/Volumes/ventormenta/raw/esios/indicators/541/capture_date=2026-10-14"
    ]


def test_write_snapshot_never_replaces_an_existing_capture() -> None:
    uploader = FakeUploader()
    raw = make_raw(b"{}")
    write_snapshot(uploader, ROOT, raw, DAY)
    with pytest.raises(FileExistsError):
        write_snapshot(uploader, ROOT, raw, DAY)


# --- Validación del día ---


@pytest.mark.parametrize(
    ("day", "step", "expected"),
    [(DAY, QUARTER_HOUR, 96), (DAY, HOUR, 24), (LONG_DAY, QUARTER_HOUR, 100), (LONG_DAY, HOUR, 25)],
)
def test_complete_day(day: date, step: timedelta, expected: int) -> None:
    result = check_completeness(make_raw(body_with(day_values(day, step)), day=day), day, step)
    assert result.status is Status.COMPLETE
    assert (result.found, result.expected) == (expected, expected)
    assert not result.retryable


def test_no_values_means_not_published() -> None:
    result = check_completeness(make_raw(body_with([])), DAY, HOUR)
    assert result.status is Status.NOT_PUBLISHED
    assert result.retryable


@pytest.mark.parametrize(
    "body",
    [
        b"<html>Mantenimiento</html>",
        b'{"errors": ["indicador no encontrado"]}',
        b'{"indicator": {"values": [{"value": 1.0}]}}',
        b'{"indicator": {"values": [{"datetime_utc": "no es una fecha"}]}}',
        b'{"indicator": {"values": [{"datetime_utc": "2026-10-15T00:00:00"}]}}',
    ],
)
def test_unreadable_response_is_retryable(body: bytes) -> None:
    result = check_completeness(make_raw(body), DAY, HOUR)
    assert result.status is Status.UNREADABLE
    assert result.retryable


def test_24_hours_on_a_25_hour_day_is_unexpected() -> None:
    values = day_values(LONG_DAY, HOUR, count=24)
    result = check_completeness(make_raw(body_with(values), day=LONG_DAY), LONG_DAY, HOUR)
    assert result.status is Status.UNEXPECTED
    assert (result.found, result.expected) == (24, 25)
    assert not result.retryable


def test_repeated_instant_is_unexpected_even_if_total_matches() -> None:
    values = day_values(DAY, HOUR)
    values[-1] = values[0]
    result = check_completeness(make_raw(body_with(values)), DAY, HOUR)
    assert result.status is Status.UNEXPECTED
    assert "1 repetidos" in result.detail


def test_value_outside_the_day_is_unexpected() -> None:
    values = day_values(DAY, HOUR)
    values.append(day_values(DAY + timedelta(days=1), HOUR, count=1)[0])
    result = check_completeness(make_raw(body_with(values)), DAY, HOUR)
    assert result.status is Status.UNEXPECTED
    assert "1 fuera del día" in result.detail

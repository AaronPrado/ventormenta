"""Tests del cliente de e·sios, con HTTP simulado: nunca se llama a e·sios."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
import requests
import responses
from responses import matchers

from ventormenta.esios import (
    ACCEPT,
    USER_AGENT,
    Clock,
    EsiosError,
    day_params,
    fetch_indicator_day,
)

TOKEN = "token-de-prueba"  # noqa: S105  (valor ficticio para los tests)
URL_541 = "https://api.esios.ree.es/indicators/541"
DAY = date(2026, 10, 15)
REQUESTED_AT = datetime(2026, 10, 14, 9, 5, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 10, 14, 9, 5, 2, tzinfo=UTC)


def fixed_clock(*moments: datetime) -> Clock:
    """Reloj que devuelve los instantes dados, en orden."""
    remaining = iter(moments)
    return lambda: next(remaining)


@pytest.fixture
def mocked() -> Iterator[responses.RequestsMock]:
    # Falla si alguna respuesta registrada no se llega a pedir.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        yield rsps


@pytest.mark.parametrize(
    ("day", "start", "end"),
    [
        (date(2026, 10, 14), "2026-10-14T00:00:00+02:00", "2026-10-14T23:59:59+02:00"),
        # Día de 25 horas: empieza en verano y acaba en invierno.
        (date(2026, 10, 25), "2026-10-25T00:00:00+02:00", "2026-10-25T23:59:59+01:00"),
        # Día de 23 horas: empieza en invierno y acaba en verano.
        (date(2027, 3, 28), "2027-03-28T00:00:00+01:00", "2027-03-28T23:59:59+02:00"),
    ],
)
def test_day_params_cover_the_peninsular_day(day: date, start: str, end: str) -> None:
    assert day_params(day) == {"start_date": start, "end_date": end}


def test_fetch_sends_headers_and_params(mocked: responses.RequestsMock) -> None:
    mocked.get(
        URL_541,
        body=b'{"indicator": {}}',
        match=[
            matchers.query_param_matcher(day_params(DAY)),
            matchers.header_matcher(
                {"x-api-key": TOKEN, "User-Agent": USER_AGENT, "Accept": ACCEPT}
            ),
        ],
    )
    result = fetch_indicator_day(
        requests.Session(), 541, DAY, TOKEN, clock=fixed_clock(REQUESTED_AT, RECEIVED_AT)
    )
    assert result.indicator_id == 541
    assert result.url == URL_541
    assert result.params == day_params(DAY)
    assert result.status_code == 200


def test_fetch_keeps_body_bytes_exactly(mocked: responses.RequestsMock) -> None:
    # Ceros finales, espacios dobles y UTF-8: parsear y volver a serializar los perdería.
    body = '{"value": 1.50,  "geo_name": "Península"}'.encode()
    mocked.get(URL_541, body=body)
    result = fetch_indicator_day(
        requests.Session(), 541, DAY, TOKEN, clock=fixed_clock(REQUESTED_AT, RECEIVED_AT)
    )
    assert result.body == body


def test_fetch_records_times_and_server_date(mocked: responses.RequestsMock) -> None:
    mocked.get(URL_541, body=b"{}", headers={"Date": "Wed, 14 Oct 2026 09:05:01 GMT"})
    result = fetch_indicator_day(
        requests.Session(), 541, DAY, TOKEN, clock=fixed_clock(REQUESTED_AT, RECEIVED_AT)
    )
    assert result.requested_at == REQUESTED_AT
    assert result.received_at == RECEIVED_AT
    assert result.server_date == "Wed, 14 Oct 2026 09:05:01 GMT"


@pytest.mark.parametrize("status", [401, 404, 500, 503])
def test_fetch_raises_on_http_error(mocked: responses.RequestsMock, status: int) -> None:
    mocked.get(URL_541, status=status)
    with pytest.raises(EsiosError, match="indicador 541") as excinfo:
        fetch_indicator_day(
            requests.Session(), 541, DAY, TOKEN, clock=fixed_clock(REQUESTED_AT, RECEIVED_AT)
        )
    assert TOKEN not in str(excinfo.value)


@pytest.mark.parametrize(
    "error", [requests.ConnectionError("sin conexión"), requests.Timeout("tiempo agotado")]
)
def test_fetch_raises_on_network_error(
    mocked: responses.RequestsMock, error: requests.RequestException
) -> None:
    mocked.get(URL_541, body=error)
    with pytest.raises(EsiosError, match="indicador 541"):
        fetch_indicator_day(
            requests.Session(), 541, DAY, TOKEN, clock=fixed_clock(REQUESTED_AT, RECEIVED_AT)
        )


def test_result_does_not_contain_token(mocked: responses.RequestsMock) -> None:
    mocked.get(URL_541, body=b"{}")
    result = fetch_indicator_day(
        requests.Session(), 541, DAY, TOKEN, clock=fixed_clock(REQUESTED_AT, RECEIVED_AT)
    )
    assert TOKEN not in repr(result)

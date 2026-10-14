"""Cliente HTTP de la API de e·sios (Red Eléctrica).

Devuelve el cuerpo de la respuesta tal como llega, sin parsear, porque las instantáneas lo
guardan byte a byte. El token viaja solo en la cabecera ``x-api-key``: ningún objeto que
devuelve este módulo lo contiene.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import requests

from ventormenta.peninsular import day_bounds

ESIOS_URL = "https://api.esios.ree.es/indicators/{indicator_id}"
USER_AGENT = "VenTormenta/0.1"
ACCEPT = "application/json; application/vnd.esios-api-v1+json"
TIMEOUT_SECONDS = 30

# Granularidad nativa de cada indicador sin time_trunc (caracterización en docs/fuentes-esios.md).
NATIVE_STEPS = {541: timedelta(minutes=15), 1777: timedelta(hours=1)}

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Instante actual en UTC, con zona horaria."""
    return datetime.now(UTC)


class EsiosError(RuntimeError):
    """La petición a e·sios falló: red, tiempo de espera o código HTTP de error."""


@dataclass(frozen=True)
class RawResponse:
    """Respuesta de e·sios sin interpretar, con los instantes de petición y recepción en UTC.

    ``received_at`` es posterior a la llegada completa del cuerpo: es la hora conservadora
    para fijar cuándo estuvo disponible el dato.
    """

    indicator_id: int
    url: str
    params: dict[str, str]
    status_code: int
    body: bytes
    server_date: str | None
    requested_at: datetime
    received_at: datetime


def day_params(day: date) -> dict[str, str]:
    """Parámetros ``start_date`` y ``end_date`` que cubren el día peninsular ``day``.

    El fin es el último segundo del día y no la medianoche siguiente: si ``end_date`` fuera
    inclusivo, esa medianoche ya sería el primer valor del día siguiente. Los desfases
    explícitos hacen que los días de 23 o 25 horas salgan completos.
    """
    start, end = day_bounds(day)
    last_second = end - timedelta(seconds=1)
    return {"start_date": start.isoformat(), "end_date": last_second.isoformat()}


def fetch_indicator_day(
    session: requests.Session,
    indicator_id: int,
    day: date,
    token: str,
    clock: Clock = utc_now,
) -> RawResponse:
    """Pide a e·sios un indicador para el día peninsular ``day``, con una sola petición.

    Lanza ``EsiosError`` si falla la red, se agota el tiempo de espera o la respuesta trae
    un código HTTP de error. No reintenta: los reintentos son del job, que así puede
    acotar cuántas peticiones se hacen al día.
    """
    url = ESIOS_URL.format(indicator_id=indicator_id)
    params = day_params(day)
    headers = {"Accept": ACCEPT, "User-Agent": USER_AGENT, "x-api-key": token}
    requested_at = clock()
    try:
        response = session.get(url, params=params, headers=headers, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as err:
        raise EsiosError(f"e·sios, indicador {indicator_id}: {err}") from err
    received_at = clock()
    return RawResponse(
        indicator_id=indicator_id,
        url=url,
        params=params,
        status_code=response.status_code,
        body=response.content,
        server_date=response.headers.get("Date"),
        requested_at=requested_at,
        received_at=received_at,
    )

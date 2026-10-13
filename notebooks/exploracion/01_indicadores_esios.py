# Databricks notebook source
# MAGIC %md
# MAGIC # Caracterización de los indicadores 541 y 1777 de e·sios
# MAGIC
# MAGIC De cada indicador: descripción oficial, granularidad, hora de publicación del D+1
# MAGIC y si sus valores cambian después de publicarse. Cada ejecución hace una petición
# MAGIC por indicador (ayer, hoy y mañana en hora peninsular) e imprime solo metadatos,
# MAGIC recuentos y huellas: los valores crudos no salen del workspace.

# COMMAND ----------

import hashlib
import html
import json
import re
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

ESIOS_URL = "https://api.esios.ree.es/indicators/{indicator_id}"
INDICATORS = (541, 1777)
USER_AGENT = "VenTormenta/0.1"
MADRID = ZoneInfo("Europe/Madrid")
PAUSE_SECONDS = 2
TIMEOUT_SECONDS = 30


def local_midnight(day: date) -> datetime:
    """Medianoche peninsular de ``day``, con la zona horaria explícita."""
    return datetime(day.year, day.month, day.day, tzinfo=MADRID)


def parse_utc(timestamp: str) -> datetime:
    """Convierte una marca ISO 8601 con zona horaria (incluido el sufijo ``Z``) a ``datetime``."""
    return datetime.fromisoformat(timestamp)


def fetch_indicator(
    indicator_id: int, start: datetime, end: datetime, token: str
) -> dict[str, Any]:
    """Pide un indicador de e·sios entre ``start`` y ``end`` y devuelve el objeto ``indicator``.

    Lanza ``RuntimeError`` si falla la petición y ``ValueError`` si la respuesta no
    tiene la forma esperada: en una exploración interesa ver el fallo, no esquivarlo.
    """
    headers = {
        "Accept": "application/json; application/vnd.esios-api-v1+json",
        "User-Agent": USER_AGENT,
        "x-api-key": token,
    }
    params = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    try:
        response = requests.get(
            ESIOS_URL.format(indicator_id=indicator_id),
            headers=headers,
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as err:
        raise RuntimeError(f"e·sios, indicador {indicator_id}: {err}") from err
    try:
        return response.json()["indicator"]
    except (ValueError, KeyError) as err:
        raise ValueError(
            f"e·sios, indicador {indicator_id}: respuesta inesperada"
        ) from err


def summarize_by_day(
    values: list[dict[str, Any]],
) -> dict[tuple[date, Any], dict[str, Any]]:
    """Agrupa los valores por día peninsular y zona: número, primera y última hora y huella.

    Se ordena y se calcula la huella en UTC porque en el cambio de hora de otoño
    las horas locales se repiten. La huella (SHA-256 de los valores ordenados)
    permite ver si un día cambia entre capturas sin exponer los datos crudos.
    """
    groups: dict[tuple[date, Any], list[tuple[datetime, Any]]] = defaultdict(list)
    for item in values:
        moment = parse_utc(item["datetime_utc"])
        key = (moment.astimezone(MADRID).date(), item.get("geo_id"))
        groups[key].append((moment, item["value"]))

    summary = {}
    for key, rows in sorted(groups.items()):
        rows.sort()
        canonical = json.dumps([(moment.isoformat(), value) for moment, value in rows])
        summary[key] = {
            "n": len(rows),
            "primera": rows[0][0].astimezone(MADRID).isoformat(),
            "ultima": rows[-1][0].astimezone(MADRID).isoformat(),
            "huella": hashlib.sha256(canonical.encode()).hexdigest()[:12],
        }
    return summary


def print_metadata(indicator: dict[str, Any]) -> None:
    """Imprime todos los metadatos del indicador (sin valores) y su descripción en texto plano."""
    metadata = {
        k: v for k, v in indicator.items() if k not in ("values", "description")
    }
    print(json.dumps(metadata, ensure_ascii=False, indent=2, default=str))
    description = re.sub(
        r"<[^>]+>", " ", html.unescape(indicator.get("description") or "")
    )
    print("Descripción:", " ".join(description.split()))


# COMMAND ----------

token = dbutils.secrets.get("ventormenta", "esios_token")  # noqa: F821  (global de Databricks)

captured_at = datetime.now(UTC)
today = captured_at.astimezone(MADRID).date()
tomorrow = today + timedelta(days=1)
start = local_midnight(today - timedelta(days=1))
end = local_midnight(today + timedelta(days=2)) - timedelta(seconds=1)

print(
    f"Captura: {captured_at.isoformat()} · {captured_at.astimezone(MADRID).isoformat()}"
)
print(f"Rango pedido: {start.isoformat()} → {end.isoformat()}")

for position, indicator_id in enumerate(INDICATORS):
    if position:
        time.sleep(PAUSE_SECONDS)
    indicator = fetch_indicator(indicator_id, start, end, token)
    print(f"\n===== Indicador {indicator_id} =====")
    print_metadata(indicator)
    summary = summarize_by_day(indicator.get("values", []))
    for (day, geo_id), stats in summary.items():
        print(f"{day} · geo {geo_id}: {stats}")
    if not any(day == tomorrow for day, _ in summary):
        print(f"⚠️ Sin valores para el D+1 ({tomorrow})")

# Databricks notebook source
# MAGIC %md
# MAGIC # Backfill de los I90 de e·sios
# MAGIC
# MAGIC Descarga al Volume los I90 (archivo 34) de un rango de días, cada uno una sola vez:
# MAGIC los días que ya están se saltan sin pedir nada, y el primer error corta la ejecución.
# MAGIC La lógica está en `ventormenta.archives`; aquí solo se leen los parámetros y el
# MAGIC secreto, y se informa de cada día.

# COMMAND ----------

import json
from datetime import date

import requests
from databricks.sdk import WorkspaceClient

from ventormenta.archives import download_days, plan_days
from ventormenta.esios import utc_now
from ventormenta.peninsular import MADRID

dbutils.widgets.text("start_date", "")  # noqa: F821  (global de Databricks)
dbutils.widgets.text("end_date", "")  # noqa: F821
dbutils.widgets.text("volume_root", "/Volumes/ventormenta/raw/esios")  # noqa: F821


def day_param(name: str) -> date:
    """Lee un parámetro de fecha ``AAAA-MM-DD`` y falla con un mensaje claro si no lo es."""
    raw = dbutils.widgets.get(name)  # noqa: F821
    try:
        return date.fromisoformat(raw)
    except ValueError as err:
        raise ValueError(f"{name} debe ser una fecha AAAA-MM-DD: {raw!r}") from err


# Todo se valida antes de leer el secreto y de hacer ninguna petición.
today = utc_now().astimezone(MADRID).date()
days = plan_days(day_param("start_date"), day_param("end_date"), today)
volume_root = dbutils.widgets.get("volume_root")  # noqa: F821
print(f"{len(days)} días, del {days[0]} al {days[-1]}, en {volume_root}")

# COMMAND ----------

token = dbutils.secrets.get("ventormenta", "esios_token")  # noqa: F821
files = WorkspaceClient().files
downloaded: list[str] = []
skipped: list[str] = []

with requests.Session() as session:
    for day, path in download_days(session, files, volume_root, days, token):
        if path is None:
            skipped.append(day.isoformat())
            print(f"{day}: ya estaba, sin peticiones")
        else:
            downloaded.append(day.isoformat())
            print(f"{day}: {path}")

print(f"Descargados: {len(downloaded)} · ya estaban: {len(skipped)}")
dbutils.notebook.exit(json.dumps({"downloaded": downloaded, "skipped": skipped}))  # noqa: F821

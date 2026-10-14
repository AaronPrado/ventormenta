# Databricks notebook source
# MAGIC %md
# MAGIC # Instantánea diaria de un indicador de e·sios
# MAGIC
# MAGIC Pide a e·sios el día D (el siguiente día peninsular) de un indicador, guarda la
# MAGIC respuesta literal en el Volume sin sobrescribir y comprueba que trae el día completo.
# MAGIC La lógica está en el paquete `ventormenta`; aquí solo se leen los parámetros y el
# MAGIC secreto, y se decide el resultado de la tarea.

# COMMAND ----------

import json

import requests
from databricks.sdk import WorkspaceClient

from ventormenta.esios import NATIVE_STEPS, fetch_indicator_day, utc_now
from ventormenta.peninsular import target_day
from ventormenta.snapshots import Status, check_completeness, write_snapshot

dbutils.widgets.text("indicator_id", "")  # noqa: F821  (global de Databricks)
dbutils.widgets.text("volume_root", "/Volumes/ventormenta/raw/esios")  # noqa: F821

raw_indicator = dbutils.widgets.get("indicator_id")  # noqa: F821
if not raw_indicator.isdigit() or int(raw_indicator) not in NATIVE_STEPS:
    raise ValueError(f"indicator_id debe ser uno de {sorted(NATIVE_STEPS)}: {raw_indicator!r}")
indicator_id = int(raw_indicator)
volume_root = dbutils.widgets.get("volume_root")  # noqa: F821

# COMMAND ----------

token = dbutils.secrets.get("ventormenta", "esios_token")  # noqa: F821
day = target_day(utc_now())

with requests.Session() as session:
    raw = fetch_indicator_day(session, indicator_id, day, token)

# Primero se guarda y después se valida: toda respuesta 200 es una observación con su hora.
path = write_snapshot(WorkspaceClient().files, volume_root, raw, day)
result = check_completeness(raw, day, NATIVE_STEPS[indicator_id])

print(f"Indicador {indicator_id} · día {day} · recibido {raw.received_at.isoformat()}")
print(f"Guardado en {path}")
print(f"Estado: {result.status} ({result.detail})")

# COMMAND ----------

if result.retryable:
    # La tarea falla para que el job reintente; cada reintento es una petición más.
    raise RuntimeError(f"Indicador {indicator_id}, día {day}: {result.status} ({result.detail})")

if result.status is Status.UNEXPECTED:
    print("⚠️ Recuento inesperado: guardado y sin reintentar, porque repetir devolvería lo mismo.")

dbutils.notebook.exit(  # noqa: F821
    json.dumps({"path": path, "status": result.status, "detail": result.detail})
)

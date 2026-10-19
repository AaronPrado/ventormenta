# Databricks notebook source
# MAGIC %pip install "python-calamine==0.8.3"

# COMMAND ----------

# MAGIC %md
# MAGIC # Estructura de los I90
# MAGIC
# MAGIC Spike de la serie gallega: qué hay dentro de los I90 descargados por el job
# MAGIC `i90_backfill` en tres fechas (enero y junio de 2025, en XLS; enero de 2026, en CSV) y
# MAGIC si el parser del paquete los lee. Solo lee del Volume: no hace ninguna petición a
# MAGIC e·sios. El paquete se importa de la copia que sube `databricks bundle deploy -t dev`
# MAGIC al workspace, así que hay que desplegar antes.

# COMMAND ----------

import json
import posixpath
import sys
import zipfile
from collections import Counter
from datetime import date
from io import BytesIO
from typing import Any

from databricks.sdk import WorkspaceClient
from python_calamine import CalamineWorkbook

workspace = WorkspaceClient()
files = workspace.files
user = workspace.current_user.me().user_name
sys.path.insert(0, f"/Workspace/Users/{user}/.bundle/ventormenta/dev/files/src")
from ventormenta.i90 import p48_rows, parse_p48  # noqa: E402

I90_DIR = "/Volumes/ventormenta/raw/esios/archives/34"
DAYS = ("2025-01-15", "2025-06-11", "2026-01-14")


def read_bytes(path: str) -> bytes:
    """Contenido de un fichero del Volume."""
    contents = files.download(path).contents
    if contents is None:
        raise RuntimeError(f"descarga sin contenido: {path}")
    with contents:
        return contents.read()


def day_pair(day: str) -> tuple[str, str]:
    """Rutas del zip y de su JSON lateral del día ``day`` (el par más reciente)."""
    directory = posixpath.join(I90_DIR, f"data_date={day}")
    names = sorted(e.name for e in files.list_directory_contents(directory) if e.name)
    stem = max(name.removesuffix(".zip") for name in names if name.endswith(".zip"))
    return posixpath.join(directory, f"{stem}.zip"), posixpath.join(directory, f"{stem}.json")


def sidecar(day: str) -> dict[str, Any]:
    """JSON lateral del zip del día ``day``."""
    data: dict[str, Any] = json.loads(read_bytes(day_pair(day)[1]))
    return data


def zip_member(day: str, name: str) -> bytes:
    """Un fichero de dentro del zip del día ``day``."""
    with zipfile.ZipFile(BytesIO(read_bytes(day_pair(day)[0]))) as archive:
        return archive.read(name)


# COMMAND ----------

# MAGIC %md
# MAGIC ## Descarga y contenedor

# COMMAND ----------

# Lo que dice el JSON lateral de cada descarga: fecha de publicación en el momento de
# descargar, si e·sios redirigió y tamaño del zip.
for day in DAYS:
    data = sidecar(day)
    archive = json.loads(data["detail"]["body"])["archive"]
    file = data["file"]
    print(f"{day} · publicado {archive['publication_date']} · recibido {file['received_at']}")
    print(f"    redirigido a: {file['redirected_to']} · {file['size']:,} bytes")

# COMMAND ----------

# Ficheros dentro de cada zip: un XLS con todas las hojas o un CSV por hoja.
for day in DAYS:
    with zipfile.ZipFile(BytesIO(read_bytes(day_pair(day)[0]))) as archive:
        print(f"{day}:")
        for info in archive.infolist():
            print(f"    {info.filename} · {info.file_size:,} bytes · {info.date_time}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Índice de hojas
# MAGIC
# MAGIC La hoja 00 lleva la fecha del informe, la de publicación y el contenido del libro. La
# MAGIC numeración de las hojas cambia entre épocas; la del P48 es la 02 en las dos.

# COMMAND ----------

# Época CSV: UTF-8 con BOM, separador «;» y fin de línea CRLF (se ve en los primeros bytes).
index = zip_member("2026-01-14", "I90DIA00_20260114.csv")
print(repr(index[:120]))
print(index.decode("utf-8-sig"))

# COMMAND ----------

# Época XLS: nombres de las hojas y primera hoja, con la fecha del informe y el índice.
workbook = CalamineWorkbook.from_filelike(BytesIO(zip_member("2025-01-15", "I90DIA_20250115.xls")))
print(workbook.sheet_names)
for row in workbook.get_sheet_by_name(workbook.sheet_names[0]).to_python()[:60]:
    print(row)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Hoja del P48

# COMMAND ----------

# Cabeceras de la hoja del P48 en las tres fechas, recortadas a las primeras celdas.
for day in DAYS:
    rows = p48_rows(read_bytes(day_pair(day)[0]), date.fromisoformat(day))
    print(f"{day}:")
    for row in rows[:4]:
        print(f"    {len(row)} celdas · {list(row)[:6]}")

# COMMAND ----------

# El parser del paquete sobre los ficheros reales: es la única prueba del adaptador XLS.
for day in DAYS:
    data_date = date.fromisoformat(day)
    values = parse_p48(p48_rows(read_bytes(day_pair(day)[0]), data_date), data_date)
    units = {value.unit: value.offer_type for value in values}
    print(f"{day}: {len(values):,} valores · {len(units):,} UP")
    print(f"    {values[0].valid_time.isoformat()} → {values[-1].valid_time.isoformat()}")
    print("    UP por Tipo Oferta:", dict(sorted(Counter(units.values()).items())))
